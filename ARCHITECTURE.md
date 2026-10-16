# Architecture - Jurassic Park

## Layout

```
agents/NN-<name>/agent.py     22 CLI agents (argparse; exit 0 ok / 1 agent failure / 2 usage)
agents/NN-<name>/requirements.txt, metadata.yaml, .env.example, README.md   (01-21)
agents/_shared/               shared runtime, imported via sys.path insert ("from _shared import llm")
  llm.py          tiered OpenAI-compatible client: chat(), get_client(), tier_of(); failover
  cache.py        L1 exact + L2 semantic response cache (SQLite)
  tool_cache.py   tool/API result cache (SQLite, per-source TTL)
  cost.py         usage/cost ledger (JSONL), DeepSeek peak/off-peak pricing
  breaker.py      per-provider circuit breaker; guardrail event log (JSONL)
  supervisor.py   zero-token heuristics for weak-tier output; optional escalation
  prompts.py      stable per-kind system prompts + dynamic tail (prefix-cache friendly)
  brain_client.py BM25 + embedding retrieval over the Obsidian vault
  data_collector.py keyless fetchers: Reddit JSON, HN Algolia, RSS, web
  run_clean.py    re-exec a script with PYTHONPATH/VIRTUAL_ENV/PYTHONHOME stripped
scripts/          cost_report.py, eval_tiers.py, bench_local_llm.py, star-history.mjs,
                  colibri-idle-runner.ps1, install-idle-tasks.ps1
docs/             static dashboard + generate_site.py (GitHub Pages)
data/             runtime output, gitignored
```

## LLM request flow (`agents/_shared/llm.py`)

1. Caller picks a tier directly or via `tier_of(task_kind)` (local kinds: summarize, extract,
   template, recipe, classify, travel, draft; pro kinds: analysis, reasoning, debate,
   financial; frontier kinds: deep-analysis, hard-reasoning, ...; default flash).
2. `chat()` checks the cache (`cache.py`), then walks `_FALLBACK[tier]`, e.g.
   `pro -> flash -> openrouter -> groq -> nvidia -> free -> local`. Each provider is gated by
   `breaker.py` (open providers are skipped); breaker open/close transitions and supervisor
   interventions are appended to `data/guardrail_events.jsonl`.
3. Weak-tier output is checked by `supervisor.py` (L1 rules; L2 escalation only if
   `LLM_SUPERVISOR=1`).
4. Billed calls are appended to `data/cost_ledger.jsonl` by `cost.py`.

Tiers and code defaults (`TIERS` in `llm.py`): `local` = LM Studio at `127.0.0.1:1234`,
`qwen/qwen3.5-9b`; `batch-local` = Colibri (`COLIBRI_BASE_URL`, unset = disabled, see
`docs/COLIBRI_PLAN.md`); `free` = Bluesminds; `openrouter`; `groq`; `nvidia` (NIM);
`flash` / `pro` = DeepSeek; `frontier` = Claude via the Claude Code OAuth token, falling back
to the Hermes CLI. Note: `llm.py`'s module docstring and `GUIDE_LOCAL.md` still describe
`local` as Ollama `qwen3:8b`; the `TIERS` table (and a comment saying Ollama was retired
2026-09-14) is current. `brain_client.py` still defaults to Ollama (`OLLAMA_BASE_URL`,
`localhost:11434`).

Frameworks per agent (`ROUTING.md`): LangChain/LangGraph (most), LlamaIndex (03), CrewAI
(05, 12, 14, 18), none (21, 22). Agents point the framework's OpenAI client at the tier's
base URL via `DEEPSEEK_API_BASE` / `DEEPSEEK_MODEL`.

## Invocation

- Direct: `<repo>/.venv/Scripts/python.exe agents/<dir>/agent.py <args>` with the env triple
  stripped (`GUIDE_LOCAL.md` section 1). No `.venv` exists in this checkout today.
- Via the private assistant app: `python qa/run_500agent.py <agent-dir> [args] [--env K=V]`.

## Dashboard

`docs/generate_site.py` reads five source paths from env vars (`FLEET_SITE_DIR`,
`FLEET_BOTS_JSON`, `FLEET_LEDGER`, `FLEET_CACHE_DB`, `FLEET_STATE`, optional
`FLEET_GUARDRAIL_LOG`), scrubs local paths and private repo names, writes `docs/data.js`,
then `git add -A` + commit + push when anything changed. Scheduler: "nightly via cron"
(`README.md`); exact job Unknown - needs owner input.

## External services

DeepSeek, OpenRouter, Groq, NVIDIA NIM, Bluesminds, Anthropic (frontier), Tavily (agent 01),
GitHub (`gh` for agent 07), yfinance (agent 11), Reddit/HN/RSS (keyless), LM Studio (local).

## Verified against

`agents/_shared/*.py` (headers, `TIERS`, `_FALLBACK`, `tier_of`, `_claude_oauth_token`),
`ROUTING.md`, `GUIDE_LOCAL.md`, `grep "from _shared" agents/*/agent.py`,
`docs/generate_site.py`, `git ls-files`.
