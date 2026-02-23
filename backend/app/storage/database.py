import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.core.chat import ChatMessage, OrionReplyPayload
from app.core.config import settings
from app.core.market import MarketBar
from app.core.rss import NewsItem, RssFeed, RssFeedCreateRequest, RssFeedUpdateRequest
from app.core.trading_settings import TradingSettings, default_trading_settings
from app.core.watchlist import WatchlistCreateRequest, WatchlistItem, WatchlistUpdateRequest

APP_SETTINGS_KEY = "app_settings"
SYMBOL_REGEX = re.compile(r"\b[A-Z]{1,6}(?:\.[A-Z]{1,4})?\b")
DEFAULT_RSS_FEEDS: list[tuple[str, str, bool]] = [
    (
        "AMF",
        "https://www.amf-france.org/fr/actualites-publications/actualites/rss.xml?item=all",
        False,
    ),
    ("ECB Press Releases", "https://www.ecb.europa.eu/press/rss/press.xml", True),
    ("DG Trésor", "https://www.tresor.economie.gouv.fr/RSS", False),
    ("Eurostat", "https://ec.europa.eu/eurostat/web/main/rss", False),
]


def init_db() -> None:
    db_path: Path = settings.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES ('app_name', 'orion-trader');
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO settings (key, value)
            VALUES (?, ?);
            """,
            (APP_SETTINGS_KEY, _serialize_settings(default_trading_settings())),
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role in ('user', 'orion')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(thread_id) REFERENCES chat_threads(id) ON DELETE CASCADE
            );
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                asset_type TEXT NOT NULL DEFAULT 'EQUITY',
                market TEXT NOT NULL DEFAULT 'EU',
                notes TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rss_feeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER NOT NULL,
                guid TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT NOT NULL,
                published_at TEXT NOT NULL,
                summary TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(feed_id, guid),
                FOREIGN KEY(feed_id) REFERENCES rss_feeds(id) ON DELETE CASCADE
            );
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS market_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                ts TEXT NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, timeframe, ts, source)
            );
            """
        )

        for name, url, is_active in DEFAULT_RSS_FEEDS:
            connection.execute(
                """
                INSERT OR IGNORE INTO rss_feeds (name, url, is_active)
                VALUES (?, ?, ?);
                """,
                (name, url, int(is_active)),
            )

        connection.commit()


def get_trading_settings() -> TradingSettings:
    with sqlite3.connect(settings.db_path) as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?;",
            (APP_SETTINGS_KEY,),
        ).fetchone()

    if row is None:
        defaults = default_trading_settings()
        save_trading_settings(defaults)
        return defaults

    return TradingSettings.model_validate(json.loads(row[0]))


