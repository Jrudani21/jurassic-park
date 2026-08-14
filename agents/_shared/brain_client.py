"""Brain-as-context-service: local retrieval from the Obsidian vault for the
agent fleet. Zero new deps — Ollama via OpenAI-compatible endpoint + pure
Python BM25. Logic mirrors the assistant app's rag.py but is
self-contained so fleet bots (different venv) can call it.

Cache-first: callers should pass the SAME `query` for the same bot kind each
run so the RAG prefix stays stable and DeepSeek prefix-cache hits.

Sources indexed on demand (lazy, cached per process): every .md under
E:\\Local\\brain (vault), plus uploaded-doc style entries if the assistant's
embeddings.json exists. Re-sync is cheap (content-hash skip).
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from pathlib import Path

VAULT_DIR = Path(os.environ.get("BRAIN_VAULT", str(Path.home() / "brain")))
VAULT_PREFIX = "vault:"
VAULT_SKIP_DIRS = {".obsidian", ".trash", ".git", "templates"}

# Optional: reuse the assistant's already-embedded store when present
ASSISTANT_STORE = Path(os.environ.get(
    "ASSISTANT_STORE",
    str(Path.home() / ".cache" / "ken" / "embeddings.json")))

EMBED_MODEL = os.environ.get("BRAIN_EMBED_MODEL", "nomic-embed-text")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
MIN_SIMILARITY = 0.45
RRF_K = 60
DEFAULT_TOP_K = 4

_TOKEN_RE = re.compile(r"\w+")
_store: list[dict] | None = None
_store_ts = 0.0
_SYNC_TTL_S = 300  # re-sync at most every 5 min per process


# ---- embedding via OpenAI-compatible endpoint (no `ollama` pkg) ---------
def _embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch via Ollama's /v1/embeddings (OpenAI-compatible)."""
    import urllib.request

    body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/v1/embeddings",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [d["embedding"] for d in data["data"]]


def _embed_one(text: str) -> list[float]:
    return _embed([text])[0]


# ---- chunking (mirrors assistant/rag.py) ---------------------------------
def _split_sentences(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
    return [p.strip() for p in pieces if p.strip()]


def _chunk(text: str) -> list[str]:
    sentences = _split_sentences(text)
    if not sentences:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for sent in sentences:
        if current_len + len(sent) > CHUNK_SIZE and current:
            chunks.append(" ".join(current))
            overlap: list[str] = []
            overlap_len = 0
            for s in reversed(current):
                if overlap_len + len(s) > CHUNK_OVERLAP:
                    break
                overlap.insert(0, s)
                overlap_len += len(s)
            current = overlap
            current_len = overlap_len
        current.append(sent)
        current_len += len(sent)
    if current:
        chunks.append(" ".join(current))
    return chunks


# ---- BM25 (pure python, no rank_bm25 dep) --------------------------------
def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class _BM25:
    def __init__(self, docs: list[list[str]]):
        self.k1, self.b = 1.5, 0.75
        self.doc_freqs: list[dict[str, int]] = [{} for _ in docs]
        self.df: dict[str, int] = {}
        self.doc_len = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_len) / len(docs)) if docs else 0
        for i, d in enumerate(docs):
            for t in d:
                self.doc_freqs[i][t] = self.doc_freqs[i].get(t, 0) + 1
                self.df[t] = self.df.get(t, 0) + 1
        self.N = len(docs)

    def score(self, query: list[str], i: int) -> float:
        if self.N == 0:
            return 0.0
        score = 0.0
        dl = self.doc_len[i]
        for t in query:
            f = self.doc_freqs[i].get(t, 0)
            if f == 0:
                continue
            idf = math.log(1 + (self.N - self.df.get(t, 0) + 0.5) / (self.df.get(t, 0) + 0.5))
            score += idf * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
        return score


# ---- store ----------------------------------------------------------------
def _vault_files() -> list[Path]:
    if not VAULT_DIR.exists():
        return []
    return [
        p for p in VAULT_DIR.rglob("*.md")
        if not VAULT_SKIP_DIRS & set(p.relative_to(VAULT_DIR).parts)
    ]


def _sync() -> int:
    """Index vault notes not already in the in-process store (content-hash skip).
    Returns number of chunks added. Cheap after first call."""
    global _store, _store_ts
    if _store is None:
        _store = []
    if _store_ts and time.time() - _store_ts < _SYNC_TTL_S:
        return 0
    _store_ts = time.time()

    indexed = {c["source"]: c.get("hash") for c in _store if c["source"].startswith(VAULT_PREFIX)}
    added = 0
    for path in _vault_files():
        source = VAULT_PREFIX + path.relative_to(VAULT_DIR).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not text.strip():
            continue
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if indexed.get(source) == digest:
            continue
        _store = [c for c in _store if c["source"] != source]
        # CONTEXTUAL RETRIEVAL (research-backed 2026-08-14): prefix each
        # chunk with the note's title/frontmatter context before embedding.
        # Anthropic: 49% fewer retrieval failures from contextualization
        # alone; free (no LLM pass) when the context is the filename/title.
        ctx = _context_for(path)
        for chunk in _chunk(text):
            try:
                emb = _embed_one(chunk)
            except Exception:
                return added  # Ollama down — keep what we have
            # store the CONTEXTUALIZED text (title + chunk) for search/snippet
            _store.append({
                "source": source,
                "text": chunk,
                "context": ctx,
                "search_text": f"{ctx}\n{chunk}" if ctx else chunk,
                "embedding": emb,
                "hash": digest,
            })
            added += 1
    return added


