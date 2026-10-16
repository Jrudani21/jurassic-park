# Code style - Jurassic Park

No lint or format config is checked in (no `pyproject.toml`, `ruff.toml`, `.flake8`,
`.editorconfig`). Conventions below are observed in the code.

## Python

- Target: Python 3.12 (`GUIDE_LOCAL.md`: "always `<repo>/.venv/Scripts/python.exe` (py3.12)").
  Modern syntax is used (`str | None`, `list[dict]`, `from __future__ import annotations` in
  some modules).
- **Every agent is a standalone CLI script**: module docstring with a `Usage:` block,
  `argparse` in `main()`, exit codes 0 success / 1 agent failure / 2 usage error
  (`GUIDE_LOCAL.md` section 2).
- Agents import shared code with a path insert, then `# noqa: E402`:
  `sys.path.insert(0, str(Path(__file__).resolve().parent.parent))` /
  `from _shared import llm as shared_llm  # noqa: E402`. The `noqa` comments suggest a
  flake8/ruff-style linter is used informally.
- New agents should call `_shared/llm.py` (`chat`, `get_client`, `tier_of`) rather than build
  their own client (`ROUTING.md`: "For NEW agents prefer `_shared/llm.py`").
- Shared modules open with a long docstring explaining the design and its evidence
  ("research-backed 2026-08", measured numbers). Keep that habit when changing behaviour.
- Infrastructure code must not break callers: ledger, guardrail logging and supervision are
  wrapped so they "never raise" (`cost.py`, `breaker.py`, `supervisor.py`).
- Tunables come from env vars with in-code defaults (`LLM_CACHE_TTL_S`,
  `LLM_SEMANTIC_THRESHOLD`, `LMSTUDIO_MODEL`, `NVIDIA_MODEL`, ...). No hardcoded local paths in
  public code: the generator and `run_clean.py` read paths from env (`FLEET_*`).
- Prompts: static, byte-identical system prompt per kind first, dynamic content last
  (`prompts.py` rules), to keep provider prefix caching effective.
- Each agent pins its own dependencies with `==` in its `requirements.txt`.

## Agent folder contract

`agent.py`, `requirements.txt`, `metadata.yaml` (`title`, `description`, `author`, `language`,
`framework`, `tags`, `industry`, `difficulty`, `llm`, `entrypoint`, `requirements`),
`.env.example`, `README.md`. Agent 22 currently has only `agent.py`.

## Site and docs

- No em-dashes in dashboard pages; real data only.
- When adding an agent, also update `ROUTING.md`, the fleet `bots.json` tier (private app) and
  the `GUIDE_LOCAL.md` matrix (`GUIDE_LOCAL.md` section 7).

## Commits

Conventional-ish prefixes on manual commits; the generator writes `site refresh <date>`.

## Verified against

`agents/_shared/*.py` docstrings and env lookups, `agents/*/agent.py` import lines,
`agents/01-web-research-agent/metadata.yaml` and `requirements.txt`, `GUIDE_LOCAL.md`,
`ROUTING.md`, `git ls-files` (no lint config).
