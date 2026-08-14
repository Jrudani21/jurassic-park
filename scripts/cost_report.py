#!/usr/bin/env python3
"""Summarize data/cost_ledger.jsonl — per-day / per-tier / per-model totals.

Usage: python scripts/cost_report.py [days]
Stable verdict line for cron/monitoring (no timestamps):
    COST_REPORT calls=<n> est_usd=<total> peak_calls=<n> days=<n>
"""
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LEDGER = Path(__file__).resolve().parents[1] / "data" / "cost_ledger.jsonl"


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    by_day = defaultdict(lambda: [0, 0.0, 0])      # calls, usd, peak_calls
    by_tier = defaultdict(lambda: [0, 0.0])
    by_model = defaultdict(lambda: [0, 0.0])
    total_calls = total_usd = total_peak = 0

    if LEDGER.exists():
        with LEDGER.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = datetime.fromisoformat(e["ts"])
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
                if ts < cutoff:
                    continue
                usd = float(e.get("est_cost_usd", 0.0))
                peak = bool(e.get("peak", False))
                day = ts.date().isoformat()
                by_day[day][0] += 1
                by_day[day][1] += usd
                by_day[day][2] += 1 if peak else 0
                by_tier[e.get("tier", "?")][0] += 1
                by_tier[e.get("tier", "?")][1] += usd
                by_model[e.get("model", "?")][0] += 1
                by_model[e.get("model", "?")][1] += usd
                total_calls += 1
                total_usd += usd
                total_peak += 1 if peak else 0

    print(f"== COST LEDGER (last {days}d) — {LEDGER.parent} ==")
    print(f"{'day':<12} {'calls':>6} {'peak':>5} {'est USD':>12}")
    for day in sorted(by_day):
        c, u, p = by_day[day]
        print(f"{day:<12} {c:>6} {p:>5} {u:>12.6f}")
    print(f"{'TOTAL':<12} {total_calls:>6} {total_peak:>5} {total_usd:>12.6f}")
    print("by tier:")
    for tier, (c, u) in sorted(by_tier.items(), key=lambda kv: -kv[1][1]):
        print(f"  {tier:<12} {c:>5} calls  ${u:.6f}")
    print("by model:")
    for model, (c, u) in sorted(by_model.items(), key=lambda kv: -kv[1][1]):
        print(f"  {model:<32} {c:>5} calls  ${u:.6f}")
    print(f"\nCOST_REPORT calls={total_calls} est_usd={total_usd:.6f} "
          f"peak_calls={total_peak} days={days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