def save_trading_settings(trading_settings: TradingSettings) -> TradingSettings:
    with sqlite3.connect(settings.db_path) as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET
              value = excluded.value,
              updated_at = CURRENT_TIMESTAMP;
            """,
            (APP_SETTINGS_KEY, _serialize_settings(trading_settings)),
        )
        connection.commit()

    return trading_settings


def create_chat_thread(title: str | None = None) -> tuple[int, str]:
    thread_title = title.strip() if title and title.strip() else "Orion Thread"
    with sqlite3.connect(settings.db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO chat_threads (title) VALUES (?);",
            (thread_title,),
        )
        connection.commit()
        thread_id = cursor.lastrowid
    if thread_id is None:
        raise RuntimeError("Failed to create chat thread")
    return thread_id, thread_title


def thread_exists(thread_id: int) -> bool:
    with sqlite3.connect(settings.db_path) as connection:
        row = connection.execute(
            "SELECT id FROM chat_threads WHERE id = ?;",
            (thread_id,),
        ).fetchone()
    return row is not None


def get_chat_thread(thread_id: int) -> tuple[str, list[ChatMessage]]:
    with sqlite3.connect(settings.db_path) as connection:
        thread_row = connection.execute(
            "SELECT title FROM chat_threads WHERE id = ?;",
            (thread_id,),
        ).fetchone()

        if thread_row is None:
            raise ValueError("thread_not_found")

        message_rows = connection.execute(
            """
            SELECT id, thread_id, role, content, created_at
            FROM chat_messages
            WHERE thread_id = ?
            ORDER BY id ASC;
            """,
            (thread_id,),
        ).fetchall()

    messages = [_row_to_chat_message(row) for row in message_rows]
    return str(thread_row[0]), messages


def add_chat_exchange(
    thread_id: int,
    user_content: str,
    orion_reply: OrionReplyPayload,
) -> tuple[ChatMessage, ChatMessage]:
    if not thread_exists(thread_id):
        raise ValueError("thread_not_found")

    with sqlite3.connect(settings.db_path) as connection:
        user_cursor = connection.execute(
            "INSERT INTO chat_messages (thread_id, role, content) VALUES (?, 'user', ?);",
            (thread_id, user_content),
        )
        orion_cursor = connection.execute(
            "INSERT INTO chat_messages (thread_id, role, content) VALUES (?, 'orion', ?);",
            (thread_id, json.dumps(orion_reply.model_dump())),
        )

        user_row = connection.execute(
            "SELECT id, thread_id, role, content, created_at FROM chat_messages WHERE id = ?;",
            (user_cursor.lastrowid,),
        ).fetchone()
        orion_row = connection.execute(
            "SELECT id, thread_id, role, content, created_at FROM chat_messages WHERE id = ?;",
            (orion_cursor.lastrowid,),
        ).fetchone()
        connection.commit()

    if user_row is None or orion_row is None:
        raise RuntimeError("Failed to persist chat messages")

    return _row_to_chat_message(user_row), _row_to_chat_message(orion_row)


def get_watchlist_items(active_only: bool = True, limit: int | None = None) -> list[WatchlistItem]:
    query = (
        "SELECT id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at "
        "FROM watchlist_items"
    )
    params: list[Any] = []

    if active_only:
        query += " WHERE is_active = 1"

    query += " ORDER BY updated_at DESC, id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    return [_row_to_watchlist_item(row) for row in rows]


def create_watchlist_item(payload: WatchlistCreateRequest) -> WatchlistItem:
    symbol = payload.symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol_required")

    with sqlite3.connect(settings.db_path) as connection:
        existing = connection.execute(
            "SELECT id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at "
            "FROM watchlist_items WHERE symbol = ? AND is_active = 1 LIMIT 1;",
            (symbol,),
        ).fetchone()
        if existing is not None:
            return _row_to_watchlist_item(existing)

        cursor = connection.execute(
            """
            INSERT INTO watchlist_items (symbol, name, asset_type, market, notes, is_active)
            VALUES (?, ?, ?, ?, ?, 1);
            """,
            (symbol, payload.name, payload.asset_type, payload.market, payload.notes),
        )
        row = connection.execute(
            "SELECT id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at "
            "FROM watchlist_items WHERE id = ?;",
            (cursor.lastrowid,),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to create watchlist item")

    return _row_to_watchlist_item(row)


def update_watchlist_item(item_id: int, payload: WatchlistUpdateRequest) -> WatchlistItem:
    current = _fetch_watchlist_row(item_id)
    if current is None:
        raise ValueError("watchlist_not_found")

    updates = payload.model_dump(exclude_unset=True)
    if "symbol" in updates and updates["symbol"] is not None:
        updates["symbol"] = updates["symbol"].strip().upper()

    merged = {
        "symbol": updates.get("symbol", current[1]),
        "name": updates.get("name", current[2]),
        "asset_type": updates.get("asset_type", current[3]),
        "market": updates.get("market", current[4]),
        "notes": updates.get("notes", current[5]),
        "is_active": updates.get("is_active", bool(current[6])),
    }

    with sqlite3.connect(settings.db_path) as connection:
        connection.execute(
            """
            UPDATE watchlist_items
            SET symbol = ?,
                name = ?,
                asset_type = ?,
                market = ?,
                notes = ?,
                is_active = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (
                merged["symbol"],
                merged["name"],
                merged["asset_type"],
                merged["market"],
                merged["notes"],
                int(bool(merged["is_active"])),
                item_id,
            ),
        )
        row = connection.execute(
            "SELECT id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at "
            "FROM watchlist_items WHERE id = ?;",
            (item_id,),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to update watchlist item")

    return _row_to_watchlist_item(row)


def soft_delete_watchlist_item(item_id: int) -> WatchlistItem:
    return update_watchlist_item(item_id, WatchlistUpdateRequest(is_active=False))


def create_watchlist_items_from_requests(watch_requests: list[str]) -> list[WatchlistItem]:
    created: list[WatchlistItem] = []
    seen: set[str] = set()

    for request in watch_requests:
        symbols = extract_symbols(request)
        for symbol in symbols:
            if symbol in seen:
                continue
            seen.add(symbol)
            existing = get_watchlist_item_by_symbol(symbol)
            if existing and existing.is_active:
                continue
            item = create_watchlist_item(
                WatchlistCreateRequest(
                    symbol=symbol,
                    notes=f"Created from Orion chat request: {request[:120]}",
                )
            )
            created.append(item)

    return created


def extract_symbols(text: str) -> list[str]:
    return [match.group(0).upper() for match in SYMBOL_REGEX.finditer(text)]


def get_watchlist_item_by_symbol(symbol: str) -> WatchlistItem | None:
    with sqlite3.connect(settings.db_path) as connection:
        row = connection.execute(
            "SELECT id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at "
            "FROM watchlist_items WHERE symbol = ? ORDER BY id DESC LIMIT 1;",
            (symbol.upper(),),
        ).fetchone()

    if row is None:
        return None
    return _row_to_watchlist_item(row)


def get_rss_feeds() -> list[RssFeed]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            "SELECT id, name, url, is_active, created_at, updated_at "
            "FROM rss_feeds ORDER BY id ASC;"
        ).fetchall()
    return [_row_to_rss_feed(row) for row in rows]


