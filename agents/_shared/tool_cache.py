"""Tool/API result cache for the agent fleet (L3 in the cost hierarchy).

Caches the RESULTS of tool calls (web search, data fetches, API reads) keyed
by (tool, normalized args) with per-source TTLs, so repeat agent steps never
re-trigger a paid API fetch or the LLM call that consumes it.

Design (research-backed, 2026-08-14):
- Normalize args before keying: sort kwargs, strip whitespace/case.
- Per-source TTL: weather/minutes, web search/1h+, docs/until version bump.
- Store raw result + optional summary (short form for prompts).
- Separate from the completion cache (exact/semantic) — an identical tool
  result with a different follow-up question still saves the expensive fetch.
- Never cache volatile intents (live prices, market data past TTL).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

_CACHE_DIR = Path(__file__).resolve().parent / ".llm_cache"
_DB = _CACHE_DIR / "tool_cache.sqlite"

_lock = threading.Lock()
_stats = {"hits": 0, "misses": 0, "puts": 0}

# Per-source TTL (seconds). Extend as sources are added.
DEFAULT_TTL_S = 3600
SOURCE_TTL = {
    "web_search": 3600,     # 1h
    "hn": 3600,
    "reddit": 3600,
    "rss": 1800,            # 30m
    "weather": 900,         # 15m
    "stock": 900,           # 15m (live prices short TTL)
    "docs": 7 * 24 * 3600,  # 7d until version bump
    "brain": 300,           # 5m
}


def _connect() -> sqlite3.Connection:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tool_cache (
               key TEXT PRIMARY KEY,
               tool TEXT,
               result TEXT,
               summary TEXT,
               ts REAL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tool_ts ON tool_cache(tool, ts)")
    return conn


def _ttl_for(tool: str) -> int:
    return int(SOURCE_TTL.get(tool, DEFAULT_TTL_S))


def _normalize_args(args: tuple | list, kwargs: dict) -> str:
    """Canonical string for keying: sorted kwargs, stripped strings."""
    parts = []
    for a in args or ():
        parts.append(str(a).strip().lower())
    for k in sorted((kwargs or {}).keys()):
        v = str(kwargs[k]).strip().lower()
        parts.append(f"{k}={v}")
    return "|".join(parts)


def _key(tool: str, args: tuple | list, kwargs: dict) -> str:
    norm = _normalize_args(args, kwargs)
    return hashlib.sha256(f"{tool}::{norm}".encode()).hexdigest()


def get(tool: str, args: tuple | list = (), kwargs: dict | None = None) -> str | None:
    """Return cached raw result for (tool, args, kwargs) if fresh, else None."""
    key = _key(tool, args, kwargs or {})
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT result FROM tool_cache WHERE key=? AND ts>?",
            (key, time.time() - _ttl_for(tool)),
        ).fetchone()
        conn.close()
        if row:
            with _lock:
                _stats["hits"] += 1
            return row[0]
        with _lock:
            _stats["misses"] += 1
    except Exception:
        pass
    return None


def put(tool: str, result: str, args: tuple | list = (), kwargs: dict | None = None,
        summary: str = "") -> None:
    """Store a tool result under (tool, args, kwargs). Never raises."""
    key = _key(tool, args, kwargs or {})
    try:
        conn = _connect()
        conn.execute(
            "INSERT OR REPLACE INTO tool_cache(key,tool,result,summary,ts) VALUES(?,?,?,?,?)",
            (key, tool, result, summary, time.time()),
        )
        # prune stale rows (keep DB lean)
        conn.execute("DELETE FROM tool_cache WHERE ts<?", (time.time() - DEFAULT_TTL_S * 2,))
        conn.commit()
        conn.close()
        with _lock:
            _stats["puts"] += 1
    except Exception:
        pass


def get_summary(tool: str, args: tuple | list = (), kwargs: dict | None = None) -> str | None:
    """Return cached summary (short form) if fresh — useful for prompt injection."""
    key = _key(tool, args, kwargs or {})
    try:
        conn = _connect()
        row = conn.execute(
            "SELECT summary FROM tool_cache WHERE key=? AND ts>?",
            (key, time.time() - _ttl_for(tool)),
        ).fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def stats() -> dict:
    with _lock:
        out = dict(_stats)
    try:
        conn = _connect()
        n = conn.execute("SELECT COUNT(*) FROM tool_cache").fetchone()[0]
        conn.close()
        out["rows"] = n
    except Exception:
        out["rows"] = 0
    return out


def clear(tool: str | None = None) -> int:
    """Clear cache (optionally per tool). Returns rows deleted."""
    try:
        conn = _connect()
        if tool:
            cur = conn.execute("DELETE FROM tool_cache WHERE tool=?", (tool,))
        else:
            cur = conn.execute("DELETE FROM tool_cache")
        conn.commit()
        n = cur.rowcount
        conn.close()
        return n
    except Exception:
        return 0


if __name__ == "__main__":
    # self-test — ISOLATED: scratch cache dir, never the prod store (lesson
    # from Tier 1 post-mortem: self-tests must not pollute prod data).
    import tempfile
    _orig_dir = _CACHE_DIR
    _CACHE_DIR = Path(tempfile.mkdtemp(prefix="tool_cache_test_"))
    _DB = _CACHE_DIR / "tool_cache.sqlite"
    try:
        put("web_search", "RESULT-A", ("query1",), {})
        print("get hit:", get("web_search", ("query1",)))
        print("get miss:", get("web_search", ("query2",)))
        print("stats:", stats())
    finally:
        import shutil
        shutil.rmtree(_CACHE_DIR, ignore_errors=True)
        _CACHE_DIR = _orig_dir
