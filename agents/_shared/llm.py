#!/usr/bin/env python3
"""Shared tiered LLM client — the standard for ALL agents in this repo.

Rule-based hybrid routing (see ROUTING.md in this repo root):

    tier    provider            cost        for task kinds
    local   Ollama qwen3:8b     $0          summarize, extract, template, recipe, classify
    nvidia  NVIDIA NIM free     $0          70b/8b fallback + free overflow (cold starts ~4min)
    flash   DeepSeek v4-flash   ~$0.14/M    default quality work
    pro     DeepSeek v4-pro     ~$0.43/M    analysis, reasoning, debate, financial

Failover: every tier falls back to cheaper tiers, then local last — a pro call
that fails still answers, on flash or local, instead of erroring.

Embeddings are ALWAYS local (sentence-transformers) — never billed.

Usage:
    from _shared.llm import chat, get_client, tier_of

    text, used_tier = chat("flash", "Summarize this", system="Be concise")
    client = get_client("local")          # OpenAI-compatible, for langchain/llama_index/crewai
    tier = tier_of("extract")             # -> "local"
"""
import os
import subprocess
from pathlib import Path
from typing import Callable

try:
    from dotenv import load_dotenv
    # repo .env (gitignored) — holds BLUESMINDS_API_KEY etc.
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except Exception:
    pass

from openai import OpenAI

from _shared import cache as cache_mod  # noqa: E402 — same package context as callers
from _shared import prompts  # noqa: E402 — cache-first prompt assembly
from _shared import breaker  # noqa: E402 — per-provider circuit breaker
from _shared import supervisor  # noqa: E402
from _shared import cost as cost_mod  # noqa: E402 — usage/cost ledger (never raises)


def _key(name: str) -> str:
    """Env var with fallback to Hermes .env and repo .env files.

    Agents are run by bots.json with limited env; this keeps flash/pro working
    even when DEEPSEEK_API_KEY isn't exported (it lives in Hermes .env).
    """
    v = os.getenv(name)
    if v:
        return v
    _cache_ = getattr(_key, "_env", None)
    if _cache_ is None:
        _env: dict[str, str] = {}
        for p in (os.path.expandvars(r"%LOCALAPPDATA%/hermes/.env"),
                  os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")):
            p = os.path.expandvars(p)
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, val = line.split("=", 1)
                            _env[k] = val
            except OSError:
                pass
        _key._env = _env  # type: ignore[attr-defined]
    return _cache_.get(name, "")  # type: ignore[union-attr]


TIERS = {
    "local": {
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "model": os.getenv("OLLAMA_MODEL", "qwen3:8b"),
        "api_key": "ollama",
        "cost": "$0",
    },
    # Bluesminds — free cloud relay (llama-8b tier, $100/mo program)
    "free": {
        "base_url": "https://api.bluesminds.com/v1",
        "model": os.getenv("BLUESMINDS_MODEL", "meta/llama-3.1-70b-instruct"),
        "api_key": _key("BLUESMINDS_API_KEY") or _key("KEN_BLUESMINDS_API_KEY"),
        "cost": "$0 (free tier)",
    },
    # OpenRouter — free models (nemotron-3-super-120b verified working;
    # ultra-550b = new 550B flagship free tier, probed 2026-08-13)
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        "api_key": _key("OPENROUTER_API_KEY"),
        "cost": "$0 (free models)",
    },
    # Groq — free tier, very fast (llama-3.3-70b verified working)
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "api_key": _key("GROQ_API_KEY"),
        "cost": "$0 (free tier)",
    },
    # NVIDIA NIM (build.nvidia.com) — free developer API tier, OpenAI-compatible.
    # Verified 2026-08-14: 200 on /v1/models + chat. Default 8b = always warm
    # (~0.4s); 70b exists but cold-starts 4-10min when unloaded (queue contention).
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct"),
        "api_key": _key("NVIDIA_API_KEY") or _key("KEN_NVIDIA_API_KEY"),
        "cost": "$0 (free tier)",
    },
    "flash": {
        "base_url": os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "api_key": _key("DEEPSEEK_API_KEY"),
        "cost": "~$0.14/M",
    },
    "pro": {
        "base_url": os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        "model": os.getenv("DEEPSEEK_PRO_MODEL", "deepseek-v4-pro"),
        "api_key": _key("DEEPSEEK_API_KEY"),
        "cost": "~$0.43/M",
    },
    # Frontier = Claude via Hermes' own adapter (Claude Code OAuth, auto-refresh,
    # identity headers). We bridge to `hermes chat` instead of re-implementing
    # Anthropic OAuth — Hermes already handles token refresh + headers.
    "frontier": {
        "provider": "hermes",
        "model": os.getenv("FRONTIER_MODEL", "claude-sonnet-5"),
        "cost": "Claude Pro OAuth (5h rolling window; in-app limit shown ~50% higher than documented — verified by user 2026-08-14)",
    },
}

