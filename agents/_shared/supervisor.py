"""Supervisor for low-parameter/free-tier LLM outputs (_shared/llm.py).

The problem: local (qwen3:8b), Bluesminds (llama-3.1-70b), OpenRouter
(:free) and Groq (:free) models are weaker — they occasionally return
empty strings, gibberish, infinite loops, or error text. This module is
the overseer that catches those failures BEFORE the caller sees them.

Two layers (cost-aware):
  L1 heuristics — pure rules, ZERO tokens. Catches:
    - empty / whitespace-only responses
    - error-shaped text ("Error talking to", "Error:", tracebacks)
    - pathological repetition (a short n-gram repeated many times)
    - loop detection ("I'm sorry" spam, repeated identical sentences)
    - refusal-shaped text when the request was a normal question
    - suspiciously short output for a non-trivial request (len threshold)
  L2 LLM escalation — ONLY when L1 fails AND LLM_SUPERVISOR=1 (default OFF
  to stay $0). Re-runs the request on the next-higher tier once and keeps
  the better reply. Env knobs:
    LLM_SUPERVISOR=0/1        (default 0 — rule-based only)
    LLM_SUPERVISOR_TIER=flash (which tier to escalate to)

Design rules:
  - Never supervises pro/frontier outputs (already strong, avoid cost).
  - Supervision is best-effort: any exception inside falls through to the
    original response (never break the caller).
  - Escalation keeps the ORIGINAL response when the stronger tier also
    looks broken (fall back to original, don't propagate garbage).
"""
import os
import re

# Tiers that need supervision (weak/free). pro/frontier are trusted.
_SUPERVISED_TIERS = {"local", "free", "openrouter", "groq", "nvidia"}

_ESCAPE = re.compile(r"error talking to|error:|traceback|exception|api key|401|429|500", re.I)
_REFUSAL = re.compile(r"^(i'?m sorry|sorry,? i|cannot|i can'?t|i am unable|as an ai)", re.I)
# A word repeated 5+ times in quick succession (loop/gibberish marker)
_LOOPY = re.compile(r"(\b\w[\w']*\b)(?:\W+\1){4,}", re.I)


def needs_supervision(tier: str) -> bool:
    """True when this tier's output should be checked."""
    return tier in _SUPERVISED_TIERS


def _looks_error(text: str) -> bool:
    return bool(_ESCAPE.search(text)) and len(text) < 800


def _looks_loopy(text: str) -> bool:
    if len(text) < 60:
        return False
    m = _LOOPY.search(text)
    if m:
        return True
    # repeated full sentences
    sents = [s.strip() for s in re.split(r"[.!?]\s+", text) if len(s.strip()) > 4]
    if len(sents) >= 4 and len(set(sents)) <= 2:
        return True
    return False


def _looks_refusal(text: str) -> bool:
    return bool(_REFUSAL.match(text.strip())) and len(text) < 400


def _looks_empty(text: str) -> bool:
    return not text or not text.strip() or text.strip().lower() in {"", "ok", "done", "yes", "no"}


def check(text: str, request_hint: str = "") -> tuple[bool, str]:
    """Run L1 heuristics. Returns (ok, reason). ok=True means pass."""
    t = text or ""
    if _looks_empty(t):
        return False, "empty"
    if _looks_error(t):
        return False, "error-text"
    if _looks_loopy(t):
        return False, "loop"
    if _looks_refusal(t):
        return False, "refusal"
    # too-short for a substantive ask
    if len(request_hint) > 40 and len(t) < 40:
        return False, "too-short"
    return True, ""


def supervise(tier: str, messages: list[dict], response: str,
              escalate=None) -> tuple[str, str, bool]:
    """Supervise a low-tier response.

    Returns (final_response, final_tier, escalated). When the response
    fails L1 and LLM escalation is enabled, re-runs on the next-higher
    tier once via the provided callable (chat-like: (tier, messages) ->
    (text, tier_used)). If escalation is off or the re-run also looks
    broken, returns the ORIGINAL response unchanged.
    """
    if not needs_supervision(tier):
        return response, tier, False
    try:
        ok, reason = check(response)
        if ok:
            return response, tier, False
        # L1 failed — try LLM escalation if enabled and a callable was given
        if os.getenv("LLM_SUPERVISOR", "0") == "1" and escalate is not None:
            target = os.getenv("LLM_SUPERVISOR_TIER", "flash")
            try:
                better, used = escalate(target, messages)
                ok2, _ = check(better)
                if ok2 and better.strip():
                    return better, used, True
            except Exception:
                pass  # fall through to original
        return response, tier, False
    except Exception:
        return response, tier, False
