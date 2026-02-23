import json
import sqlite3
from pathlib import Path
from typing import Any

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


def _serialize_settings(trading_settings: TradingSettings) -> str:
    payload: dict[str, Any] = trading_settings.model_dump()
    return json.dumps(payload)
