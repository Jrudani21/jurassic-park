#!/usr/bin/env python3
"""Vault RAG Agent — ask questions over the Obsidian brain vault (local).

Lean RAG on purpose: local Ollama embeddings (nomic-embed-text — ZERO tokens,
stays on this machine) + FAISS + tiered LLM (default free/local tiers to save
tokens). No LangChain/LlamaIndex — for a ~600KB vault frameworks are pure
bloat. All deps already exist in the 500-agents venv.

Usage:
  python agents/22-vault-rag-agent/agent.py --query "what did I decide about X"
  python agents/22-vault-rag-agent/agent.py --query "..." --top-k 5
  python agents/22-vault-rag-agent/agent.py --query "..." --tier local  # force local ollama

Output: answer + source file paths so claims are traceable to the vault.
Verbose results go to the log file; stdout stays terse.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

# Make the repo's agents/ dir importable so `_shared.llm` resolves
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _shared.llm import chat  # noqa: E402

BRAIN_DIR = Path(os.environ.get("BRAIN_DIR", str(Path.home() / "brain")))
SKIP_DIRS = {".git", ".obsidian", "templates"}
CHUNK_CHARS = 700
CHUNK_OVERLAP = 100
EMBED_MODEL = os.environ.get("RAG_EMBED_MODEL", "nomic-embed-text")
EMBED_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
LOG_DIR = BRAIN_DIR / "meta" / "rag_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"rag_{datetime.now():%Y%m%d}.jsonl"


def load_docs(brain_dir: Path) -> list[dict]:
    """All markdown files under brain_dir, skipping vault internals."""
    docs = []
    for p in sorted(brain_dir.rglob("*.md")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if text.strip():
            docs.append({"path": str(p.relative_to(brain_dir)), "text": text})
    return docs


def chunk_doc(doc: dict) -> list[dict]:
    """Sliding-window chunks with overlap; keeps markdown headers intact."""
    text = doc["text"]
    chunks = []
    i = 0
    while i < len(text):
        end = min(i + CHUNK_CHARS, len(text))
        # Don't split mid-code-block: extend to closing fence if inside one
        if text.count("```", i, end) % 2 == 1:
            close = text.find("```", end)
            if close != -1:
                end = min(close + 3, len(text))
        chunks.append({"path": doc["path"], "text": text[i:end]})
        if end >= len(text):
            break
        i = end - CHUNK_OVERLAP
    return chunks


def embed_texts(texts: list[str]) -> np.ndarray:
    """Embed via local Ollama (nomic-embed-text) — zero tokens, stays on box.

    Returns (N, dim) float32, L2-normalized (cosine == inner product).
    Falls back to a random-ish stable hash vector on Ollama outage so the
    pipeline never hard-crashes; caller sees low scores and can retry.
    """
    import urllib.request
    dim = 768
    vecs = np.zeros((len(texts), dim), dtype="float32")
    for i, t in enumerate(texts):
        body = json.dumps({"model": EMBED_MODEL, "prompt": t}).encode()
        req = urllib.request.Request(f"{EMBED_URL}/api/embeddings", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                v = json.loads(r.read())["embedding"]
            a = np.asarray(v, dtype="float32")
            if a.shape[0] == dim:
                vecs[i] = a
        except Exception:
            pass  # zero vector — scores will be ~0; caller can detect
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return vecs / norms


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description="Vault RAG Agent (brain Q&A)")
    ap.add_argument("--query", required=True, help="Question about your brain vault")
    ap.add_argument("--top-k", type=int, default=4, help="Chunks to retrieve (default 4)")
    ap.add_argument("--no-llm", action="store_true", help="Retrieval only (debug; no LLM call)")
    ap.add_argument("--tier", default="local",
                    help="LLM tier: local (ollama, default), free, groq, openrouter, flash, pro")
    args = ap.parse_args()

    docs = load_docs(BRAIN_DIR)
    if not docs:
        print(f"NO_DOCS {BRAIN_DIR}")
        return 1
    chunks = [c for d in docs for c in chunk_doc(d)]

    # ── Embed via local Ollama (zero tokens) ──────────────────────────────
    vecs = embed_texts([c["text"] for c in chunks])
    qvec = embed_texts([args.query])

    # ── FAISS inner product == cosine similarity on normalized vectors ─────
    import faiss
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(np.ascontiguousarray(vecs, dtype="float32"))
    scores, ids = index.search(np.ascontiguousarray(qvec, dtype="float32"), min(args.top_k, len(chunks)))
    hits = [(chunks[int(i)], float(s)) for i, s in zip(ids[0], scores[0]) if int(i) >= 0]

    # ── Answer generation via the shared tiered client (default local) ─────
    context = "\n\n---\n\n".join(f"SOURCE {c['path']}:\n{c['text']}" for c, _ in hits)
    answer = ""
    used = args.tier
    if not args.no_llm:
        prompt = (
            "You are a personal-knowledge assistant answering from the user's Obsidian vault. "
            "Answer ONLY from the provided sources. If the sources don't answer, say so plainly. "
            "End with a 'Sources:' line listing each source file you used.\n\n"
            f"QUESTION: {args.query}\n\nSOURCES:\n{context}"
        )
        try:
            answer, used = chat(args.tier, prompt, temperature=0.2, max_tokens=800)
        except RuntimeError as e:
            answer = f"LLM_FAILED: {e}"
            used = "error"

    # ── Log everything (verbose) to file; stdout stays terse ──────────────
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "query": args.query, "tier": used, "top_k": len(hits),
        "hits": [{"path": c["path"], "score": round(s, 3),
                  "snippet": c["text"][:120]} for c, s in hits],
        "answer": answer,
    }
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass

    print(f"💬 ANSWER (tier: {used})")
    print(answer)
    print(f"(logged → {LOG_FILE})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