def get_active_rss_feeds() -> list[RssFeed]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, name, url, is_active, created_at, updated_at
            FROM rss_feeds
            WHERE is_active = 1
            ORDER BY id ASC;
            """
        ).fetchall()
    return [_row_to_rss_feed(row) for row in rows]


def create_rss_feed(payload: RssFeedCreateRequest) -> RssFeed:
    with sqlite3.connect(settings.db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO rss_feeds (name, url, is_active) VALUES (?, ?, ?);",
            (payload.name.strip(), payload.url.strip(), int(payload.is_active)),
        )
        row = connection.execute(
            "SELECT id, name, url, is_active, created_at, updated_at FROM rss_feeds WHERE id = ?;",
            (cursor.lastrowid,),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to create rss feed")
    return _row_to_rss_feed(row)


def update_rss_feed(feed_id: int, payload: RssFeedUpdateRequest) -> RssFeed:
    with sqlite3.connect(settings.db_path) as connection:
        current = connection.execute(
            "SELECT id, name, url, is_active, created_at, updated_at FROM rss_feeds WHERE id = ?;",
            (feed_id,),
        ).fetchone()
        if current is None:
            raise ValueError("feed_not_found")

        name = payload.name if payload.name is not None else current[1]
        is_active = int(payload.is_active) if payload.is_active is not None else int(current[3])

        connection.execute(
            """
            UPDATE rss_feeds
            SET name = ?, is_active = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (name, is_active, feed_id),
        )
        row = connection.execute(
            "SELECT id, name, url, is_active, created_at, updated_at FROM rss_feeds WHERE id = ?;",
            (feed_id,),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to update rss feed")
    return _row_to_rss_feed(row)


def create_news_item(
    feed_id: int,
    guid: str,
    title: str,
    link: str,
    published_at: str,
    summary: str,
    raw_json: str,
) -> bool:
    with sqlite3.connect(settings.db_path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO news_items (
                feed_id, guid, title, link, published_at, summary, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (feed_id, guid, title, link, published_at, summary, raw_json),
        )
        connection.commit()
        return cursor.rowcount > 0


def get_latest_news(limit: int = 50) -> list[NewsItem]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            """
            SELECT n.id, n.feed_id, n.guid, n.title, n.link, n.published_at, n.summary, n.raw_json,
                   n.created_at, f.name
            FROM news_items n
            JOIN rss_feeds f ON f.id = n.feed_id
            ORDER BY n.published_at DESC, n.id DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

    return [_row_to_news_item(row) for row in rows]


def insert_market_bars(
    symbol: str,
    timeframe: str,
    source: str,
    bars: list[dict[str, float | str]],
) -> int:
    inserted = 0
    with sqlite3.connect(settings.db_path) as connection:
        for bar in bars:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO market_bars (
                    symbol, timeframe, ts, open, high, low, close, volume, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    symbol.upper(),
                    timeframe,
                    str(bar["ts"]),
                    float(bar["open"]),
                    float(bar["high"]),
                    float(bar["low"]),
                    float(bar["close"]),
                    float(bar["volume"]),
                    source,
                ),
            )
            if cursor.rowcount > 0:
                inserted += 1
        connection.commit()
    return inserted


def get_market_bars(symbol: str, timeframe: str = "1d", limit: int = 200) -> list[MarketBar]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, symbol, timeframe, ts, open, high, low, close, volume, source, created_at
            FROM market_bars
            WHERE symbol = ? AND timeframe = ?
            ORDER BY ts DESC
            LIMIT ?;
            """,
            (symbol.upper(), timeframe, limit),
        ).fetchall()
    return [_row_to_market_bar(row) for row in rows]


def get_market_closes(symbol: str, timeframe: str = "1d", limit: int = 250) -> list[float]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            """
            SELECT close
            FROM market_bars
            WHERE symbol = ? AND timeframe = ?
            ORDER BY ts ASC
            LIMIT ?;
            """,
            (symbol.upper(), timeframe, limit),
        ).fetchall()
    return [float(row[0]) for row in rows]


