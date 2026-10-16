# Testing - Jurassic Park

## What exists

**No automated test suite** (no `tests/`, no `test_*.py`, no CI workflow). Verification is
manual and described in `GUIDE_LOCAL.md` section 5-6 (import sanity, `--help` wiring check,
two end-to-end smoke runs, failover check). Those commands need `<repo>/.venv`, which does
**not exist in this checkout**, so they could not be run.

## Commands verified on 2026-10-15

| Command | Result |
|---|---|
| `python -X utf8 -c "<ast.parse every git ls-files *.py>"` (system Python 3.12.10) | 36 files parsed, 0 failures |
| `python -X utf8 scripts/cost_report.py 7` (reads `data/cost_ledger.jsonl` only) | ran; final line `COST_REPORT calls=632 est_usd=1.097859 peak_calls=168 days=7` |

`git status` was unchanged by both.

## Commands deliberately not run

- `docs/generate_site.py` - writes `docs/data.js`, then `git add -A`, commit, **push**.
- `scripts/eval_tiers.py` - sends real requests to every tier (paid DeepSeek, free cloud
  relays, local LM Studio) and overwrites `data/eval_results.json`.
- `scripts/bench_local_llm.py` - drives the local GPU.
- Any `agents/*/agent.py` run - real LLM calls; needs the missing `.venv`.

## Gaps and risks found

- No unit tests for the shared runtime, even though it carries testable pure logic:
  `tier_of()`, `_FALLBACK` ordering, `cache.exact_key()`, `cost.estimate_cost()` / `is_peak()`,
  `supervisor.check()`, `breaker.CircuitBreaker` state transitions,
  `prompts.dynamic_tail()`, `generate_site.scrub()`.
- `agents/06-news-summarizer-agent/agent.py::fetch_news()` returns **three invented articles**
  ("Return mock data if no API key") when `NEWS_API_KEY` is unset, and the agent then
  summarises them as news. This contradicts the fleet's "never fabricate" rule
  (`data_collector.py` docstring) and would not be caught without a test.
- The documented local tier in `GUIDE_LOCAL.md` (Ollama `qwen3:8b`) no longer matches the code
  (LM Studio `qwen/qwen3.5-9b`), so following the guide's `--env` example targets a retired
  server.

## Verified against

`git ls-files` (no tests), `GUIDE_LOCAL.md`, `scripts/cost_report.py`, `scripts/eval_tiers.py`
header, `agents/06-news-summarizer-agent/agent.py` lines 27-40, commands above (executed).
