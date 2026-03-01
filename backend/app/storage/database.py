import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.core.chat import ChatMessage, OrionReplyPayload
from app.core.config import settings
from app.core.market import MarketBar
from app.core.proposal import (
    TradeProposal,
    TradeProposalActionRequest,
    TradeProposalCreateRequest,
    TradeProposalUpdateRequest,
)
from app.core.rss import NewsItem, RssFeed, RssFeedCreateRequest, RssFeedUpdateRequest
from app.core.simulator import (
    EquityCurvePoint,
    PerformanceSummary,
    PortfolioResponse,
    PortfolioState,
    Position,
    Reflection,
    SimulatedTrade,
)
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

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT NOT NULL,
                asset_type TEXT NOT NULL CHECK(asset_type IN ('EQUITY', 'ETF', 'BOND')),
                market TEXT NOT NULL,
                side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL', 'HOLD')),
                qty REAL NULL,
                notional_eur REAL NULL,
                order_type TEXT NOT NULL DEFAULT 'LIMIT' CHECK(order_type IN ('LIMIT')),
                limit_price REAL NULL,
                horizon_window TEXT NOT NULL,
                thesis_json TEXT NOT NULL,
                status TEXT NOT NULL CHECK(
                    status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'CANCELLED')
                ),
                approved_by TEXT NULL,
                approved_at TEXT NULL,
                notes TEXT NULL
            );
            """
        )


        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS simulated_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proposal_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL NOT NULL,
                ts TEXT NOT NULL,
                fees_eur REAL NOT NULL,
                slippage_bps REAL NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(proposal_id) REFERENCES trade_proposals(id) ON DELETE CASCADE
            );
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS portfolio_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                cash_eur REAL NOT NULL,
                equity_eur REAL NOT NULL,
                unrealized_pnl_eur REAL NOT NULL,
                realized_pnl_eur REAL NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                proposal_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                json_payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(proposal_id) REFERENCES trade_proposals(id) ON DELETE CASCADE
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


def list_trade_proposals(status: str | None = None, limit: int = 100) -> list[TradeProposal]:
    query = (
        "SELECT id, created_at, updated_at, symbol, asset_type, market, side, qty, notional_eur, "
        "order_type, limit_price, horizon_window, thesis_json, "
        "status, approved_by, approved_at, notes "
        "FROM trade_proposals"
    )
    params: list[Any] = []
    if status is not None:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    return [_row_to_trade_proposal(row) for row in rows]


def create_trade_proposal(payload: TradeProposalCreateRequest) -> TradeProposal:
    with sqlite3.connect(settings.db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO trade_proposals (
                symbol, asset_type, market, side, qty, notional_eur, order_type,
                limit_price, horizon_window, thesis_json, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                payload.symbol.upper(),
                payload.asset_type,
                payload.market,
                payload.side,
                payload.qty,
                payload.notional_eur,
                payload.order_type,
                payload.limit_price,
                payload.horizon_window,
                payload.thesis_json,
                "PENDING" if payload.asset_type == "BOND" else payload.status,
                payload.notes,
            ),
        )
        row = connection.execute(
            "SELECT id, created_at, updated_at, symbol, asset_type, market, side, qty, "
            "notional_eur, order_type, limit_price, horizon_window, thesis_json, "
            "status, approved_by, approved_at, notes "
            "FROM trade_proposals WHERE id = ?;",
            (cursor.lastrowid,),
        ).fetchone()
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to create proposal")
    return _row_to_trade_proposal(row)


def update_trade_proposal(proposal_id: int, payload: TradeProposalUpdateRequest) -> TradeProposal:
    current = _fetch_trade_proposal_row(proposal_id)
    if current is None:
        raise ValueError("proposal_not_found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return _row_to_trade_proposal(current)

    if current[4] == "BOND" and updates.get("status") not in (None, "PENDING"):
        raise ValueError("bond_status_locked")

    merged = {
        "qty": updates.get("qty", current[7]),
        "limit_price": updates.get("limit_price", current[10]),
        "notes": updates.get("notes", current[16]),
        "status": updates.get("status", current[13]),
    }

    with sqlite3.connect(settings.db_path) as connection:
        connection.execute(
            """
            UPDATE trade_proposals
            SET qty = ?,
                limit_price = ?,
                notes = ?,
                status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (merged["qty"], merged["limit_price"], merged["notes"], merged["status"], proposal_id),
        )
        row = _fetch_trade_proposal_row(proposal_id, connection)
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to update proposal")
    return _row_to_trade_proposal(row)


