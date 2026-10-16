# Data stores - Jurassic Park

No server database. State is local SQLite and JSON Lines files written by `agents/_shared/`,
all gitignored (`data/`, `agents/_shared/.llm_cache/`).

## SQLite

**`agents/_shared/.llm_cache/llm_cache.sqlite`** (`cache.py`; dir overridable with
`LLM_CACHE_DIR`; WAL mode, `synchronous=NORMAL`, shared by concurrent agent processes)

| Table | Columns | Notes |
|---|---|---|
| `exact` | `key TEXT PK`, `tier`, `model`, `response`, `ts REAL` | key = sha256 of tier+model+messages+params; TTL `LLM_CACHE_TTL_S` (24h) |
| `semantic` | `id INTEGER PK AUTOINCREMENT`, `model_family`, `system`, `prompt`, `response`, `embedding BLOB`, `ts` | MiniLM cosine >= `LLM_SEMANTIC_THRESHOLD` (0.93); TTL 7d; off with `LLM_SEMANTIC_CACHE=0` |
| `stats` | `name TEXT PK`, `value INTEGER` | hit/miss counters |

Indexes: `idx_exact_ts`, `idx_semantic_fam_ts`. Only successful completions are cached.

**`agents/_shared/.llm_cache/tool_cache.sqlite`** (`tool_cache.py`): table `tool_cache`
(`key TEXT PK`, `tool`, `result`, `summary`, `ts REAL`), index `idx_tool_ts(tool, ts)`.

## JSON Lines / JSON (`data/`)

| File | Writer | Record |
|---|---|---|
| `cost_ledger.jsonl` | `cost.record_usage()` | `ts`, `tier`, `model`, `prompt_tokens`, `completion_tokens`, `cache_hit_tokens`, `peak`, `est_cost_usd`, `caller` |
| `guardrail_events.jsonl` | `breaker.log_guardrail_event()` | `ts`, `source`, `kind`, optional `provider`, `detail`, extras |
| `eval_results.json` | `scripts/eval_tiers.py` | per-tier correctness/latency |
| `bench_*.json` | `scripts/bench_local_llm.py --json-out <path>` (path chosen by caller) | local-model benchmarks |

Both writers append and never raise. `scripts/cost_report.py [days]` summarises the ledger.

## Other state

- `brain_client.py` keeps its vault index in process memory only (re-sync at most every 5 min);
  it can read an existing embeddings store at `ASSISTANT_STORE` (default
  `~/.cache/ken/embeddings.json`).
- `docs/data.js` - generated, committed snapshot for the dashboard (shape as in the
  `ken-fleet-site` repo's DATABASE.md, plus scrubbing).

## Observed inconsistency

`data/llm_cache.sqlite` exists but has **no tables**, while the live cache is
`agents/_shared/.llm_cache/llm_cache.sqlite` (1 exact, 19 semantic rows on 2026-10-15). If
`FLEET_CACHE_DB` points at `data/llm_cache.sqlite`, the dashboard's cache stats will be empty.
Its actual value is Unknown - needs owner input.

## Verified against

`CREATE TABLE` statements in `agents/_shared/cache.py` and `tool_cache.py`,
`cost.record_usage`, `breaker.log_guardrail_event`, `brain_client.py` constants,
`.gitignore`, read-only `sqlite3` (`mode=ro`) table counts of the three `.sqlite` files.
