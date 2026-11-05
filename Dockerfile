# Jurassic Park fleet - one image runs any agent.
#   docker build -t jurassic-park .
#   docker run --rm jurassic-park                                   # self-test, no keys needed
#   docker run --rm --env-file .env jurassic-park agents/01-web-research-agent/agent.py --query "topic"
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

# The shared client (agents/_shared) needs only these two packages.
RUN pip install openai==1.* requests

RUN useradd --create-home --uid 1000 fleet && mkdir -p /app/data && chown fleet /app/data
COPY --chown=fleet agents ./agents
COPY --chown=fleet docs/generate_site.py docs/selftest_scrub.py ./docs/
USER fleet

# Ledger and cache live here; mount a volume to keep them across runs.
VOLUME ["/app/data"]

ENTRYPOINT ["python"]
CMD ["docs/selftest_scrub.py"]
