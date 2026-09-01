#!/usr/bin/env python3
"""Benchmark any OpenAI-compatible local endpoint: TTFT, decode tok/s, VRAM.

Written for the Colibri evaluation (docs/COLIBRI_PLAN.md), but provider-
agnostic on purpose: point it at Ollama today to capture a BASELINE, then at
Colibri after install, and compare like for like.

Usage:
    # baseline against the Ollama tier already in the router
    python scripts/bench_local_llm.py --tier local

    # after Colibri is installed and COLIBRI_BASE_URL is set
    python scripts/bench_local_llm.py --tier batch-local

    # explicit endpoint, no router involvement
    python scripts/bench_local_llm.py --base-url http://localhost:8080/v1 \
        --model deepseek-v4-flash

    # the Phase 2 protocol from the plan, in one shot
    python scripts/bench_local_llm.py --tier batch-local --sustained 10 --long-context

What it reports
---------------
  TTFT           time to first token (prefill cost)
  decode tok/s   completion_tokens / (total - ttft)   <- the number that matters
  peak VRAM      sampled from nvidia-smi during the call
  run-over-run   sustained mode shows drift; on a DRAM-less NVMe (SN770) a
                 falling tok/s across runs means the SLC cache is saturating,
                 which a single hot run would have hidden

Exit code is 0 even on a slow result — this measures, it does not judge.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents"))

# Short prompt: measures decode with negligible prefill.
SHORT_PROMPT = "Write a plain-English explanation of what a hash map is."
# Long prompt: streaming inference cost scales with context, so this is the
# case that actually distinguishes an NVMe-streaming engine from a resident one.
LONG_FILLER = (
    "The quick brown fox jumps over the lazy dog near the riverbank at dawn. "
)


class VramSampler(threading.Thread):
    """Poll nvidia-smi for used VRAM while a call is in flight."""

    def __init__(self, interval: float = 0.25) -> None:
        super().__init__(daemon=True)
        self.interval = interval
        self.samples: list[int] = []
        self._halt = threading.Event()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=memory.used",
                     "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                if out.returncode == 0:
                    self.samples.append(int(out.stdout.strip().splitlines()[0]))
            except Exception:
                pass  # no GPU, or nvidia-smi busy — VRAM is a nice-to-have
            self._halt.wait(self.interval)

    def stop(self) -> int | None:
        self._halt.set()
        self.join(timeout=5)
        return max(self.samples) if self.samples else None


def build_client(args) -> tuple[object, str, str]:
    """Return (client, model, label) from either --tier or explicit flags."""
    if args.base_url:
        from openai import OpenAI
        model = args.model or "unknown"
        return OpenAI(api_key=args.api_key, base_url=args.base_url), model, args.base_url
    from _shared.llm import TIERS, get_client  # noqa: PLC0415 — needs sys.path above
    if args.tier not in TIERS:
        sys.exit(f"unknown tier {args.tier!r} — use {sorted(TIERS)}")
    cfg = TIERS[args.tier]
    return get_client(args.tier), args.model or cfg["model"], cfg.get("base_url", "")


def one_run(client, model: str, prompt: str, max_tokens: int,
            sample_vram: bool) -> dict:
    """One streamed completion. Streaming is required to separate TTFT from decode."""
    sampler = VramSampler() if sample_vram else None
    if sampler:
        sampler.start()

    t0 = time.perf_counter()
    ttft: float | None = None
    chunks = 0
    text_parts: list[str] = []
    usage = None
    err = None
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None)
            # Reasoning models (qwen3, deepseek-r1) emit thinking tokens FIRST,
            # in a separate field. Those are generated tokens too: counting only
            # `content` puts every thinking token inside the "prefill" window and
            # inflates decode tok/s by an order of magnitude.
            think = getattr(delta, "reasoning_content", None) or getattr(
                delta, "reasoning", None)
            if piece or think:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                chunks += 1
                if piece:
                    text_parts.append(piece)
    except TypeError:
        # Some servers reject stream_options — retry without it.
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0, max_tokens=max_tokens, stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
                think = getattr(delta, "reasoning_content", None) or getattr(
                    delta, "reasoning", None)
                if piece or think:
                    if ttft is None:
                        ttft = time.perf_counter() - t0
                    chunks += 1
                    if piece:
                        text_parts.append(piece)
        except Exception as e:  # noqa: BLE001
            err = repr(e)
    except Exception as e:  # noqa: BLE001
        err = repr(e)

    total = time.perf_counter() - t0
    peak_vram = sampler.stop() if sampler else None

    text = "".join(text_parts)
    # Prefer server-reported token counts; fall back to stream chunks, which
    # approximate tokens 1:1 on most OpenAI-compatible servers.
    out_tokens = getattr(usage, "completion_tokens", None) or chunks
    in_tokens = getattr(usage, "prompt_tokens", None)
    decode_window = max(total - (ttft or 0.0), 1e-9)

    return {
        "ok": err is None and out_tokens > 0,
        "error": err,
        "ttft_s": round(ttft, 3) if ttft is not None else None,
        "total_s": round(total, 3),
        "prompt_tokens": in_tokens,
        "completion_tokens": out_tokens,
        "decode_tok_s": round(out_tokens / decode_window, 2),
        "overall_tok_s": round(out_tokens / max(total, 1e-9), 2),
        "peak_vram_mib": peak_vram,
        "preview": text[:120].replace("\n", " "),
    }


def fmt(run: dict) -> str:
    if not run["ok"]:
        return f"    FAILED: {run['error']}"
    vram = f"{run['peak_vram_mib']} MiB" if run["peak_vram_mib"] else "n/a"
    return (f"    ttft {run['ttft_s']}s | {run['completion_tokens']} tok in "
            f"{run['total_s']}s | decode {run['decode_tok_s']} tok/s | "
            f"peak VRAM {vram}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tier", default="local",
                   help="router tier from _shared.llm.TIERS (default: local)")
    p.add_argument("--base-url", default="", help="bypass the router entirely")
    p.add_argument("--api-key", default="local", help="only used with --base-url")
    p.add_argument("--model", default="", help="override the tier's model")
    p.add_argument("--max-tokens", type=int, default=256,
                   help="output cap per run (default 256; raise for a realistic "
                        "agent-shaped call, ~500-1500)")
    p.add_argument("--sustained", type=int, default=3,
                   help="consecutive runs (default 3; use 10 for the Phase 2 "
                        "SLC-cache falloff check)")
    p.add_argument("--long-context", action="store_true",
                   help="add a ~4k-token prefix run — the case that separates "
                        "NVMe streaming from a resident model")
    p.add_argument("--no-vram", action="store_true", help="skip nvidia-smi sampling")
    p.add_argument("--json", dest="json_out", default="",
                   help="also write raw results to this path")
    args = p.parse_args()

    client, model, endpoint = build_client(args)
    label = args.tier if not args.base_url else "explicit"

    print(f"== bench {label} | model={model} | {endpoint or 'n/a'} ==")
    print(f"   max_tokens={args.max_tokens} runs={args.sustained}"
          f"{' +long-context' if args.long_context else ''}")
    print()

    results: dict[str, list[dict]] = {"short": [], "long": []}

    print(f"-- short prompt x{args.sustained} (first run is the cold one) --")
    for i in range(args.sustained):
        r = one_run(client, model, SHORT_PROMPT, args.max_tokens, not args.no_vram)
        results["short"].append(r)
        print(f"  run {i + 1}:")
        print(fmt(r))
        if not r["ok"]:
            break

    if args.long_context:
        # ~4k tokens of filler. Deliberately repetitive: this measures the
        # transport, not the model's reasoning.
        long_prompt = (LONG_FILLER * 300) + "\n\nSummarize the passage above in one sentence."
        print(f"\n-- long context (~4k tok prefix) x{max(1, args.sustained // 3)} --")
        for i in range(max(1, args.sustained // 3)):
            r = one_run(client, model, long_prompt, args.max_tokens, not args.no_vram)
            results["long"].append(r)
            print(f"  run {i + 1}:")
            print(fmt(r))
            if not r["ok"]:
                break

    print("\n== verdict ==")
    ok_short = [r for r in results["short"] if r["ok"]]
    if not ok_short:
        print("  NO SUCCESSFUL RUNS — endpoint unreachable or not OpenAI-compatible.")
        return 0

    speeds = [r["decode_tok_s"] for r in ok_short]
    median = statistics.median(speeds)
    print(f"  decode tok/s: first={speeds[0]} median={median} "
          f"min={min(speeds)} max={max(speeds)}")

    # Drift across runs is the SN770 DRAM-less signal called out in the plan.
    # Run 1 is the cold-load run and is excluded — otherwise the warm-up
    # speed-up swamps the slow degradation this check is looking for.
    if len(speeds) >= 4:
        warm = speeds[1:]
        drift = (warm[-1] - warm[0]) / max(warm[0], 1e-9) * 100
        print(f"  drift across warm runs (2..{len(speeds)}): {drift:+.1f}%")
        if drift < -20:
            print("  NOTE: >20% slowdown across runs — consistent with SLC-cache")
            print("        saturation on a DRAM-less NVMe. Re-run after idle to confirm.")

    # Translate tok/s into the units the routing decision is actually made in.
    for out_len in (500, 1500):
        secs = out_len / max(median, 1e-9)
        print(f"  a {out_len}-token agent reply would take {secs / 60:.1f} min "
              f"at the median rate")
    if median < 1.5:
        print("  GATE: below the 1.5 tok/s Phase 2 floor — batch-only at best.")
    elif median < 10:
        print("  GATE: usable for batch/offline work; not for interactive agents.")
    else:
        print("  GATE: fast enough to consider for interactive tiers.")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"tier": label, "model": model, "endpoint": endpoint,
                        "max_tokens": args.max_tokens, "results": results},
                       indent=2), encoding="utf-8")
        print(f"\n  raw results -> {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