def _context_for(path: Path) -> str:
    """Note title + frontmatter tags as retrieval context (no LLM)."""
    parts = [path.stem]
    try:
        head = path.read_text(encoding="utf-8")[:800]
    except Exception:
        return " ".join(parts)
    # frontmatter tags/aliases
    m = re.search(r"^---\s*\n([\s\S]*?)\n---", head)
    if m:
        fm = m.group(1)
        for line in fm.splitlines():
            if line.strip().lower().startswith(("tags:", "aliases:")):
                parts.append(line.strip())
    return " ".join(parts)


def _load_assistant_store() -> int:
    """Import pre-embedded chunks from the assistant's embeddings.json once."""
    global _store
    if _store is None:
        _store = []
    if ASSISTANT_STORE.exists():
        try:
            data = json.loads(ASSISTANT_STORE.read_text(encoding="utf-8"))
            existing = {c["source"] for c in _store}
            n = 0
            for c in data:
                if c.get("source") not in existing and c.get("embedding"):
                    _store.append(c)
                    existing.add(c["source"])
                    n += 1
            return n
        except Exception:
            return 0
    return 0


# ---- public API -----------------------------------------------------------
def ensure_indexed() -> str:
    """Sync vault + assistant store. Returns a short status string."""
    if not VAULT_DIR.exists() and not ASSISTANT_STORE.exists():
        return f"NO_VAULT {VAULT_DIR} (set BRAIN_VAULT)"
    a = _load_assistant_store()
    v = _sync()
    n = len(_store) if _store else 0
    parts = []
    if a:
        parts.append(f"{a} assistant chunks")
    if v:
        parts.append(f"{v} vault chunks")
    return f"BRAIN_INDEXED {n} chunks" + (f" ({', '.join(parts)})" if parts else "")


def search(query: str, top_k: int | None = None) -> str:
    """Hybrid BM25+cosine over vault + assistant store. Returns markdown text
    ready to drop into a prompt tail (cache-friendly: stable per query)."""
    ensure_indexed()
    if not _store:
        return "(no brain context indexed)"

    top_k = top_k or DEFAULT_TOP_K
    try:
        q_emb = _embed_one(query)
    except Exception:
        return "(brain embed unavailable — Ollama down?)"

    cosine_scores = []
    for c in _store:
        e = c.get("embedding")
        if not e:
            cosine_scores.append(0.0)
            continue
        dot = sum(a * b for a, b in zip(q_emb, e))
        nq = math.sqrt(sum(a * a for a in q_emb)) or 1e-9
        ne = math.sqrt(sum(a * a for a in e)) or 1e-9
        cosine_scores.append(dot / (nq * ne))

    bm25 = _BM25([_tokenize(c.get("search_text", c["text"])) for c in _store])
    bm25_scores = [bm25.score(_tokenize(query), i) for i in range(len(_store))]

    # RRF fusion (same as assistant)
    order_cos = sorted(range(len(_store)), key=lambda i: cosine_scores[i], reverse=True)
    order_bm = sorted(range(len(_store)), key=lambda i: bm25_scores[i], reverse=True)
    rank_cos = {i: r for r, i in enumerate(order_cos)}
    rank_bm = {i: r for r, i in enumerate(order_bm)}
    fused = []
    for i, c in enumerate(_store):
        rrf = 1 / (RRF_K + rank_cos[i] + 1) + 1 / (RRF_K + rank_bm[i] + 1)
        fused.append((rrf, cosine_scores[i], bm25_scores[i], c))
    fused.sort(key=lambda x: x[0], reverse=True)

    relevant = [f for f in fused if f[1] >= MIN_SIMILARITY or f[2] > 0]
    top = relevant[:top_k]
    if not top:
        return "(no sufficiently relevant brain chunks)"

    # RERANK (research-backed 2026-08-14): local cross-encoder on the top-N
    # beats BM25/vector rank. Gated — only used if the model is cached
    # locally (no surprise downloads); falls back to RRF order otherwise.
    top = _rerank(query, top)

    return "\n\n".join(
        f"[{n}] {c['source']} (score {sim:.2f})\n{c['text']}"
        for n, (_, sim, _, c) in enumerate(top, start=1)
    )


_reranker = None
_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
_rerank_tried = False


def _rerank(query: str, top: list[tuple]) -> list[tuple]:
    """Cross-encoder rerank of the RRF top-N (gated on local model cache)."""
    global _reranker, _rerank_tried
    if _rerank_tried:
        if _reranker is None:
            return top
    else:
        _rerank_tried = True
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(_RERANK_MODEL)
        except Exception:
            _reranker = None  # not cached / unavailable — keep RRF order
            return top
    try:
        pairs = [(query, c.get("search_text", c["text"])) for _, _, _, c in top]
        scores = _reranker.predict(pairs)
        scored = [(s, sim, bm, c) for (_, sim, bm, c), s in zip(top, scores)]
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored
    except Exception:
        return top


if __name__ == "__main__":
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "what projects are on this machine"
    print(ensure_indexed())
    print("---")
    print(search(q))
