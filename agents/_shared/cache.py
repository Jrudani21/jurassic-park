"""Disk-backed LLM response cache for the agent fleet (_shared/llm.py).

Layers (research-backed 2026-08, see ROUTING.md):
  L1 exact   — sha256(model + messages + params) -> response. SQLite, TTL 24h.
               Sub-millisecond, zero-risk (identical request = identical answer).
  L2 semantic— MiniLM embeddings (local, free) + cosine >= 0.93 against cached
               prompts of the same model family. Catches rephrased repeats
               (typical 25-45% extra hit rate per AWS/arxiv data).
  L3 provider— DeepSeek automatic prompt caching (cached-input tokens ~0.1x).
               Nothing to code: keep system prompts stable, done.

Design rules:
  - Never cache errors. Cache only successful completions.
  - Key includes tier + model + temperature + max_tokens: different model
    config = different answer space.
  - Semantic layer is opt-out via env LLM_SEMANTIC_CACHE=0 (adds ~1s + ~90MB
    RAM the first time MiniLM loads; worth it for repeated similar asks).
  - Time-sensitive callers pass cache=False (live tracking, weather).
"""
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

_CACHE_DIR = Path(os.getenv("LLM_CACHE_DIR", Path(__file__).resolve().parent / ".llm_cache"))
_DB = _CACHE_DIR / "llm_cache.sqlite"
_TTL_EXACT_S = int(os.getenv("LLM_CACHE_TTL_S", str(24 * 3600)))        # 24h
_TTL_SEMANTIC_S = int(os.getenv("LLM_SEMANTIC_TTL_S", str(7 * 24 * 3600)))  # 7d
_SEMANTIC_ON = os.getenv("LLM_SEMANTIC_CACHE", "1") != "0"
_SIM_THRESHOLD = float(os.getenv("LLM_SEMANTIC_THRESHOLD", "0.93"))

_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0, "semantic_hits": 0}
_warned: set[str] = set()  # one-shot warning per error class (B10)

_embedder = None  # lazy MiniLM

# Semantic layer is only safe for SHORT, self-contained questions (B1).
# Long prompts (RAG prompts embed retrieved sources) must never be matched
# semantically — a different question over the same source text shares ~90%
# of the vector and would serve a wrong cached answer. Length gate + caller
# opt-out both bypass it.
_SEMANTIC_MAX_PROMPT = int(os.getenv("LLM_SEMANTIC_MAX_PROMPT", "2000"))
_SEMANTIC_MIN_PROMPT = int(os.getenv("LLM_SEMANTIC_MIN_PROMPT", "15"))


def _warn_once(tag: str, msg: str) -> None:
    """Log the first occurrence of each error class, then stay quiet (B10)."""
    if tag not in _warned:
        _warned.add(tag)
        import warnings

        warnings.warn(f"llm-cache[{tag}]: {msg}")


def _connect() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB, timeout=10)
    # B9: WAL + NORMAL — concurrent fleet processes share this file; the
    # default rollback journal blocks readers during writes (busy timeouts
    # under fleet load). WAL lets readers and writers proceed concurrently.
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    conn.execute(
        """CREATE TABLE IF NOT EXISTS exact (
               key TEXT PRIMARY KEY, tier TEXT, model TEXT, response TEXT,
               ts REAL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS semantic (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               model_family TEXT, system TEXT, prompt TEXT, response TEXT,
               embedding BLOB, ts REAL)"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS stats (
               name TEXT PRIMARY KEY, value INTEGER)"""
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exact_ts ON exact(ts)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_semantic_fam_ts "
            "ON semantic(model_family, ts)")
    except Exception:
        pass
    return conn


