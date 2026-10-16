# AGENTS.md - Jurassic Park

Guidance for AI coding agents. Read `GUIDE_LOCAL.md` (exact invocation, exit codes, agent
matrix) and `ROUTING.md` (tiers, failover, key names) first; this file is the short version.

## Setup

- Python 3.12. The guide expects `<repo>/.venv/Scripts/python.exe`; there is no `.venv` in this
  checkout and no repo-wide requirements file. Each agent has its own `requirements.txt`.
  Do not install anything without the owner's go-ahead.
- When launched from a Hermes/Ken shell, strip the leaked env first:
  `env -u PYTHONPATH -u VIRTUAL_ENV -u PYTHONHOME ...` (all three), or use
  `agents/_shared/run_clean.py`.
- Keys come from env, the repo `.env` (gitignored), or `FLEET_ENV_FILE`. Never print them.

## Run

```bash
env -u PYTHONPATH -u VIRTUAL_ENV -u PYTHONHOME .venv/Scripts/python.exe agents/<dir>/agent.py --help   # exit 2 = wiring OK
python scripts/cost_report.py 7                                                                    # read-only ledger summary
```

Running an agent for real makes LLM calls. Prefer the `local` tier or a free tier; never
route to `pro`/`frontier` unless asked.

## Test

No suite exists (see TESTING.md). Minimum check after editing Python: AST-parse the changed
files; for `_shared/` changes, add a small offline `test_*.py` rather than calling providers.

## Conventions

- New agents: folder `agents/NN-name/` with `agent.py`, `requirements.txt`, `metadata.yaml`,
  `.env.example`, `README.md`; use `_shared/llm.py`; argparse; exit codes 0/1/2.
- Register a new agent in `ROUTING.md`, `GUIDE_LOCAL.md` and the private `bots.json`.
- Keep system prompts static per kind (`prompts.py`); dynamic content goes in the tail.
- Never fabricate data on a missing key or failed fetch; report the failure.
- PII stays local; agent 21 must stay LLM-free.

## Do / don't

- **Don't run `docs/generate_site.py`** unless asked: it commits with `git add -A` and pushes.
- **Don't leave stray files in the repo**: the nightly refresh would publish them.
- Stage explicit paths only (`GUIDE_LOCAL.md`: "Don't `git add -A`").
- Don't hardcode local paths in tracked code; read them from env (`FLEET_*`).
- Don't touch the gitignored machine-setup scripts (`setup-wsl-model-disk.*`, `fix-c-drive.*`,
  `*-ext4.sh`, `finish-migration.sh`).

## Sensitive paths

`agents/_shared/llm.py` (key lookup, Claude OAuth token read), `docs/generate_site.py`
(publishes, scrubs), `.env`, `data/` (ledger, guardrail log), `agents/21-pii-sanitization-agent/`.

## Verified against

`GUIDE_LOCAL.md`, `ROUTING.md`, `.gitignore`, `agents/_shared/llm.py`, `agents/_shared/run_clean.py`,
`docs/generate_site.py`, `ls -a` (no `.venv`).
