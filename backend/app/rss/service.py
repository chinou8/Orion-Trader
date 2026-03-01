import json
from datetime import datetime, timezone
from urllib.request import urlopen

import feedparser

from app.storage.database import create_news_item, get_active_rss_feeds


def fetch_all_active_feeds() -> int:
    created_total = 0
    for feed in get_active_rss_feeds():
        try:
            with urlopen(feed.url, timeout=10) as response:
                raw = response.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        created_total += parse_feed_content(feed.id, raw)
    return created_total


def parse_feed_content(feed_id: int, raw_content: str) -> int:
    parsed = feedparser.parse(raw_content)
    created = 0

    for entry in parsed.entries:
        title = str(getattr(entry, "title", "")).strip()
        link = str(getattr(entry, "link", "")).strip()
        entry_id = str(getattr(entry, "id", "")).strip()
        guid = entry_id or f"{link}|{title}"
        summary = str(getattr(entry, "summary", "")).strip()

        published = _extract_published(entry)
        raw_json = json.dumps(entry, default=str)

        inserted = create_news_item(
            feed_id=feed_id,
            guid=guid,
            title=title or "(untitled)",
            link=link,
            published_at=published,
            summary=summary,
            raw_json=raw_json,
        )
        if inserted:
            created += 1

    return created


def _extract_published(entry: object) -> str:
    published = str(getattr(entry, "published", "")).strip()
    if published:
        return published
    updated = str(getattr(entry, "updated", "")).strip()
    if updated:
        return updated
    return datetime.now(timezone.utc).isoformat()