def approve_trade_proposal(proposal_id: int, payload: TradeProposalActionRequest) -> TradeProposal:
    current = _fetch_trade_proposal_row(proposal_id)
    if current is None:
        raise ValueError("proposal_not_found")

    with sqlite3.connect(settings.db_path) as connection:
        connection.execute(
            """
            UPDATE trade_proposals
            SET status = 'APPROVED',
                approved_by = ?,
                approved_at = CURRENT_TIMESTAMP,
                notes = COALESCE(?, notes),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (payload.approved_by, payload.notes, proposal_id),
        )
        row = _fetch_trade_proposal_row(proposal_id, connection)
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to approve proposal")
    return _row_to_trade_proposal(row)


def reject_trade_proposal(proposal_id: int, payload: TradeProposalActionRequest) -> TradeProposal:
    current = _fetch_trade_proposal_row(proposal_id)
    if current is None:
        raise ValueError("proposal_not_found")

    with sqlite3.connect(settings.db_path) as connection:
        connection.execute(
            """
            UPDATE trade_proposals
            SET status = 'REJECTED',
                notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (payload.notes, proposal_id),
        )
        row = _fetch_trade_proposal_row(proposal_id, connection)
        connection.commit()

    if row is None:
        raise RuntimeError("Failed to reject proposal")
    return _row_to_trade_proposal(row)




def execute_simulated_trade(
    proposal_id: int,
) -> tuple[TradeProposal, SimulatedTrade, PortfolioState, Reflection]:
    proposal_row = _fetch_trade_proposal_row(proposal_id)
    if proposal_row is None:
        raise ValueError("proposal_not_found")

    proposal = _row_to_trade_proposal(proposal_row)
    if proposal.status != "APPROVED":
        raise ValueError("proposal_not_approved")
    if proposal.asset_type not in {"EQUITY", "ETF"}:
        raise ValueError("unsupported_asset_type")

    qty = float(proposal.qty or 1.0)
    if qty <= 0:
        raise ValueError("invalid_qty")

    with sqlite3.connect(settings.db_path) as connection:
        bar_row = connection.execute(
            "SELECT close, ts FROM market_bars "
            "WHERE symbol = ? AND timeframe = '1d' "
            "ORDER BY ts DESC LIMIT 1;",
            (proposal.symbol.upper(),),
        ).fetchone()
        if bar_row is None:
            raise ValueError("market_data_missing")

        ref_price = float(bar_row[0])
        ts = str(bar_row[1])
        slippage_bps = get_trading_settings().simulator_slippage_bps
        fee = get_trading_settings().simulator_fee_per_trade_eur

        if proposal.side == "BUY":
            execution_price = ref_price * (1 + (slippage_bps / 10000))
            cash_delta = -(qty * execution_price) - fee
        elif proposal.side == "SELL":
            execution_price = ref_price * (1 - (slippage_bps / 10000))
            cash_delta = (qty * execution_price) - fee
        else:
            execution_price = ref_price
            cash_delta = -fee

        cursor = connection.execute(
            """
            INSERT INTO simulated_trades (
                proposal_id, symbol, side, qty, price, ts, fees_eur, slippage_bps, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'simulator');
            """,
            (
                proposal.id,
                proposal.symbol,
                proposal.side,
                qty,
                execution_price,
                ts,
                fee,
                slippage_bps,
            ),
        )

        connection.execute(
            """
            UPDATE trade_proposals
            SET status = 'EXECUTED',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?;
            """,
            (proposal.id,),
        )

        state = _compute_portfolio_state(connection, cash_delta)

        reflection_payload = _build_reflection_payload(proposal)
        reflection_text = reflection_payload["summary"]
        reflection_cursor = connection.execute(
            """
            INSERT INTO reflections (ts, proposal_id, text, json_payload)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?);
            """,
            (proposal.id, reflection_text, json.dumps(reflection_payload)),
        )

        trade_row = connection.execute(
            "SELECT id, proposal_id, symbol, side, qty, price, ts, fees_eur, "
            "slippage_bps, source, created_at "
            "FROM simulated_trades WHERE id = ?;",
            (cursor.lastrowid,),
        ).fetchone()
        proposal_row_updated = _fetch_trade_proposal_row(proposal.id, connection)
        reflection_row = connection.execute(
            "SELECT id, ts, proposal_id, text, json_payload, created_at "
            "FROM reflections WHERE id = ?;",
            (reflection_cursor.lastrowid,),
        ).fetchone()
        connection.commit()

    if trade_row is None or proposal_row_updated is None or reflection_row is None:
        raise RuntimeError("Failed to execute simulated trade")

    return (
        _row_to_trade_proposal(proposal_row_updated),
        _row_to_simulated_trade(trade_row),
        state,
        _row_to_reflection(reflection_row),
    )


