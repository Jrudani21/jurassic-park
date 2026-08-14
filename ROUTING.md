# Agent Fleet Routing & Tooling Map (Hybrid Local + Cloud)

Operating manual for the whole corps: which model tier each agent runs on,
which framework it uses, and how to switch tiers. Research-backed (2026-08).

## The hybrid rule

> **Local for cheap/mechanical, flash for default quality, pro for deep
> reasoning — and everything falls back downward on failure.**

Tiers (see `agents/_shared/llm.py` — the shared client ALL new agents use):

| Tier   | Provider              | Cost      | Task kinds                              |
|--------|-----------------------|-----------|------------------------------------------|
| local  | Ollama `qwen3:8b`     | **$0**    | summarize, extract, template, recipe, classify, travel, draft |
| free   | Bluesminds relay      | **$0**    | cloud fallback (llama-3.1-70b verified working) |
| openrouter | OpenRouter `:free` | **$0**    | cloud fallback (nemotron-3-super-120b verified) |
| groq   | Groq free tier        | **$0**    | fast cloud fallback (llama-3.3-70b verified) |
| nvidia | NVIDIA NIM free       | **$0**    | cloud fallback (llama-3.3-70b / 8b, verified 2026-08-14) |
| flash  | DeepSeek v4-flash     | ~$0.14/M  | default quality work (most agents)       |
| pro    | DeepSeek v4-pro       | ~$0.43/M  | analysis, reasoning, debate, financial   |

- **Failover:** pro → flash → **openrouter → groq → nvidia → free** → local. A pro call
  that fails still answers, on flash, then four free cloud relays, then
  local — instead of erroring. (`_shared.llm.chat()` does this.)
- **Free cloud tiers (all probe-verified 2026-08-13/14):**
  - `free` (Bluesminds): `meta/llama-3.1-70b-instruct`, 600 req/day cap.
  - `openrouter`: `nvidia/nemotron-3-super-120b-a12b:free` (120B MoE, $0).
  - `groq`: `llama-3.3-70b-versatile` (fastest of the three, free tier limits).
  - `nvidia` (NIM): `meta/llama-3.1-8b-instruct` (default — always warm,
    ~0.4s TTFT; `NVIDIA_MODEL` override for e.g. `meta/llama-3.3-70b-instruct`).
    ⚠️ **70b cold-starts 4-10 min when unloaded** (free tier unloads after
    idle, queue contention) — stick with 8b for fleet use; circuit breaker
    + agent timeouts handle the rest; supervisor treats it as free.
  Keys in repo `.env` (gitignored): `BLUESMINDS_API_KEY`, `OPENROUTER_API_KEY`,
  `GROQ_API_KEY`, `NVIDIA_API_KEY`. SambaNova key exists but has 0 balance — don't use.
- **Embeddings are ALWAYS local** (sentence-transformers MiniLM) — never billed.
- **Sensitivity rule:** PII never leaves local. `21-pii` is deterministic
  regex (no LLM at all); anything PII-adjacent stays on tier local.
- **Advisor pattern** (biggest token saver): let local draft, flash review.
  E.g. `brain-qa --local` drafts from your vault, flash refines when needed.

## Per-agent tier map (22 agents)

### LOCAL — zero tokens (template / extraction / mechanical)
| Agent | Bot | What |
|---|---|---|
| 06-news-summarizer | `news-digest` | short daily digest |
| 09-resume-parser | `career-parser` | CV → structured profile |
| 10-meeting-notes | `meeting-scribe` | transcript → notes + action items |
| 14-social-media | `career-brand` | LinkedIn post templates |
| 12-travel-planner | (not in bots.json) | itinerary templates |
| 17-recipe | (not in bots.json) | recipe generation |
| 21-pii | `career-pii` | deterministic regex, no LLM (tier: none) |

### FLASH — default quality (12 bots)
01 web-research (`web-researcher`) · 02 code-review (`code-reviewer`) ·
03 pdf-qa (`doc-qa`) · 04 sql-query (`sql-agent`) · 05 email-drafting
(`career-outreach`) · 07 github-issue-triager (`issue-triager`) ·
13 customer-support (`kb-agent`) · 15 unit-test-generator (`test-writer`) ·
16 documentation-writer (`doc-writer`) · 18 job-application
(`career-applier`) · 19 competitive-analysis (`career-researcher`) ·
22 vault-rag (`brain-qa`)

### PRO — deep reasoning (3 bots)
08 data-analysis (`data-analyst`) · 11 stock-research (`market-watch`) ·
20 multi-agent-debate (`arb-debate`)

## Frameworks in use (per-agent requirements.txt)

- **langchain + langgraph** (11 agents): 01, 02, 04, 06, 07, 08, 09, 10, 11,
  13, 15, 16, 17, 19, 20 — ChatOpenAI pointed at DeepSeek; 13 adds FAISS RAG.
- **llama_index** (1): 03 — OpenAI LLM + embeddings pointed at DeepSeek.
- **crewai** (4): 05, 12, 14, 18 — LLM(provider="openai") pointed at DeepSeek.
- **no framework** (2): 21 (requests), 22 (sentence-transformers + faiss + openai).

**Verdict:** frameworks already installed do the job; nothing new needed.
LangChain = chains/RAG glue, LangGraph = stateful agent loops (13), CrewAI =
role-based crews (05/12/14/18), LlamaIndex = doc RAG (03). For NEW agents
prefer `_shared/llm.py` (lean, no framework) — frameworks only when you
actually need their orchestration (see 13/20 as references).

## How tier switching works

All 21 legacy agents now read `DEEPSEEK_API_BASE` / `DEEPSEEK_MODEL` env vars
(defaults: api.deepseek.com / deepseek-v4-flash — unchanged behavior).
To run any agent on local, set:

    DEEPSEEK_API_BASE=http://localhost:11434/v1  DEEPSEEK_MODEL=qwen3:8b

Bot wiring (the assistant app, private):
- `data/bots.json`: each agent bot has `tier` (local|flash|pro|none) + `env`
  dict. Local-tier bots carry the Ollama env above.
- `qa/run_500agent.py`: `--env K=V K2=V2` forwards env to the agent process.
- `qa/bot_runner.py`: builds the run command, appends `--env` from bot config.
- New agents: `agents/_shared/llm.py` — `chat(tier, ...)` / `get_client(tier)`
  / `tier_of(task_kind)`. Reference implementation: `22-vault-rag-agent`.

## Cost profile (whole corps, per month)

- 4 local bots: **$0**
- 12 flash bots + Hermes delegation: bulk of spend (flash ≈ 3× cheaper than pro)
- 3 pro bots: used sparingly (weekly macro, debates, analysis)
- Hermes fallback chain: flash → claude-sonnet-5 → local (never erroring)
