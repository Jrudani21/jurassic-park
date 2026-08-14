---
title: "Jurassic Park — Local Operators Guide"
schema_version: 1
repo: "local runtime (private)"
origin: "https://github.com/Jrudani21/jurassic-park (our own, not a fork)"
last_verified: 2026-08-13
audience: "bots, review agents, QA crews, subagents, humans"
intent: "Run, verify, and review every agent deterministically. Machine-parseable: tables, stable anchors, exact commands, exit codes."
---

# LOCAL OPERATORS GUIDE - Jurassic Park

> Written for ALL consumers (bots included). Stable anchors are `## agent-<id>`.
> Every command is exact and runnable. Exit codes are the contract.
> Interpreter rule: **always** `<repo>/.venv/Scripts/python.exe` (py3.12).
> Hermes/other shells inject a py3.11 venv via PYTHONPATH — strip it:
> `env -u PYTHONPATH -u VIRTUAL_ENV -u PYTHONHOME` (PYTHONPATH alone is NOT enough).

---

## 1. INVOCATION (two supported paths)

| Path | Command | When |
|---|---|---|
| Direct (repo) | `env -u PYTHONPATH -u VIRTUAL_ENV -u PYTHONHOME .venv/Scripts/python.exe agents/<dir>/agent.py <args>` | CLI / scripts / review |
| Via KEN fleet | `python qa/run_500agent.py <agent-dir> [args...] [--env K=V ...]` (cwd = the assistant app, private) | fleet bots; logs -> the assistant app data dir |

`--env` forwards vars (e.g. local tier forces Ollama:
`--env DEEPSEEK_API_BASE=http://localhost:11434/v1 DEEPSEEK_MODEL=qwen3:8b`).

## 2. EXIT-CODE CONTRACT

| Code | Meaning | Bot action |
|---|---|---|
| 0 | success (output valid, may be empty) | use output |
| 1 | agent-level failure (bad input / API error / no data) | read stderr, retry once, else escalate |
| 2 | usage error (bad args) | fix invocation, don't retry agent |

## 3. AGENT SPEC MATRIX

| Agent | Args (required = **bold**) | Tier | Framework | Output |
|---|---|---|---|---|
| 01-web-research | **--query**, --tier, --limit | flash | langchain | text summary |
| 02-code-review | --file / --code, --language | flash | langchain | review text |
| 03-pdf-qa | **--pdf**, --question | flash | llama_index | answer text |
| 04-sql-query | --db, --question, --allow-write | flash | langchain | SQL + result |
| 05-email-drafting | --context, --tone, --recipient | flash | crewai | email draft |
| 06-news-summarizer | --topic, --count | **local** | langchain | digest |
| 07-github-issue-triager | (uses gh) | flash | langchain | labels/severity |
| 08-data-analysis | **--file**, --question | **pro** | langchain | analysis |
| 09-resume-parser | --resume, --job-desc | **local** | langchain | structured profile |
| 10-meeting-notes | --transcript / --text, --output | **local** | langchain | notes+actions |
| 11-stock-research | --ticker | **pro** | agno | analysis |
| 12-travel-planner | --destination, --days, --budget, --interests | **local** | crewai | itinerary |
| 13-customer-support | --kb-dir, --query | flash | langgraph | answer |
| 14-social-media | --topic, --brand, --platforms | **local** | crewai | post templates |
| 15-unit-test-generator | (reads file) | flash | langchain | pytest file |
| 16-documentation-writer | (reads repo) | flash | langchain | docs |
| 17-recipe | --ingredients, --diet, --time, --servings | **local** | langchain | recipe |
| 18-job-application | --job-desc, --candidate | flash | crewai | cover letter |
| 19-competitive-analysis | --company, --industry | flash | langchain | deep-dive |
| 20-multi-agent-debate | (topic arg) | **pro** | langchain | debate |
| 21-pii-sanitization | --text / --file, --context, --tx-hash, --local | **none** (deterministic) | requests | redacted text |
| 22-vault-rag | --query, --top-k, --no-llm, --local | flash | st+faiss | RAG answer |