def list_simulated_trades(limit: int = 200) -> list[SimulatedTrade]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            "SELECT id, proposal_id, symbol, side, qty, price, ts, fees_eur, "
            "slippage_bps, source, created_at "
            "FROM simulated_trades ORDER BY id DESC LIMIT ?;",
            (limit,),
        ).fetchall()
    return [_row_to_simulated_trade(row) for row in rows]


def list_reflections(limit: int = 200) -> list[Reflection]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            "SELECT id, ts, proposal_id, text, json_payload, created_at "
            "FROM reflections ORDER BY id DESC LIMIT ?;",
            (limit,),
        ).fetchall()
    return [_row_to_reflection(row) for row in rows]




def get_equity_curve(limit: int = 500) -> list[EquityCurvePoint]:
    with sqlite3.connect(settings.db_path) as connection:
        rows = connection.execute(
            """
            SELECT ts, equity_eur, cash_eur, realized_pnl_eur, unrealized_pnl_eur
            FROM portfolio_state
            ORDER BY ts DESC, id DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

    points = [
        EquityCurvePoint(
            ts=str(row[0]),
            equity_eur=float(row[1]),
            cash_eur=float(row[2]),
            realized_pnl_eur=float(row[3]),
            unrealized_pnl_eur=float(row[4]),
        )
        for row in rows
    ]
    return list(reversed(points))


def get_performance_summary() -> PerformanceSummary:
    with sqlite3.connect(settings.db_path) as connection:
        current = connection.execute(
            "SELECT equity_eur FROM portfolio_state ORDER BY id DESC LIMIT 1;"
        ).fetchone()
        first = connection.execute(
            "SELECT equity_eur FROM portfolio_state ORDER BY id ASC LIMIT 1;"
        ).fetchone()
        trades_row = connection.execute("SELECT COUNT(*) FROM simulated_trades;").fetchone()

    settings_payload = get_trading_settings()
    current_equity = (
        float(current[0])
        if current is not None
        else settings_payload.simulator_initial_cash_eur
    )
    starting_equity = (
        float(first[0])
        if first is not None
        else settings_payload.simulator_initial_cash_eur
    )
    trades_count = int(trades_row[0]) if trades_row is not None else 0
    pnl_total = current_equity - settings_payload.simulator_initial_cash_eur

    if starting_equity > 0:
        perf_pct = ((current_equity / starting_equity) - 1) * 100
    else:
        perf_pct = 0.0

    return PerformanceSummary(
        current_equity_eur=current_equity,
        performance_since_start_pct=perf_pct,
        trades_count=trades_count,
        pnl_total_eur=pnl_total,
    )
def get_portfolio() -> PortfolioResponse:
    with sqlite3.connect(settings.db_path) as connection:
        state = _compute_portfolio_state(connection, cash_delta=0.0, persist=False)
        positions = _compute_positions(connection)
    return PortfolioResponse(state=state, positions=positions)


def _compute_portfolio_state(
    connection: sqlite3.Connection,
    cash_delta: float,
    persist: bool = True,
) -> PortfolioState:
    last_state_row = connection.execute(
        "SELECT id, ts, cash_eur, equity_eur, unrealized_pnl_eur, realized_pnl_eur, created_at "
        "FROM portfolio_state ORDER BY id DESC LIMIT 1;"
    ).fetchone()

    if last_state_row is None:
        cash = get_trading_settings().simulator_initial_cash_eur
        realized = 0.0
    else:
        cash = float(last_state_row[2])
        realized = float(last_state_row[5])

    cash += cash_delta
    positions = _compute_positions(connection)
    unrealized = sum(p.unrealized_pnl_eur for p in positions)
    market_value = sum(p.market_value for p in positions)
    equity = cash + market_value

    if persist:
        cursor = connection.execute(
            """
            INSERT INTO portfolio_state (
                ts, cash_eur, equity_eur, unrealized_pnl_eur, realized_pnl_eur
            )
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?);
            """,
            (cash, equity, unrealized, realized),
        )
        row = connection.execute(
            "SELECT id, ts, cash_eur, equity_eur, unrealized_pnl_eur, realized_pnl_eur, created_at "
            "FROM portfolio_state WHERE id = ?;",
            (cursor.lastrowid,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to persist portfolio state")
        return _row_to_portfolio_state(row)

    row = (
        0,
        "",
        cash,
        equity,
        unrealized,
        realized,
        "",
    )
    return _row_to_portfolio_state(row)


def _compute_positions(connection: sqlite3.Connection) -> list[Position]:
    rows = connection.execute(
        "SELECT symbol, side, qty, price FROM simulated_trades ORDER BY id ASC;"
    ).fetchall()

    books: dict[str, dict[str, float]] = {}
    for symbol, side, qty, price in rows:
        book = books.setdefault(symbol, {"qty": 0.0, "cost": 0.0})
        q = float(qty)
        p = float(price)
        if side == "BUY":
            book["cost"] += q * p
            book["qty"] += q
        elif side == "SELL":
            if book["qty"] > 0:
                avg = book["cost"] / book["qty"]
            else:
                avg = p
            book["cost"] -= q * avg
            book["qty"] -= q

    positions: list[Position] = []
    for symbol, book in books.items():
        qty = book["qty"]
        if qty <= 0:
            continue
        avg_price = book["cost"] / qty if qty else 0.0
        market_row = connection.execute(
            "SELECT close FROM market_bars "
            "WHERE symbol = ? AND timeframe = '1d' "
            "ORDER BY ts DESC LIMIT 1;",
            (symbol,),
        ).fetchone()
        market_price = float(market_row[0]) if market_row else avg_price
        market_value = qty * market_price
        unrealized = (market_price - avg_price) * qty
        positions.append(
            Position(
                symbol=symbol,
                qty=qty,
                avg_price=avg_price,
                market_price=market_price,
                market_value=market_value,
                unrealized_pnl_eur=unrealized,
            )
        )

    return positions


def _build_reflection_payload(proposal: TradeProposal) -> dict[str, Any]:
    try:
        thesis = json.loads(proposal.thesis_json or "{}")
    except json.JSONDecodeError:
        thesis = {}

    horizon = proposal.horizon_window
    objective_consistency = horizon in {"2-5 jours", "5-15 jours", "1-3 mois", "5-10 jours"}
    has_indicators = any(k in thesis for k in ["horizon_hint", "rsi14", "volatility"])
    has_news = bool(thesis.get("news_refs"))

    improvements: list[str] = [
        "Attendre une confirmation de tendance avant exécution.",
        "Ajuster le sizing au risque par trade.",
    ]

    return {
        "horizon_window": horizon,
        "objective_2_5_consistent": objective_consistency,
        "indicators_present": has_indicators,
        "news_present": has_news,
        "improvements": improvements,
        "summary": (
            f"Reflection for proposal #{proposal.id}: vérifier confirmation, "
            "sizing et discipline d'exécution."
        ),
    }


def _fetch_trade_proposal_row(
    proposal_id: int,
    connection: sqlite3.Connection | None = None,
) -> tuple[Any, ...] | None:
    query = (
        "SELECT id, created_at, updated_at, symbol, asset_type, market, side, qty, notional_eur, "
        "order_type, limit_price, horizon_window, thesis_json, "
        "status, approved_by, approved_at, notes "
        "FROM trade_proposals WHERE id = ?;"
    )
    if connection is not None:
        return connection.execute(query, (proposal_id,)).fetchone()

    with sqlite3.connect(settings.db_path) as conn:
        return conn.execute(query, (proposal_id,)).fetchone()


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


def _row_to_trade_proposal(row: tuple[Any, ...]) -> TradeProposal:
    return TradeProposal(
        id=row[0],
        created_at=row[1],
        updated_at=row[2],
        symbol=row[3],
        asset_type=row[4],
        market=row[5],
        side=row[6],
        qty=row[7],
        notional_eur=row[8],
        order_type=row[9],
        limit_price=row[10],
        horizon_window=row[11],
        thesis_json=row[12],
        status=row[13],
        approved_by=row[14],
        approved_at=row[15],
        notes=row[16],
    )



def _row_to_simulated_trade(row: tuple[Any, ...]) -> SimulatedTrade:
    return SimulatedTrade(
        id=row[0],
        proposal_id=row[1],
        symbol=row[2],
        side=row[3],
        qty=float(row[4]),
        price=float(row[5]),
        ts=row[6],
        fees_eur=float(row[7]),
        slippage_bps=float(row[8]),
        source=row[9],
        created_at=row[10],
    )


def _row_to_portfolio_state(row: tuple[Any, ...]) -> PortfolioState:
    return PortfolioState(
        id=row[0],
        ts=row[1],
        cash_eur=float(row[2]),
        equity_eur=float(row[3]),
        unrealized_pnl_eur=float(row[4]),
        realized_pnl_eur=float(row[5]),
        created_at=row[6],
    )


def _row_to_reflection(row: tuple[Any, ...]) -> Reflection:
    return Reflection(
        id=row[0],
        ts=row[1],
        proposal_id=row[2],
        text=row[3],
        json_payload=row[4],
        created_at=row[5],
    )

def _serialize_settings(trading_settings: TradingSettings) -> str:
    payload: dict[str, Any] = trading_settings.model_dump()
    return json.dumps(payload)
