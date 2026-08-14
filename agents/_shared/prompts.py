"""Cache-first prompt assembly for the fleet (used by _shared/llm.py).

Two rules (research-backed; see brain/notes/2026-08-14-cache-first-architecture.md):

1. STATIC FIRST, BYTE-IDENTICAL. The system message must be bit-for-bit the
   same on every call of the same bot kind. One dynamic character (date,
   session id, query) mid-prefix collapses the whole DeepSeek prefix cache at
   that point. DeepSeek v4-flash needs >= 256 tokens of stable prefix before
   any cache hit is possible (measured 2026-08-13).

2. DYNAMIC AT THE TAIL. Everything that changes (date, work-order state,
   last-run info, retrieved docs, the query itself) goes in the LAST user
   message via dynamic_tail(). Never in system.

Pattern (ProjectDiscovery case: 7% -> 84% hit rate): static system + static
docs prefix, then dynamic tail. Static content gets the ~0.1x cached-input
rate; only the tail is billed at full price.
"""

# Stable, per-kind system prompts. These are LONG on purpose: prefix caching
# only pays off with enough static mass (>= 256 tokens for v4-flash), and the
# prompt must NEVER change for a given kind — edit = cache cold start.
STABLE_SYSTEMS: dict[str, str] = {
    "research": (
        "You are a research analyst in the KEN agent fleet. Produce structured "
        "reports with three sections: Summary, Key Findings (bullets), Sources. "
        "Cite every claim to a source URL. If sources are empty or insufficient, "
        "say so honestly - never fabricate sources, never invent URLs, never "
        "guess numbers. Keep findings factual and concise. Do not editorialize "
        "beyond the evidence. Output markdown. Prefer the most recent and most "
        "authoritative sources available."
    ),
    "summarize": (
        "You are a summarizer in the KEN agent fleet. Condense the input to its "
        "essential facts, decisions, and action items. Preserve exact numbers, "
        "dates, names, and technical terms. Drop filler and repetition. Output "
        "tight bullet list when input is list-like, short paragraphs otherwise. "
        "Never add information that is not in the input."
    ),
    "news": (
        "You are a news analyst in the KEN agent fleet. Create a structured "
        "news briefing with: 1) Top Story, 2) Key Themes (3 bullet points), "
        "3) What to Watch, 4) Quick Headlines list. Base every item only on "
        "the provided articles; never invent stories or details not in the "
        "input. Cite the source name next to each item."
    ),
    "financial": (
        "You are a financial analyst in the KEN agent fleet. Provide a concise "
        "stock analysis covering: Investment Thesis (2-3 sentences), Key "
        "Strengths (3 bullets), Key Risks (3 bullets), Valuation Assessment, "
        "and a Verdict (Buy/Hold/Sell with brief reasoning). Keep it under "
        "300 words. Base every figure on the provided data; never invent "
        "numbers, never guess market data you were not given."
    ),
    "classify": (
        "You are a classifier in the KEN agent fleet. Assign the input to exactly "
        "one category from the provided set. Reply with the category name only - "
        "no explanation, no punctuation beyond the name itself. If the input does "
        "not fit any category, reply UNKNOWN. Be consistent: identical input must "
        "always yield the identical category."
    ),
    "qa": (
        "You are a QA analyst in the KEN agent fleet. Review the given test "
        "evidence and report pass/fail per case with the decisive log line quoted "
        "verbatim. Do not speculate about causes; report what the evidence shows. "
        "Flag flaky or inconclusive results explicitly rather than guessing."
    ),
    "coordinator": (
        "You are a fleet coordinator in the KEN agent fleet. Read the fleet "
        "report, identify issues (stale bots, over-budget, missed windows), and "
        "escalate per policy. Routine issues you may pre-approve; anything "
        "unusual or costly goes to the human owner. Do not auto-fix. Deliver "
        "findings as a concise bullet list with bot ids."
    ),
    "analysis": (
        "You are KEN's log analyst. Produce terse, grounded EOD reports from "
        "the supplied log bundle. Never invent facts. Use the exact section "
        "structure requested."
    ),
    "default": (
        "You are KEN, a local personal AI assistant. Answer directly, work "
        "efficiently, keep responses concise. Use the tools available to you. "
        "If you do not know something, say so - never fabricate. Technical "
        "terms, paths, and commands must be reproduced exactly."
    ),
}


def stable_system(kind: str | None) -> str:
    """Return the canonical system prompt for a task kind (fallback: default)."""
    return STABLE_SYSTEMS.get(kind or "", STABLE_SYSTEMS["default"])


# OUTPUT-TOKEN CONTROL (research-backed 2026-08-14): output tokens are billed
# at the same rate as input and NEVER cacheable — pure cost. Per-kind caps
# keep the model from rambling. Override with max_tokens= explicitly.
MAX_TOKENS: dict[str, int] = {
    "classify": 60,       # category name only
    "extract": 300,
    "summarize": 500,
    "news": 800,
    "qa": 400,
    "research": 1000,
    "financial": 500,
    "coordinator": 400,
    "analysis": 1200,
    "default": 1024,
}


def max_tokens_for(kind: str | None) -> int:
    """Per-kind output cap; explicit max_tokens= overrides at call site."""
    return MAX_TOKENS.get(kind or "", MAX_TOKENS["default"])


# PROMPT COMPRESSION (research-backed 2026-08-14): compress the static
# reference-docs prefix ONCE (deterministic, no LLM), cache the compressed
# form so DeepSeek prefix caching still hits. Simple + lossless-ish:
# collapse blank runs, drop markdown code fences' trailing whitespace, trim
# per-chunk to N chars. No tokenizer needed — deterministic by doc version.
COMPRESS_MAX_CHUNK = 2000      # max chars per retained chunk
COMPRESS_MAX_CHUNKS = 8        # max chunks retained


def compress_docs(docs: str) -> str:
    """Deterministic, cache-safe compression of reference material.

    Output depends ONLY on the input bytes (same docs -> same compressed
    form every time), so the provider prefix cache keeps hitting. Cheap
    regex/normalization — no LLM, no external deps.
    """
    if not docs:
        return ""
    # collapse blank lines, normalize whitespace per line
    lines = [ln.rstrip() for ln in docs.splitlines()]
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        blank = not ln.strip()
        if blank and prev_blank:
            continue  # collapse multiple blanks to one
        prev_blank = blank
        out.append(ln)
    text = "\n".join(out).strip()

    # split into chunks on blank-line separators (already normalized), cap count
    chunks = [c.strip() for c in text.split("\n\n") if c.strip()]
    if len(chunks) > COMPRESS_MAX_CHUNKS:
        chunks = chunks[:COMPRESS_MAX_CHUNKS]
    # cap each chunk length (hard truncate at word boundary)
    capped = []
    for c in chunks:
        if len(c) > COMPRESS_MAX_CHUNK:
            cut = c[:COMPRESS_MAX_CHUNK]
            sp = cut.rfind(" ")
            capped.append(cut[:sp] if sp > 0 else cut)
        else:
            capped.append(c)
    return "\n\n".join(capped)


def dynamic_tail(*blocks: str) -> str:
    """Pack dynamic context as ONE tail user message (cache-safe).

    Pass every per-call value here: current date, session/work-order state,
    last-run info, retrieved documents, and the query itself. The system
    message never changes; only this tail does.
    """
    return "\n\n".join(b for b in blocks if b and b.strip())