# Failover order: requested tier first, then cheaper, local is the last resort.
_FALLBACK = {
    "frontier": ["frontier", "pro", "flash", "openrouter", "groq", "nvidia", "free", "local"],
    "pro": ["pro", "flash", "openrouter", "groq", "nvidia", "free", "local"],
    "flash": ["flash", "openrouter", "groq", "nvidia", "free", "local"],
    "openrouter": ["openrouter", "groq", "nvidia", "free", "local"],
    "groq": ["groq", "nvidia", "openrouter", "free", "local"],
    "nvidia": ["nvidia", "groq", "openrouter", "free", "local"],
    "free": ["free", "openrouter", "groq", "nvidia", "local"],
    "local": ["local"],
}

# Rule-based routing: task kind -> tier (research-backed; see ROUTING.md)
_LOCAL_KINDS = {"summarize", "extract", "template", "recipe", "classify", "travel", "draft"}
_PRO_KINDS = {"analysis", "reasoning", "debate", "financial"}
_FRONTIER_KINDS = {"deep-analysis", "hard-reasoning", "complex-reasoning", "frontier"}


def tier_of(task_kind: str) -> str:
    """Route a task kind to a tier. Unknown kinds default to flash (quality)."""
    k = (task_kind or "").lower().strip()
    if k in _FRONTIER_KINDS:
        return "frontier"
    if k in _PRO_KINDS:
        return "pro"
    if k in _LOCAL_KINDS:
        return "local"
    return "flash"


def cascade(task_kind: str, messages: list | None = None, system: str | None = None,
            temperature: float = 0.2, max_tokens: int = 1024,
            kind: str | None = None, docs: str | None = None,
            validate: Callable | None = None, **kwargs) -> tuple[str, str]:
    """CHEAP-FIRST CASCADE (research-backed 2026-08-14): route easy intents to
    the cheap tier (local/free), escalate to a stronger tier ONLY on a
    structured failure signal — empty output, refusal ("I cannot"), or a
    caller-provided validator rejecting the answer.

    Returns (content, tier_used). Escalation ladder: requested tier -> next
    stronger (via _FALLBACK reversed). Never raises unless ALL tiers fail.

    Args:
        task_kind: routes the FIRST attempt (tier_of).
        validate: optional callable(content) -> bool; False triggers escalation.
    """
    first = tier_of(task_kind)
    # Escalate from cheap upward: reverse of the normal fallback chain,
    # skipping tiers already tried. Normal fallback goes expensive->cheap;
    # cascade goes cheap->expensive.
    chain = list(dict.fromkeys(_FALLBACK.get(first, _FALLBACK["flash"])))
    # _FALLBACK[first] starts at first (most expensive for that tier) and
    # walks down. For cascade we want the reverse (cheap first), then up.
    chain = list(reversed(chain))

    messages = messages or []
    if isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    if system is None and kind:
        system = prompts.stable_system(kind)
    prefix: list[dict] = []
    if system:
        prefix.append({"role": "system", "content": system})
    if docs:
        prefix.append({"role": "system", "content": f"<reference-docs>\n{docs}\n</reference-docs>"})
    msgs = prefix + list(messages)

    last_err: Exception | None = None
    tried: set[str] = set()
    for t in chain:
        if t in tried:
            continue
        tried.add(t)
        brk = breaker.breaker_for(t)
        if not brk.allow():
            continue
        try:
            if t == "frontier":
                content = _chat_frontier(msgs, temperature, max_tokens)
            else:
                cfg = TIERS[t]
                call_kwargs = dict(kwargs)
                call_kwargs.pop("model", None)
                resp = get_client(t).chat.completions.create(
                    model=cfg["model"], messages=msgs,
                    temperature=temperature, max_tokens=max_tokens, **call_kwargs,
                )
                content = resp.choices[0].message.content
                if content:
                    cost_mod.record_usage(t, cfg["model"], resp.usage, caller="cascade")
            if not (content or "").strip():
                brk.record_failure()
                continue  # empty -> escalate
            low = content.lower()
            if any(x in low for x in ("i cannot", "i can't", "cannot provide", "unable to", "as an ai")):
                brk.record_failure()
                continue  # refusal -> escalate
            if validate is not None:
                try:
                    if not validate(content):
                        brk.record_failure()
                        continue  # validator rejected -> escalate
                except Exception:
                    brk.record_failure()
                    continue
            brk.record_success()
            return content, t
        except Exception as e:  # noqa: BLE001
            last_err = e
            brk.record_failure()
            continue
    raise RuntimeError(f"CASCADE_ALL_TIERS_FAILED ({first}): {last_err}")