def get_active_watchlist_symbols() -> list[str]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            "SELECT symbol FROM watchlist_items WHERE is_active = 1 ORDER BY id ASC;"
        ).fetchall()
    return [str(row[0]) for row in rows]


def _fetch_watchlist_row(item_id: int) -> tuple[Any, ...] | None:
    with sqlite3.connect(settings.db_path) as connection:
        return connection.execute(
            "SELECT id, symbol, name, asset_type, market, notes, is_active, created_at, updated_at "
            "FROM watchlist_items WHERE id = ?;",
            (item_id,),
        ).fetchone()


def _row_to_chat_message(row: tuple[Any, ...]) -> ChatMessage:
    return ChatMessage(
        id=row[0],
        thread_id=row[1],
        role=row[2],
        content=row[3],
        created_at=row[4],
    )


def _row_to_watchlist_item(row: tuple[Any, ...]) -> WatchlistItem:
    return WatchlistItem(
        id=row[0],
        symbol=row[1],
        name=row[2],
        asset_type=row[3],
        market=row[4],
        notes=row[5],
        is_active=bool(row[6]),
        created_at=row[7],
        updated_at=row[8],
    )


def _row_to_rss_feed(row: tuple[Any, ...]) -> RssFeed:
    return RssFeed(
        id=row[0],
        name=row[1],
        url=row[2],
        is_active=bool(row[3]),
        created_at=row[4],
        updated_at=row[5],
    )


def _row_to_news_item(row: tuple[Any, ...]) -> NewsItem:
    return NewsItem(
        id=row[0],
        feed_id=row[1],
        guid=row[2],
        title=row[3],
        link=row[4],
        published_at=row[5],
        summary=row[6],
        raw_json=row[7],
        created_at=row[8],
        feed_name=row[9],
    )


def _row_to_market_bar(row: tuple[Any, ...]) -> MarketBar:
    return MarketBar(
        id=row[0],
        symbol=row[1],
        timeframe=row[2],
        ts=row[3],
        open=float(row[4]),
        high=float(row[5]),
        low=float(row[6]),
        close=float(row[7]),
        volume=float(row[8]),
        source=row[9],
        created_at=row[10],
    )


def _serialize_settings(trading_settings: TradingSettings) -> str:
    payload: dict[str, Any] = trading_settings.model_dump()
    return json.dumps(payload)