def _bump(name: str) -> None:
    try:
        conn = _connect()
        conn.execute(
            "INSERT INTO stats(name,value) VALUES(?,1) "
            "ON CONFLICT(name) DO UPDATE SET value=value+1",
            (name,),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _embed(text: str) -> list[float]:
    """MiniLM embedding — local + free, same model the vault-rag agent uses."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder.encode(text, normalize_embeddings=True).tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def last_user_content(messages: list[dict]) -> str:
    """Last plain-string user message (B4: get AND put must embed the same).

    Returns '' when there is no user message or the content isn't a plain
    string (multimodal lists, etc.) — callers must skip semantic caching
    in that case.
    """
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content", "")
            return c if isinstance(c, str) else ""
    return ""


def semantic_eligible(prompt: str) -> bool:
    """True only if `prompt` is a short self-contained question (B1/B11)."""
    if not _SEMANTIC_ON:
        return False
    p = prompt.strip()
    return _SEMANTIC_MIN_PROMPT <= len(p) <= _SEMANTIC_MAX_PROMPT


def exact_key(tier: str, model: str, messages: list[dict], temperature: float,
              max_tokens: int, extra: dict | None = None) -> str:
    payload = {
        "tier": tier, "model": model, "messages": messages,
        "temperature": temperature, "max_tokens": max_tokens,
        "extra": extra or {},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def exact_get(key: str) -> tuple[str, str] | None:
    """Return (response, tier) or None."""
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT response, tier FROM exact WHERE key=? AND ts>?",
            (key, time.time() - _TTL_EXACT_S),
        ).fetchone()
        conn.close()
        if row:
            _stats["hits"] += 1
            _bump("exact_hits")
            return row[0], row[1]
        _stats["misses"] += 1
    except Exception as e:
        _warn_once("exact_get", str(e))
    return None


def exact_put(key: str, tier: str, model: str, response: str) -> None:
    try:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO exact(key,tier,model,response,ts) VALUES(?,?,?,?,?)",
            (key, tier, model, response, time.time()),
        )
        # B8: mirror the semantic-table prune — stale rows are never read
        # (TTL filter at read time) but must not grow the DB forever.
        conn.execute("DELETE FROM exact WHERE ts<?", (time.time() - _TTL_EXACT_S,))
        conn.commit()
        conn.close()
    except Exception as e:
        _warn_once("exact_put", str(e))


def semantic_get(model_family: str, system: str, prompt: str) -> tuple[str, str] | None:
    """Return (response, tier) if a similar prompt was answered recently."""
    if not _SEMANTIC_ON:
        return None
    try:
        vec = _embed(prompt)
        conn = _connect()
        rows = conn.execute(
            "SELECT prompt, response, embedding, tier FROM semantic "
            "WHERE model_family=? AND system=? AND ts>?",
            (model_family, system, time.time() - _TTL_SEMANTIC_S),
        ).fetchall()
        conn.close()
        best, best_sim = None, _SIM_THRESHOLD
        for p, resp, emb_blob, tier in rows:
            import numpy as np

            emb = np.frombuffer(emb_blob, dtype="float32").tolist()
            s = _cosine(vec, emb)
            if s >= best_sim:
                best, best_sim = (resp, tier), s
        if best:
            _stats["semantic_hits"] += 1
            _bump("semantic_hits")
            return best
    except Exception as e:
        _warn_once("semantic_get", str(e))
    return None


def semantic_put(model_family: str, system: str, prompt: str, response: str,
                 tier: str) -> None:
    if not _SEMANTIC_ON:
        return
    try:
        vec = _embed(prompt)
        import numpy as np

        conn = _connect()
        conn.execute(
            "INSERT INTO semantic(model_family,system,prompt,response,embedding,ts) "
            "VALUES(?,?,?,?,?,?)",
            (model_family, system, prompt, response,
             np.asarray(vec, dtype="float32").tobytes(), time.time()),
        )
        # keep the table lean: drop old entries past TTL
        conn.execute("DELETE FROM semantic WHERE ts<?", (time.time() - _TTL_SEMANTIC_S,))
        conn.commit()
        conn.close()
    except Exception as e:
        _warn_once("semantic_put", str(e))


def stats() -> dict:
    try:
        conn = _connect()
        rows = conn.execute("SELECT name, value FROM stats").fetchall()
        conn.close()
        out = dict(rows)
    except Exception:
        out = {}
    out.update({k: v for k, v in _stats.items()})
    return out


def model_family(model: str) -> str:
    """Group semantically comparable models (deepseek-* / llama-* / qwen-*)."""
    m = model.lower()
    for fam in ("deepseek", "llama", "qwen", "gemma", "gpt", "claude", "mistral", "kimi"):
        if fam in m:
            return fam
    return "other"
