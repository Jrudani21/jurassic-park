# Jurassic Park fleet - one image runs any agent.
#   docker build -t jurassic-park .      (agent 01 tested; other agents need their own requirements)
#   docker run --rm jurassic-park                                   # self-test, no keys needed
#   docker run --rm --env-file .env jurassic-park agents/01-web-research-agent/agent.py --query "topic"
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# The shared client (agents/_shared) needs only these two packages.
RUN pip install openai==1.109.1 requests==2.34.2

RUN useradd --create-home --uid 1000 fleet && mkdir -p /app/data && chown fleet /app/data
COPY --chown=fleet agents ./agents
COPY --chown=fleet docs/generate_site.py docs/selftest_scrub.py ./docs/
USER fleet

# Cost ledger and LLM response cache live here; the volume keeps them across runs.
ENV LLM_CACHE_DIR=/app/data/llm_cache
VOLUME ["/app/data"]

ENTRYPOINT ["python"]
CMD ["docs/selftest_scrub.py"]
