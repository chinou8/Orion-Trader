from pathlib import Path

from app.core.config import settings
from app.core.rss import RssFeedCreateRequest, RssFeedUpdateRequest
from app.rss.service import parse_feed_content
from app.storage.database import (
    create_rss_feed,
    get_latest_news,
    get_rss_feeds,
    init_db,
    update_rss_feed,
)


def test_rss_feed_crud_without_network(tmp_path: Path) -> None:
    original_db_path = settings.db_path
    settings.db_path = tmp_path / "rss-test.db"
    try:
        init_db()

        created = create_rss_feed(
            RssFeedCreateRequest(
                name="Mock Feed",
                url="https://example.org/rss.xml",
                is_active=True,
            )
        )
        assert created.name == "Mock Feed"
        assert created.is_active is True

        updated = update_rss_feed(
            created.id,
            RssFeedUpdateRequest(name="Mock Feed Renamed", is_active=False),
        )
        assert updated.name == "Mock Feed Renamed"
        assert updated.is_active is False

        all_feeds = get_rss_feeds()
        assert any(feed.id == created.id for feed in all_feeds)
    finally:
        settings.db_path = original_db_path


def test_parse_mock_rss_creates_news_item(tmp_path: Path) -> None:
    original_db_path = settings.db_path
    settings.db_path = tmp_path / "rss-parse-test.db"
    try:
        init_db()
        feed = create_rss_feed(
            RssFeedCreateRequest(
                name="Fixture Feed",
                url="https://example.org/fixture.xml",
                is_active=True,
            )
        )

        raw_feed = Path("backend/tests/fixtures/sample_rss.xml").read_text(encoding="utf-8")
        created_count = parse_feed_content(feed.id, raw_feed)
        assert created_count == 1

        news_items = get_latest_news(limit=10)
        assert len(news_items) >= 1
        assert news_items[0].title == "ECB keeps rates unchanged"
    finally:
        settings.db_path = original_db_path
