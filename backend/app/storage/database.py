import json
import sqlite3
from pathlib import Path
from typing import Any

from app.core.chat import ChatMessage, OrionReplyPayload
from app.core.config import settings
from app.core.trading_settings import TradingSettings, default_trading_settings

APP_SETTINGS_KEY = "app_settings"


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

    messages = [
        ChatMessage(
            id=row[0],
            thread_id=row[1],
            role=row[2],
            content=row[3],
            created_at=row[4],
        )
        for row in message_rows
    ]
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

    return (
        ChatMessage(
            id=user_row[0],
            thread_id=user_row[1],
            role=user_row[2],
            content=user_row[3],
            created_at=user_row[4],
        ),
        ChatMessage(
            id=orion_row[0],
            thread_id=orion_row[1],
            role=orion_row[2],
            content=orion_row[3],
            created_at=orion_row[4],
        ),
    )


def _serialize_settings(trading_settings: TradingSettings) -> str:
    payload: dict[str, Any] = trading_settings.model_dump()
    return json.dumps(payload)
