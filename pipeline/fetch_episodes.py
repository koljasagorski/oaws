"""Phase 1: OAWS-Episoden via RSS holen.

Feed-URL nicht raten -> ueber iTunes-Lookup aufloesen. Mit feedparser parsen.
Pro Episode: {guid, title, text, published_utc}. text = summary + content
gemerged und HTML-Entities dekodiert. Idempotent/inkrementell ueber guid.
"""
from __future__ import annotations

import html
import sys
from datetime import datetime, timezone

import feedparser
import requests

try:
    from .common import EPISODES, PODCAST_ID, load_json, save_json
except ImportError:  # pragma: no cover
    from common import EPISODES, PODCAST_ID, load_json, save_json

ITUNES_LOOKUP = "https://itunes.apple.com/lookup"


def resolve_feed_url() -> str:
    r = requests.get(ITUNES_LOOKUP,
                     params={"id": PODCAST_ID, "entity": "podcast"},
                     timeout=20)
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results or not results[0].get("feedUrl"):
        raise RuntimeError("Keine feedUrl ueber iTunes-Lookup gefunden")
    return results[0]["feedUrl"]


def _published_utc(entry) -> str | None:
    pp = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pp:
        return None
    return datetime(*pp[:6], tzinfo=timezone.utc).isoformat()


def _entry_text(entry) -> str:
    parts = [entry.get("summary", "")]
    for c in entry.get("content", []) or []:
        parts.append(c.get("value", ""))
    return html.unescape("\n".join(p for p in parts if p))


def _guid(entry) -> str:
    return entry.get("id") or entry.get("guid") or entry.get("link") or entry.get("title", "")


def main() -> None:
    feed_url = resolve_feed_url()
    print(f"fetch_episodes: feedUrl = {feed_url}", file=sys.stderr)
    feed = feedparser.parse(feed_url)

    existing = {e["guid"]: e for e in (load_json(EPISODES, default=[]) or [])}
    added = 0
    for entry in feed.entries:
        guid = _guid(entry)
        pub = _published_utc(entry)
        if not guid or not pub:
            continue
        rec = {
            "guid": guid,
            "title": entry.get("title", ""),
            "text": _entry_text(entry),
            "published_utc": pub,
        }
        if guid not in existing:
            added += 1
        existing[guid] = rec  # refresh text/title (Beschreibungen werden nachgepflegt)

    episodes = sorted(existing.values(), key=lambda e: e["published_utc"], reverse=True)
    save_json(EPISODES, episodes)
    print(f"fetch_episodes: {len(episodes)} Episoden total (+{added} neu) -> {EPISODES}")


if __name__ == "__main__":
    main()