def get_client(tier: str = "flash") -> OpenAI:
    """OpenAI-compatible client for the tier — plug into langchain/llama_index/crewai."""
    if tier not in TIERS:
        raise ValueError(f"unknown tier '{tier}' (use {sorted(TIERS)})")
    cfg = TIERS[tier]
    if tier != "local" and not cfg["api_key"]:
        raise RuntimeError(f"NO_API_KEY for tier '{tier}' — set DEEPSEEK_API_KEY")
    # Browser User-Agent: Groq is behind Cloudflare and 403/error-1010s
    # default SDK/urllib UAs (verified 2026-08-13). Harmless elsewhere.
    return OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"],
                  default_headers={"User-Agent":
                                   "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                                   "Chrome/126.0.0.0 Safari/537.36"})


def _chat_for_escalation(tier: str, messages: list[dict]) -> tuple[str, str]:
    """Escalation path for supervisor: re-run on a stronger tier, no recursion."""
    for t in _FALLBACK.get(tier, _FALLBACK["flash"]):
        brk = breaker.breaker_for(t)
        if not brk.allow():
            continue
        try:
            if t == "frontier":
                return _chat_frontier(messages, 0.2, 1024), t
            cfg = TIERS[t]
            call_kwargs = dict(kwargs)
            call_kwargs.pop("model", None)
            resp = get_client(t).chat.completions.create(
                model=cfg["model"], messages=messages,
                temperature=0.2, max_tokens=1024, **call_kwargs,
            )
            content = resp.choices[0].message.content
            if content:
                cost_mod.record_usage(t, cfg["model"], resp.usage, caller="escalation")
                brk.record_success()
                return content, t
            brk.record_failure()
        except Exception:
            brk.record_failure()
            continue
    return "", tier


def chat(tier: str = "flash", messages: list | None = None, system: str | None = None,
         temperature: float = 0.2, max_tokens: int | None = None, cache: bool = True,
         kind: str | None = None, docs: str | None = None, **kwargs) -> tuple[str, str]:
    """One completion with automatic failover to cheaper tiers.

    Caching (see _shared/cache.py): exact-match disk cache first, semantic
    (MiniLM) second — identical or near-identical requests skip the API
    entirely. Pass cache=False for time-sensitive calls (live tracking,
    weather, anything whose answer must be fresh).
    Returns (content, tier_used). Raises RuntimeError only if EVERY tier fails.

    CACHE-FIRST PROMPTING (see _shared/prompts.py):
    - system is the STATIC prefix: keep it byte-identical per task kind.
      Pass `kind=` and it defaults to the canonical stable prompt for that
      kind (research/summarize/classify/qa/coordinator) — never inline
      dates, session ids, or queries into it.
    - `docs=` holds retrieved reference material (RAG chunks). It is placed
      in a STATIC prefix after system, before the dynamic tail. Docs are
      stable per query, so the prefix stays cacheable across calls with the
      same query; only the tail (query itself, state) is billed full price.
      A dynamic field mid-prefix collapses the provider prefix cache.
    - ALL dynamic content (date, session, work-order state, the query) goes
      in the LAST user message, e.g. messages=[{"role": "user",
      "content": prompts.dynamic_tail(state_block, query_block)}].
    """
    if messages is None:
        messages = []
    elif isinstance(messages, str):
        messages = [{"role": "user", "content": messages}]
    if system is None and kind:
        system = prompts.stable_system(kind)
    if max_tokens is None:
        max_tokens = prompts.max_tokens_for(kind)  # per-kind output cap
    # Cache-first prefix assembly (order matters for provider prefix cache):
    #   [stable system prompt] -> [reference docs] -> [dynamic user tail]
    # Stable system stays FIRST so the prefix cache hits on it; docs extend
    # the stable prefix; only the tail is billed at full price.
    prefix: list[dict] = []
    if system:
        prefix.append({"role": "system", "content": system})
    if docs:
        # Framed as a system message so it never reads as a user turn.
        # Compressed deterministically (same docs -> same form) so the
        # provider prefix cache still hits on the shortened prefix.
        prefix.append({"role": "system", "content": f"<reference-docs>\n{prompts.compress_docs(docs)}\n</reference-docs>"})
    messages = prefix + list(messages)

    # ---- cache lookup (L1 exact, L2 semantic) ----
    key = None
    if cache:
        try:
            # B7: a non-serializable kwarg must never crash chat() — a key
            # construction failure only disables caching for this call.
            model0 = TIERS.get(tier, {}).get("model", "")
            key = cache_mod.exact_key(tier, model0, messages, temperature, max_tokens, kwargs)
            hit = cache_mod.exact_get(key)
            if hit is None and temperature <= 0.3:
                # B1/B4: semantic layer only ever embeds the last plain-string
                # USER message, and only when it's a short self-contained
                # question. Long prompts (RAG prompts embedding retrieved
                # sources) must not be semantically matched — a different
                # question over the same source text would collide.
                last_user = cache_mod.last_user_content(messages)
                if cache_mod.semantic_eligible(last_user):
                    hit = cache_mod.semantic_get(
                        cache_mod.model_family(model0), system or "", last_user)
            if hit is not None:
                return hit  # (response, tier_used)
        except Exception:
            key = None  # cache is an optimization — never a crash source (B7)

    last_err: Exception | None = None
    for t in _FALLBACK.get(tier, _FALLBACK["flash"]):
        # Circuit breaker: skip providers that are tripped open (fail fast —
        # a down provider shouldn't eat timeouts from 30 agents in parallel).
        brk = breaker.breaker_for(t)
        if not brk.allow():
            continue
        try:
            if t == "frontier":
                out = _chat_frontier(messages, temperature, max_tokens), t
            else:
                cfg = TIERS[t]
                call_kwargs = dict(kwargs)
                call_kwargs.pop("model", None)  # avoid duplicate model kwarg
                resp = get_client(t).chat.completions.create(
                    model=cfg["model"], messages=messages,
                    temperature=temperature, max_tokens=max_tokens, **call_kwargs,
                )
                content = resp.choices[0].message.content
                if not (content or "").strip():
                    # Empty completion (providers intermittently return 200
                    # with no text) is a tier failure, not success — fail over
                    # to the next tier, mirroring _chat_for_escalation.
                    brk.record_failure()
                    continue
                out = content, t
                cost_mod.record_usage(t, cfg["model"], resp.usage)

            # Supervisor: catch low-param/free-tier failures before returning.
            if supervisor.needs_supervision(t):
                final, used, _ = supervisor.supervise(
                    t, messages, out[0], escalate=_chat_for_escalation)
                out = final, used
            brk.record_success()  # provider call succeeded (post-supervision)

            # ---- cache write (AFTER supervision — cache what the caller
            #      actually receives, B3; per-PRODUCING-tier key, B2;
            #      temperature gates, B5) ----
            if cache and out[0]:
                try:
                    prod_cfg = TIERS.get(out[1], {})
                    # B2: key by the tier that PRODUCED the answer — a
                    # fallback-tier answer must not shadow the primary tier
                    # once it recovers (24h stale downgrade otherwise).
                    if key is None:
                        key = cache_mod.exact_key(
                            out[1], prod_cfg.get("model", ""), messages,
                            temperature, max_tokens, kwargs)
                    # B5: high-temperature outputs are non-deterministic by
                    # design — never cache above 0.8, semantic only <= 0.3.
                    if temperature <= 0.8:
                        cache_mod.exact_put(key, out[1], prod_cfg.get("model", ""), out[0])
                        if temperature <= 0.3:
                            last_user = cache_mod.last_user_content(messages)
                            if cache_mod.semantic_eligible(last_user):
                                cache_mod.semantic_put(
                                    cache_mod.model_family(prod_cfg.get("model", "")),
                                    system or "", last_user, out[0], out[1])
                except Exception:
                    pass  # write-through failure never fails the call
            return out
        except Exception as e:  # noqa: BLE001 — any provider failure triggers failover
            last_err = e
            brk.record_failure()
            continue
    raise RuntimeError(f"ALL_TIERS_FAILED ({tier}): {last_err}")


def _chat_frontier(messages: list[dict], temperature: float, max_tokens: int) -> str:
    """Claude frontier tier.

    Fast path: read the OAuth access token from the Claude Code credentials
    file (~/.claude/.credentials.json — the SAME store the VS Code Claude
    extension and `hermes` use) and call the Anthropic Messages API directly.
    Safety net: if the direct call fails (expired token, rate limit), fall
    back to `hermes chat -Q` which handles refresh + identity headers.
    """
    model = TIERS["frontier"]["model"]
    prompt = "\n\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    try:
        return _chat_frontier_direct(model, prompt, temperature, max_tokens)
    except Exception as direct_err:
        # Token expired / rate-limited / missing → let Hermes refresh & retry
        return _chat_frontier_hermes(model, prompt, direct_err)


def _claude_oauth_token() -> str | None:
    """Read the Claude Code OAuth access token (~/.claude/.credentials.json).

    Also honors ANTHROPIC_CREDENTIALS_FILE override (see project .env).
    """
    import json

    path = os.getenv("ANTHROPIC_CREDENTIALS_FILE") or os.path.join(
        os.path.expanduser("~"), ".claude", ".credentials.json"
    )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data["claudeAiOauth"]["accessToken"]
    except Exception:
        return None


def _chat_frontier_direct(model: str, prompt: str, temperature: float, max_tokens: int) -> str:
    """Call the Anthropic Messages API directly with the OAuth token (Bearer)."""
    import httpx

    tok = _claude_oauth_token()
    if not tok:
        raise RuntimeError("no claude oauth token (credentials file missing)")
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "Authorization": f"Bearer {tok}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"anthropic direct {resp.status_code}: {resp.text[:200]}")
    return resp.json()["content"][0]["text"]


def _chat_frontier_hermes(model: str, prompt: str, direct_err: Exception) -> str:
    """Safety net: hermes CLI auto-refreshes the OAuth token + identity headers."""
    cmd = ["hermes", "chat", "-q", prompt, "-Q", "-m", f"anthropic/{model}"]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"frontier {model} failed (direct: {direct_err}; hermes: {proc.stderr.strip()[:200]})"
        ) from direct_err
    out = proc.stdout.strip()
    if not out:
        raise RuntimeError(f"frontier {model} failed (direct: {direct_err}; hermes: empty output)") from direct_err
    if "Switched to fallback model" in out or "Fallback activated" in out:
        raise RuntimeError(
            f"frontier {model} unavailable; hermes fell back (direct: {direct_err})"
        ) from direct_err
    return _clean_cli_output(out)


