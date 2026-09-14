#!/usr/bin/env python3
"""Eval harness: run a fixed question set through each of the 7 LLM tiers,
score correctness (keyword match) and latency. No fallback per tier — patches
llm._FALLBACK so tier=X hits only X, not X's whole chain.

Usage: python scripts/eval_tiers.py [tier ...]   (default: all 7 tiers)
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
from _shared import llm  # noqa: E402

TIERS = ["pro", "flash", "openrouter", "groq", "nvidia", "free", "local"]

CASES = [
    {"q": "What is 17 * 24? Answer with just the number.", "expect": ["408"]},
    {"q": "Name the capital of Canada. One word.", "expect": ["ottawa"]},
    {"q": "In Python, what keyword defines a function?", "expect": ["def"]},
    {"q": "Reverse the string 'cat'. Just the result.", "expect": ["tac"]},
    {"q": "Is 7 a prime number? Answer yes or no.", "expect": ["yes"]},
]


def run_case(tier: str, case: dict) -> dict:
    t0 = time.monotonic()
    try:
        content, used = llm.chat(tier, case["q"], cache=False, max_tokens=1024)
        elapsed = time.monotonic() - t0
        low = content.lower()
        hit = any(e in low for e in case["expect"])
        return {"ok": True, "used_tier": used, "elapsed_s": round(elapsed, 2),
                "correct": hit, "response": content[:200]}
    except Exception as e:
        return {"ok": False, "used_tier": None, "elapsed_s": round(time.monotonic() - t0, 2),
                "correct": False, "error": str(e)}


def main():
    tiers = sys.argv[1:] or TIERS
    results = {}
    for tier in tiers:
        orig = llm._FALLBACK.get(tier)
        llm._FALLBACK[tier] = [tier]  # no fallback, this tier only
        try:
            cases = [run_case(tier, c) for c in CASES]
        finally:
            if orig is not None:
                llm._FALLBACK[tier] = orig
        n_ok = sum(1 for c in cases if c["ok"])
        n_correct = sum(1 for c in cases if c["correct"])
        avg_latency = round(sum(c["elapsed_s"] for c in cases) / len(cases), 2)
        results[tier] = {"cases": cases, "reachable": n_ok, "correct": n_correct,
                          "total": len(cases), "avg_latency_s": avg_latency}
        print(f"{tier:12s} reachable={n_ok}/{len(cases)} correct={n_correct}/{len(cases)} "
              f"avg_latency={avg_latency}s")

    out_path = Path(__file__).resolve().parent.parent / "data" / "eval_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
