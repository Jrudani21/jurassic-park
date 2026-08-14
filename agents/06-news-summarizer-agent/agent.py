"""
News Summarizer Agent using AutoGen.

Fetches news articles and produces structured summaries with key insights.

Usage:
    python agent.py --topic "artificial intelligence"
    python agent.py --topic "climate change" --count 5
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _shared import llm  # noqa: E402 — shared client: tier failover + L1/L2 cache + L3 prefix

load_dotenv()

NEWS_API_KEY = os.getenv("NEWS_API_KEY")


def fetch_news(topic: str, count: int = 5) -> list[dict]:
    if not NEWS_API_KEY:
        # Return mock data if no API key
        return [
            {"title": f"Major development in {topic}", "description": f"Researchers announce breakthrough in {topic} field.", "url": "https://example.com/1", "source": {"name": "Tech News"}},
            {"title": f"{topic.title()} industry sees rapid growth", "description": f"New report shows {topic} adoption up 40% year-over-year.", "url": "https://example.com/2", "source": {"name": "Business Daily"}},
            {"title": f"Experts weigh in on {topic} challenges", "description": f"Leading experts discuss obstacles facing the {topic} space.", "url": "https://example.com/3", "source": {"name": "Science Weekly"}},
        ]

    url = f"https://newsapi.org/v2/everything?q={topic}&language=en&pageSize={count}&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    response = requests.get(url, timeout=10)
    data = response.json()
    return data.get("articles", [])


def summarize_news(topic: str, articles: list[dict]) -> str:
    articles_text = "\n\n".join(
        f"Title: {a['title']}\nSource: {a.get('source', {}).get('name', 'Unknown')}\nSummary: {a.get('description', 'N/A')}"
        for a in articles[:5]
    )

    tail = (
        f"Topic: {topic}\n\nArticles:\n{articles_text}"
    )
    response, used = llm.chat(
        "flash",
        [{"role": "user", "content": tail}],
        kind="news",
        max_tokens=800,
    )
    return response


def main():
    parser = argparse.ArgumentParser(description="News Summarizer Agent")
    parser.add_argument("--topic", default="artificial intelligence", help="News topic to search")
    parser.add_argument("--count", type=int, default=5, help="Number of articles to fetch")
    args = parser.parse_args()

    print(f"\n📰 Fetching news about: {args.topic}\n")
    articles = fetch_news(args.topic, args.count)
    print(f"✅ Found {len(articles)} articles")

    summary = summarize_news(args.topic, articles)

    print("\n" + "=" * 60)
    print(f"📋 NEWS BRIEFING: {args.topic.upper()}")
    print("=" * 60)
    print(summary)


if __name__ == "__main__":
    main()
