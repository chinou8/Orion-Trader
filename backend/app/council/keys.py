"""
AI Council v2 — Gestion des clés API.

Priorité de résolution pour chaque clé :
  1. Valeur en DB (table council_config) — saisie depuis le dashboard
  2. Variable d'environnement (OS env / .env)
  3. Clé fictive pour compilation

Fonctions publiques :
  get_key(name)              → str
  set_key(name, value)       → None
  get_keys_status()          → dict  (clé set ou non, sans exposer la valeur)
"""

import os
import sqlite3

from app.core.config import settings

_FICTITIOUS = {
    "openrouter_api_key": "sk-or-fictitious-key-for-compilation",
    "xai_api_key":        "xai-fictitious-key-for-compilation",
}
_ENV_NAMES = {
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "xai_api_key":        "XAI_API_KEY",
}


def get_key(name: str) -> str:
    """Retourne la clé API selon l'ordre de priorité DB → env → fictive."""
    # 1. DB
    try:
        with sqlite3.connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM council_config WHERE key = ?", (name,)
            ).fetchone()
        if row and row[0]:
            return row[0]
    except sqlite3.Error:
        pass

    # 2. Env
    env_val = os.environ.get(_ENV_NAMES.get(name, ""), "")
    if env_val:
        return env_val

    # 3. Fictive
    return _FICTITIOUS.get(name, "")


def set_key(name: str, value: str) -> None:
    """Persiste la clé API en DB (valeur vide = effacement)."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                INSERT INTO council_config (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, value),
            )
            conn.commit()
    except sqlite3.Error as exc:
        raise RuntimeError(f"council_config write error: {exc}") from exc


def get_keys_status() -> dict:
    """
    Retourne le statut des clés sans exposer leur valeur.
    Indique aussi si la clé vient de la DB ou de l'env.
    """
    result = {}
    for name, env_name in _ENV_NAMES.items():
        db_val  = _read_db(name)
        env_val = os.environ.get(env_name, "")
        is_set  = bool(db_val or env_val)
        source  = "db" if db_val else ("env" if env_val else "none")
        result[name] = {"set": is_set, "source": source}
    return result


def _read_db(name: str) -> str:
    try:
        with sqlite3.connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM council_config WHERE key = ?", (name,)
            ).fetchone()
        return row[0] if row and row[0] else ""
    except sqlite3.Error:
        return ""