**Tier map (ROUTING.md):** local = Ollama qwen3:8b ($0) · free = Bluesminds 70b
($0, 600/day) · openrouter = nemotron-3-super-120b:free · groq = llama-3.3-70b
(fixed 2026-08-13, UA) · flash = deepseek-v4-flash · pro = deepseek-v4-pro.
Failover: `pro→flash→openrouter→groq→free→local` (`_shared/llm.py chat()`).

## 4. SHARED INFRA (`agents/_shared/`)

| Module | Purpose |
|---|---|
| `llm.py` | tiered client `chat(tier)`, `get_client(tier)`, `tier_of(kind)`, `frontier`→Claude |
| `cache.py` | SQLite L1 exact (sha256, 24h) + L2 semantic (MiniLM ≥0.93, 7d) + L3 prompt |
| `supervisor.py` | weak-tier failure heuristics (empty/gibberish/loop/refusal) |
| `data_collector.py` | free keyless data (Reddit JSON, HN Algolia, RSS, web) |

Keys: `_key()` = env → optional extra env file (`FLEET_ENV_FILE`) → repo `.env`.
Embeddings ALWAYS local MiniLM. **PII never leaves local** (21-pii is
deterministic, no model).

## 5. VERIFICATION (for review bots)

```bash
# import sanity (all frameworks present)
env -u PYTHONPATH -u VIRTUAL_ENV -u PYTHONHOME .venv/Scripts/python.exe -c \
  "import langchain, langgraph, crewai, llama_index, yfinance, faiss, pandas; print('all imports OK')"
# dry-run one agent (usage error expected: exit 2 = wiring OK)
env -u PYTHONPATH -u VIRTUAL_ENV -u PYTHONHOME .venv/Scripts/python.exe agents/22-vault-rag-agent/agent.py --help
# config sanity
git status --short && git remote -v   # expect origin=Jrudani21, NO upstream
```

## 6. REVIEW PROTOCOL (bots: run in this order)

1. **Wiring** — §5 import check + one `--help` → exit 2 (not 1/0) means argparse wired.
2. **Tier config** — each agent's `tier` matches ROUTING.md (check `agents/*/requirements.txt` framework line, not just the map).
3. **PII rule** — agent 21 deterministic, no LLM; nothing PII-adjacent on a cloud tier.
4. **Data** — `_shared/data_collector.py` keyless; verify no hardcoded creds (grep `sk-|gsk_|BEGIN PRIVATE`).
5. **Behavior smoke** — run 2 agents end-to-end (e.g. 06 local-tier, 22 RAG) → exit 0 + non-empty output.
6. **Failover** — kill deepseek reachability; `chat("pro")` must fall through to a free/local tier, never raise (exception-based, skip rungs).
7. **Report** — per-agent verdict table + any deviation → log to `data/agents/review-<ts>.md`.

## 7. PITFALLS (bot reminders)

- `env -u PYTHONPATH` ALONE breaks py3.12 (Hermes 3.11 venv leaks pydantic_core) — use the full `-u` triple or the repo `.venv` directly.
- Groq needs browser UA (Cloudflare error-1010) — already in `llm.py get_client()`.
- Don't `git add -A` — repo `.env` is gitignored but present; stage explicit paths.
- New agent? Add it to `agents/`, ROUTING.md tier map, fleet `bots.json` tier, and this matrix (row + verify).
- Exit 2 = usage error → fix invocation, never retry the agent.

## 8. LINKS

- Routing/tiers: `ROUTING.md` · frameworks: `agents/*/requirements.txt`
- Zero-token error runbook: the brain vault runbook (private)
- Fleet side: the assistant app qa/ dir (private)
- Domino checks before commit: the domino-check skill (assistant app)

---
*End of guide. All anchors stable; bot consumers may reference `## agent-<id>`.*
