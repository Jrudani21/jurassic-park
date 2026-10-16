# PRD - Jurassic Park (agent fleet + live dashboard)

> Inferred from `README.md`, `ROUTING.md`, `GUIDE_LOCAL.md` and the code. No standalone spec
> exists; goals below are the owner's apparent intent.

## What it is

Two things in one repo (`README.md`):

1. **The fleet code**: 22 runnable single-purpose agents under `agents/` (research, code
   review, PDF Q&A, SQL, email drafting, news digest, resume parsing, meeting notes, stock
   research, debate, PII redaction, vault RAG, ...) sharing one tiered LLM client in
   `agents/_shared/`.
2. **The dashboard**: a static "Jurassic Park" themed site in `docs/` (GitHub Pages from
   `/docs`, per `README.md`) showing bots, crews, model tiers and the real cost ledger.
   `docs/generate_site.py` refreshes `docs/data.js` and commits+pushes nightly
   (`git log` shows daily "site refresh" commits through 2026-10-15).

The agents are scheduled and invoked by a separate private app ("the assistant app",
`qa/run_500agent.py` / `qa/bot_runner.py` per `ROUTING.md`), not by this repo.

## Users (inferred)

- The owner, operating the fleet at near-zero cost.
- Scheduled bots and review agents (`GUIDE_LOCAL.md` is written for "bots, review agents,
  QA crews, subagents, humans").
- Portfolio visitors (the dashboard is linked from the owner's portfolio).

## Goals (from `ROUTING.md`)

- Cheapest adequate model per task: local for mechanical work, DeepSeek flash by default,
  pro for reasoning, with free cloud relays as fallback.
- Never error when a provider is down: fail over down the tier chain to local.
- PII never leaves the machine (agent 21 is deterministic regex, no LLM).
- Every number on the dashboard is real (`README.md`).

## Non-goals

- Not a framework or library for others; no packaging (`pyproject.toml`/`setup.py` absent).
- No shared virtualenv definition in the repo: each agent has its own `requirements.txt`.

## Open questions

- **Provenance:** `README.md` says "our own build (not a fork)", but 20 of the 21
  `agents/*/metadata.yaml` files list `author: ashishpatel26` (one lists another GitHub user), and `agents/README.md` keeps that project's agent-index layout.
  Which agents are original vs adapted? Unknown - needs owner input.
- `ROUTING.md` (2026-09-14) records DeepSeek, OpenRouter, Groq and Bluesminds keys failing
  (401/500) with only `nvidia` and `local` reachable. Current state Unknown.
- Agents 21-22 are not in `agents/README.md`'s index; 22 has no README/metadata.

## Verified against

`README.md`, `ROUTING.md`, `GUIDE_LOCAL.md`, `agents/README.md`,
`agents/01-web-research-agent/metadata.yaml`, `git ls-files`, `git log --oneline`,
`ls agents/22-vault-rag-agent`.
