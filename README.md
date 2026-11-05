# 🦖 JURASSIC PARK - Janak's AI Fleet

**The whole fleet in one place.** 34 scheduled bots + 17 on-demand agents, 4 crews, 8 model tiers,
running 24/7 on one PC - and the live dashboard that watches them.

The park theme is a memory aid: **staff = bots, species = LLM model tiers, DNA = tokens,
budget ledger = every real API call.** Every number on the dashboard is real, read live from `data.js`.

## What's inside

| Path | What it is |
|---|---|
| `agents/` | The fleet itself - 22 agent codebases + `_shared/` (zero-token LLM client, cache, supervisor, breaker, cost ledger) |
| `docs/` | The website - live Jurassic Park dashboard (served by GitHub Pages from `/docs`) |
| `scripts/` | Fleet ops scripts (cost report, model swaps, repair tools) |
| `ROUTING.md` | Operating manual: which tier each agent runs on, how to switch |
| `data/` | Runtime data (gitignored - cost ledger, cache) |

## The 8 species (= model tiers)

| Tier | Dino | Model | Cost |
|---|---|---|---|
| local | Compsognathus | qwen3.5-9b (LM Studio) | $0 |
| flash | Triceratops | DeepSeek v4-flash | ~$0.14/M |
| pro | Tyrannosaurus Rex | DeepSeek v4-pro | ~$0.43/M |
| frontier | Indominus Rex | Claude sonnet-5 (Pro sub) | sub |
| groq | Velociraptor | llama-3.3-70b | $0 |
| openrouter | Brachiosaurus | nemotron 120B | $0 |
| nvidia | Dilophosaurus | llama-3.1-8b | $0 |
| free | Gallimimus | Bluesminds 70b | $0 |

## Live refresh

`docs/generate_site.py` regenerates `data.js` from the real sources (bots.json, cost_ledger.jsonl,
llm_cache.sqlite, bots_state.json) and commits+pushes when something changed. Runs nightly via cron.

```bash
python docs/generate_site.py        # refresh + push only if data changed
python docs/generate_site.py --force   # always push
```

## Run in Docker

One image runs the agents that need only the shared client (`openai` + `requests`); agent 01 is the one tested. Agents that import `dotenv`, LangChain, pandas, CrewAI or LlamaIndex need their own `requirements.txt` installed first. Provider keys come from a `.env` file (see `ROUTING.md`). Compose 2.24 or newer is required.

```bash
docker build -t jurassic-park .
docker run --rm jurassic-park                      # self-test, needs no keys
docker compose up dashboard                        # dashboard at http://localhost:8080
docker compose run --rm agent agents/01-web-research-agent/agent.py --query "topic"
```

The agent run needs at least one provider key; without one it stops with `ALL_TIERS_FAILED`.
The container runs as a non-root user and keeps the cost ledger and LLM response cache in the `fleet-data` volume. The tool cache is not persisted.

## License

MIT - this is **our own** build (not a fork). The fleet code, shared client, and site were
written from scratch for this system.
