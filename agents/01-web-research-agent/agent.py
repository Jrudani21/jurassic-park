"""
Web Research Agent — keyless search + shared LLM client.

Searches the web for a given topic, synthesizes findings, and returns
a structured research report.

Repaired 2026-08-13 (domino check): TavilySearch required langchain_tavily
+ a TAVILY_API_KEY that was never configured, so the agent crashed on
import. Replaced with the keyless data collector (Hacker News + Reddit)
and the shared _shared.llm.chat() client (full tier failover + cache +
supervision).

Usage:
    python agent.py --query "latest advances in quantum computing"
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _shared import data_collector, llm, prompts  # noqa: E402


def search_web(query: str, limit: int = 5) -> list[dict]:
    """Keyless web search: Hacker News + Reddit (no API keys needed)."""
    results: list[dict] = []
    for it in data_collector.hackernews(query, limit):
        if "error" not in it:
            results.append({
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "content": it.get("selftext", "") or it.get("title", ""),
                "score": it.get("points"),
            })
    for it in data_collector.reddit(["MachineLearning", "LocalLLaMA", "artificial"], limit):
        if "error" not in it:
            results.append({
                "url": it.get("url", ""),
                "title": it.get("title", ""),
                "content": it.get("selftext", "") or it.get("title", ""),
                "score": it.get("score"),
            })
    return results[:limit]


def synthesize_report(query: str, results: list[dict], tier: str = "flash",
                      brain_context: str = "") -> str:
    """Synthesize search results into a structured report via the shared client.

    Cache-first: stable system prompt (kind=research) + stable docs prefix
    (`docs=` holds retrieved vault context — stable per query) + dynamic tail
    (query + results) as the LAST user message. Provider prefix cache hits
    on the static system + docs; only the tail is billed at full price.
    """
    results_text = "\n\n".join(
        f"Source: {r.get('url', 'N/A')}\nTitle: {r.get('title', 'N/A')}\nContent: {str(r.get('content', ''))[:500]}"
        for r in results
    ) or "(no results found)"
    tail = prompts.dynamic_tail(
        f"Research query: {query}",
        f"Search results:\n{results_text}",
    )
    report, used = llm.chat(
        tier,
        [{"role": "user", "content": tail}],
        kind="research",
        docs=brain_context or None,
        max_tokens=800,
    )
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Keyless web research agent")
    ap.add_argument("--query", default="latest advances in local LLMs",
                    help="research query")
    ap.add_argument("--tier", default=os.getenv("AGENT_TIER", "flash"),
                    choices=sorted(llm.TIERS), help="LLM tier for synthesis")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--brain-context", action="store_true",
                    help="retrieve local vault context for the query (brain-as-context-service)")
    args = ap.parse_args()

    print(f"Searching: {args.query}")
    results = search_web(args.query, args.limit)
    print(f"Found {len(results)} results")
    brain_context = ""
    if args.brain_context:
        from _shared import brain_client
        print("Retrieving local brain context...")
        brain_context = brain_client.search(args.query)
        print(f"Brain context: {len(brain_context)} chars")
    report = synthesize_report(args.query, results, args.tier, brain_context)
    print("\n" + report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
