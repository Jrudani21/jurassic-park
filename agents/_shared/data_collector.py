"""Data Collector — real, free-source fetching for the fleet.

Free data sources (no API keys):
  - Reddit:      r/{sub}/top.json + search (public JSON, no auth needed)
  - Hacker News: Algolia API (search + top stories)
  - RSS/Atom:    generic feed fetch (Reuters, arXiv, blogs, ...)
  - Web:         simple page fetch for candidate URLs

Guarantees: NEVER fabricates. If a source fails or returns nothing, it is
reported as failed — no placeholder content, ever. (Contrast: the old
06-news-summarizer faked example articles when NewsAPI was absent.)

Usage:
    python data_collector.py reddit --subs "MachineLearning,LocalLLaMA" --limit 5
    python data_collector.py hn --query "llm cache" --limit 5
    python data_collector.py rss --feeds "https://arxiv.org/rss/cs.AI"
    python data_collector.py all --topics "weather derivatives" --limit 4
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/html",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 15


def _get(url: str, params: dict | None = None, headers: dict | None = None,
         cache_tool: str = "", cache_ttl: int | None = None) -> dict:
    """GET JSON with optional tool-cache layer.

    When `cache_tool` is set, the raw JSON response is cached keyed by
    (tool, url+params) with the tool's default TTL (or cache_ttl override).
    This is the L3 tool-result cache: repeat fetches (same query within TTL)
    are served from SQLite, zero network, zero cost.
    """
    if cache_tool:
        from _shared import tool_cache
        hit = tool_cache.get(cache_tool, (url,), {"params": params or {}})
        if hit is not None:
            try:
                return json.loads(hit)
            except Exception:
                pass  # corrupt cache entry — refetch

    r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    if cache_tool:
        try:
            from _shared import tool_cache
            tool_cache.put(cache_tool, json.dumps(data), (url,), {"params": params or {}})
        except Exception:
            pass
    return data


def reddit(subs: list[str], limit: int = 5, sort: str = "top") -> list[dict]:
    """Fetch top posts from subreddits via the public JSON API (no key).

    Reddit blocks some IPs/datacenter ranges; falls back to old.reddit.com
    when www.reddit.com refuses.
    """
    out = []
    for sub in subs:
        sub = sub.strip().lstrip("r/")
        for host in ("https://www.reddit.com", "https://old.reddit.com"):
            try:
                data = _get(f"{host}/r/{sub}/{sort}.json",
                            {"limit": limit, "raw_json": 1}, cache_tool="reddit")
                for child in data.get("data", {}).get("children", []):
                    p = child.get("data", {})
                    out.append({
                        "source": f"reddit/r/{sub}",
                        "title": p.get("title"),
                        "url": "https://www.reddit.com" + (p.get("permalink") or ""),
                        "score": p.get("score"),
                        "comments": p.get("num_comments"),
                        "created_utc": p.get("created_utc"),
                        "selftext": (p.get("selftext") or "")[:300],
                    })
                break  # host succeeded
            except Exception as e:
                last_err = e
        else:
            out.append({"source": f"reddit/r/{sub}", "error": str(last_err)[:120]})
        time.sleep(0.5)  # be polite
    return out


def hackernews(query: str | None = None, limit: int = 5) -> list[dict]:
    """Hacker News via Algolia API — free, no key."""
    try:
        if query:
            data = _get("https://hn.algolia.com/api/v1/search",
                        {"query": query, "tags": "story", "hitsPerPage": limit},
                        cache_tool="hn")
            hits = data.get("hits", [])
        else:
            data = _get("https://hn.algolia.com/api/v1/search_by_date",
                        {"tags": "front_page", "hitsPerPage": limit},
                        cache_tool="hn")
            hits = data.get("hits", [])
        return [{
            "source": "hackernews",
            "title": h.get("title"),
            "url": h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
            "points": h.get("points"),
            "comments": h.get("num_comments"),
            "created_utc": h.get("created_at_i"),
            "selftext": "",
        } for h in hits]
    except Exception as e:
        return [{"source": "hackernews", "error": str(e)[:120]}]


def rss(feeds: list[str], limit: int = 5) -> list[dict]:
    """Fetch entries from RSS/Atom feeds (no key)."""
    try:
        import feedparser
    except ImportError:
        return [{"source": f"rss:{f}", "error": "feedparser not installed"} for f in feeds]
    out = []
    for f in feeds:
        try:
            from _shared import tool_cache
            hit = tool_cache.get("rss", (f,))
            if hit is not None:
                parsed_entries = json.loads(hit)
            else:
                parsed = feedparser.parse(f)
                if getattr(parsed, "bozo", 0) and not parsed.entries:
                    out.append({"source": f"rss:{f}", "error": "parse failed"})
                    continue
                parsed_entries = [{
                    "title": e.get("title"), "link": e.get("link"),
                    "summary": (e.get("summary") or "")[:300],
                } for e in parsed.entries[:limit]]
                tool_cache.put("rss", json.dumps(parsed_entries), (f,))
            for e in parsed_entries:
                out.append({
                    "source": f"rss:{f}",
                    "title": e.get("title"),
                    "url": e.get("link"),
                    "score": None,
                    "comments": None,
                    "created_utc": None,
                    "selftext": e.get("summary") or "",
                })
        except Exception as e:
            out.append({"source": f"rss:{f}", "error": str(e)[:120]})
    return out


def collect(topics: list[str], subs: list[str], limit: int) -> dict:
    """Run all sources for the given topics — returns structured results."""
    result = {"collected_at": datetime.now(timezone.utc).isoformat(), "items": []}
    for topic in topics:
        q = topic.strip()
        if not q:
            continue
        items = hackernews(q, limit)
        items += reddit(subs, limit) if subs else []
        for it in items:
            it["topic"] = q
        result["items"].extend(items)
    if not topics:
        result["items"] = reddit(subs, limit) if subs else hackernews(None, limit)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["reddit", "hn", "rss", "all"])
    ap.add_argument("--subs", default="MachineLearning,LocalLLaMA",
                    help="comma-separated subreddits")
    ap.add_argument("--feeds", default="", help="comma-separated RSS feeds")
    ap.add_argument("--topics", default="", help="comma-separated topics")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--out", default="", help="JSON output file")
    args = ap.parse_args()

    subs = [s for s in args.subs.split(",") if s.strip()]
    feeds = [f for f in args.feeds.split(",") if f.strip()]
    topics = [t for t in args.topics.split(",") if t.strip()]

    if args.mode == "reddit":
        data = {"collected_at": datetime.now(timezone.utc).isoformat(),
                "items": reddit(subs, args.limit)}
    elif args.mode == "hn":
        data = {"collected_at": datetime.now(timezone.utc).isoformat(),
                "items": hackernews(topics[0] if topics else None, args.limit)}
    elif args.mode == "rss":
        data = {"collected_at": datetime.now(timezone.utc).isoformat(),
                "items": rss(feeds, args.limit)}
    else:
        data = collect(topics, subs, args.limit)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data, indent=1), encoding="utf-8")
    else:
        print(json.dumps(data, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