def _clean_cli_output(out: str) -> str:
    """Strip hermes CLI startup noise (warnings, model-normalization notices)
    and ANSI escape codes from the captured stdout, keeping only the answer."""
    import re

    noise_prefixes = ("Warning:", "⚠️", "⚠ ", "Normalized model", "Resume this session")
    lines = []
    prev_dropped = False
    for ln in out.splitlines():
        s = ln.strip()
        if not s or s.startswith(noise_prefixes):
            prev_dropped = True
            continue
        # Continuation of a filtered multi-line warning (e.g. "... for\nanthropic.")
        if prev_dropped and len(s) < 40 and s.endswith("."):
            prev_dropped = True
            continue
        prev_dropped = False
        lines.append(s)
    # Drop ANSI escapes from anything that survived
    return re.sub(r"\x1b\[[0-9;]*m", "", "\n".join(lines)).strip()


if __name__ == "__main__":
    # Quick self-test: tier routing + a real zero-token local call.
    for kind in ["summarize", "template", "code", "analysis", "debate", "deep-analysis", ""]:
        print(f"  tier_of({kind!r:16}) -> {tier_of(kind)}")
    text, used = chat("local", "Reply with exactly: ok", max_tokens=8)
    print(f"  local chat -> {used}: {text.strip()!r}")
