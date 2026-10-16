# Security - Jurassic Park

Public GitHub repo (`github.com/Jrudani21/jurassic-park`) that runs agents with real provider
keys on the owner's machine and auto-publishes a dashboard.

## Secrets

- Keys are read by `agents/_shared/llm.py::_key()` in this order: process env, then the repo
  `.env`, then an optional extra file named by `FLEET_ENV_FILE`. Key names referenced:
  `DEEPSEEK_API_KEY`, `BLUESMINDS_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`,
  `NVIDIA_API_KEY` (`ROUTING.md`), `TAVILY_API_KEY` (agent 01 `.env.example`).
- `.gitignore` excludes `.env` and `.env.*` (keeps `.env.example`), `data/`, logs, LLM caches,
  and machine-specific setup scripts (`setup-wsl-model-disk.*`, `fix-c-drive.*`, ...).
- **Frontier tier reads the Claude Code OAuth access token** from
  `~/.claude/.credentials.json` (or `ANTHROPIC_CREDENTIALS_FILE`) and calls the Anthropic API
  directly (`_claude_oauth_token()` in `llm.py`); on failure it shells out to the Hermes CLI
  (`subprocess.run`, 600 s timeout). Treat any code path near this as credential-handling.
- Secret scans (gitleaks v8.30.1, `--redact`, 2026-10-15): full git history - no leaks;
  `agents/`, `docs/`, `scripts/` working tree - no leaks. The only key-shaped string in tracked
  files is a labelled fake fixture in agent 21.
- No pre-commit hook is configured (`core.hooksPath` unset).

## Data protection

- PII rule (`ROUTING.md`): agent 21 is deterministic regex with no LLM; PII-adjacent work stays
  on the local tier.
- `docs/generate_site.py` scrubs absolute local paths (`E:\Local...`, `C:\Users...`) and five
  private repo names before writing the public `docs/data.js`.
- Agent 04 opens its SQLite database read-only unless `--allow-write` is passed.

## Findings from documenting (not fixed)

1. **Unattended publish with `git add -A`.** `docs/generate_site.py` stages the whole tree,
   commits and pushes whenever anything changed. Any untracked file in the repo at run time
   is published to the public repo. (`GUIDE_LOCAL.md` itself says "Don't `git add -A`".)
   This also means any local commit, including the one adding these docs, will be pushed by
   the next nightly run.
2. The tracked `jurassic-park-audit.md` is a placeholder audit stub (status checkboxes empty).
3. Agents pin old framework versions (e.g. `langchain==0.3.0`, `langgraph==0.2.0` in agent 01).
   No `pip-audit`/Dependabot configuration exists; vulnerability status Unknown.
4. `brain_client.py` indexes every `.md` under `BRAIN_VAULT` (personal notes) and may send
   chunks to cloud tiers when callers use a non-local tier.

## Reporting

Unknown - needs owner input.

## Verified against

`agents/_shared/llm.py` (`_key`, `_claude_oauth_token`, `_chat_frontier_hermes`),
`.gitignore`, `ROUTING.md`, `GUIDE_LOCAL.md`, `docs/generate_site.py` (`scrub`, commit block),
`agents/04-sql-query-agent/agent.py`, `agents/01-web-research-agent/requirements.txt`,
gitleaks runs, `git grep` for key patterns, `git config core.hooksPath`.
