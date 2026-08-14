#!/usr/bin/env python3
"""Usage/cost ledger for the shared tiered LLM client (_shared/llm.py).

Every billed API call in chat()/_chat_for_escalation appends one JSON line to
<repo>/data/cost_ledger.jsonl: ts, tier, model, tokens, peak flag, est_cost.
Local/free tiers cost $0 but are recorded for call-count visibility.

Rates (DeepSeek v4, peak/off-peak effective 2026-08-16 — brain runbook
meta/known-issues-and-fixes.md#deepseek_peak_billing):
    flash  off-peak $0.22/M in · $0.66/M out · peak $0.44/M in · $1.32/M out
    pro    off-peak $0.66/M in · $1.98/M out · peak $1.32/M in · $3.96/M out
Cache-hit input is ~30x cheaper (1/30 of the input rate). Peak windows (UTC):
01:00-04:00 & 06:00-10:00. All other tiers (local/free/openrouter/groq) $0.

This module NEVER raises — ledgering is an optimization, not a failure source.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
LEDGER = DATA_DIR / "cost_ledger.jsonl"

# model-name prefix -> (input $/M off-peak, output $/M off-peak, peak multiplier)
_RATES = {
    "deepseek-v4-flash": (0.22, 0.66, 2.0),
    "deepseek-v4-pro": (0.66, 1.98, 2.0),
}
PEAK_MULT = 2.0          # fallback for unlisted deepseek models
CACHE_HIT_DISCOUNT = 30  # ~30x cheaper cache-hit input
CACHE_HIT_MULT = 1.0 / CACHE_HIT_DISCOUNT

# DeepSeek peak windows (UTC) — see runbook. Inclusive on both ends.
_PEAK_WINDOWS = ((1, 4), (6, 10))


def is_peak(dt: datetime | None = None) -> bool:
    """True when dt (default now, UTC) falls inside a DeepSeek peak window."""
    dt = dt or datetime.now(timezone.utc)
    h = dt.hour if dt.tzinfo else dt.replace(tzinfo=timezone.utc).hour
    return any(start <= h <= end for start, end in _PEAK_WINDOWS)


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int,
                  cache_hit_tokens: int = 0, dt: datetime | None = None) -> float:
    """Estimated USD for one completion (0.0 for unknown/free models).

    DeepSeek usage counts cache-hit tokens inside prompt_tokens, so input
    cost = miss_tokens x in_rate + hit_tokens x in_rate/30.
    """
    key = (model or "").lower()
    rates = _RATES.get(key)
    if rates is None:
        for prefix, r in _RATES.items():
            if key.startswith(prefix):
                rates = r
                break
    if rates is None:
        return 0.0
    in_rate, out_rate, peak_mult = rates
    mult = peak_mult if is_peak(dt) else 1.0
    hit = max(0, int(cache_hit_tokens or 0))
    miss = max(0, int(prompt_tokens or 0) - hit)
    usd = (miss * in_rate + hit * in_rate * CACHE_HIT_MULT
           + max(0, int(completion_tokens or 0)) * out_rate) * mult / 1_000_000
    return round(usd, 6)


def record_usage(tier: str, model: str, usage, caller: str = "") -> None:
    """Append one ledger line for a billed completion. Never raises."""
    try:
        u = usage or {}
        pt = int(getattr(u, "prompt_tokens", 0) or 0)
        ct = int(getattr(u, "completion_tokens", 0) or 0)
        cht = int(getattr(u, "prompt_cache_hit_tokens", 0) or 0)
        now = datetime.now(timezone.utc)
        entry = {
            "ts": now.isoformat(),
            "tier": tier,
            "model": model,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "cache_hit_tokens": cht,
            "peak": is_peak(now),
            "est_cost_usd": estimate_cost(model, pt, ct, cht, now),
            "caller": caller,
        }
        DATA_DIR.mkdir(exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # ledger must never break a completion


def cache_hit_rate(days: int = 7) -> dict:
    """Aggregate provider prefix-cache hit rate from the ledger (L3).

    Returns {"prompt_tokens", "cache_hit_tokens", "hit_rate"} over the last
    `days` days. 0/0 -> hit_rate 0. Never raises (empty ledger -> zeros).
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        pt = ct_hit = 0
        if LEDGER.exists():
            for line in LEDGER.read_text(encoding="utf-8").splitlines():
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if datetime.fromisoformat(e.get("ts", "")).replace(tzinfo=timezone.utc) < cutoff:
                    continue
                pt += int(e.get("prompt_tokens", 0) or 0)
                ct_hit += int(e.get("cache_hit_tokens", 0) or 0)
        rate = (ct_hit / pt) if pt else 0.0
        return {"prompt_tokens": pt, "cache_hit_tokens": ct_hit, "hit_rate": round(rate, 4)}
    except Exception:
        return {"prompt_tokens": 0, "cache_hit_tokens": 0, "hit_rate": 0.0}


if __name__ == "__main__":
    # Self-test: window classification + rate math (no network).
    for h, expect in [(0, False), (2, True), (5, False), (8, True), (12, False)]:
        got = is_peak(datetime(2026, 8, 16, h, tzinfo=timezone.utc))
        assert got is expect, f"hour {h}: got {got}, want {expect}"
    off = estimate_cost("deepseek-v4-flash", 1_000_000, 100_000,
                        dt=datetime(2026, 8, 16, 12, tzinfo=timezone.utc))
    assert abs(off - (0.22 + 0.066)) < 1e-6, off
    peak = estimate_cost("deepseek-v4-flash", 1_000_000, 100_000,
                         dt=datetime(2026, 8, 16, 2, tzinfo=timezone.utc))
    assert abs(peak - (0.44 + 0.132)) < 1e-6, peak
    hit = estimate_cost("deepseek-v4-pro", 1_000_000, 0, cache_hit_tokens=1_000_000,
                        dt=datetime(2026, 8, 16, 12, tzinfo=timezone.utc))
    assert abs(hit - 0.66 / 30) < 1e-6, hit
    print("cost.py self-test OK: peak windows, off-peak/peak rates, cache-hit discount")
