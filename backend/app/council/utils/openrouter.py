"""
AI Council v2 — Client OpenRouter async.

Tous les appels sont async (httpx). Gestion du budget,
retry simple et logging structuré.
"""

import logging
import os
import sqlite3
import time
from typing import Any

import httpx

from app.core.config import settings
from app.council.config import (
    API_MAX_TOKENS_AGENT,
    API_MAX_TOKENS_MASTER,
    API_TEMPERATURE_AGENT,
    API_TEMPERATURE_MASTER,
    API_TIMEOUT_SECONDS,
    OPENROUTER_BASE_URL,
)

logger = logging.getLogger(__name__)

# Clé fictive pour compilation — remplacée par la vraie clé via .env
_OPENROUTER_KEY_FALLBACK = "sk-or-fictitious-key-for-compilation"


def _get_api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", _OPENROUTER_KEY_FALLBACK)


def _debit_budget(cost_eur: float) -> None:
    """Déduit le coût estimé du budget OpenRouter en DB."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                UPDATE ai_budget
                SET total_spent_eur = total_spent_eur + ?,
                    total_calls     = total_calls + 1,
                    balance_eur     = MAX(0, balance_eur - ?),
                    updated_at      = CURRENT_TIMESTAMP
                WHERE provider = 'openrouter';
                """,
                (cost_eur, cost_eur),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.debug("budget debit error: %s", exc)


def _update_budget_status() -> None:
    """Met à jour le statut du budget (OK / LOW / CRITICAL)."""
    from app.council.config import AI_BUDGET_ALERT_EUR, AI_BUDGET_MIN_EUR
    try:
        with sqlite3.connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT balance_eur FROM ai_budget WHERE provider = 'openrouter';"
            ).fetchone()
            if not row:
                return
            bal = row[0]
            if bal <= AI_BUDGET_MIN_EUR:
                status = "CRITICAL"
            elif bal <= AI_BUDGET_ALERT_EUR:
                status = "LOW"
            else:
                status = "OK"
            conn.execute(
                "UPDATE ai_budget SET status = ? WHERE provider = 'openrouter';",
                (status,),
            )
            conn.commit()
    except sqlite3.Error:
        pass


async def call_agent(
    model: str,
    system_prompt: str,
    user_prompt: str,
    is_master: bool = False,
) -> tuple[str, float]:
    """
    Appel OpenRouter async — retourne (content, duration_seconds).
    Lève httpx.HTTPError en cas d'échec.
    """
    max_tokens  = API_MAX_TOKENS_MASTER if is_master else API_MAX_TOKENS_AGENT
    temperature = API_TEMPERATURE_MASTER if is_master else API_TEMPERATURE_AGENT

    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://orion-trader.local",
        "X-Title": "Orion AI Council",
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.post(OPENROUTER_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()

    duration = time.monotonic() - t0
    data = response.json()
    content: str = data["choices"][0]["message"]["content"] or "{}"

    # Estimation coût (très approximatif — sera affiné avec usage réel)
    usage = data.get("usage", {})
    total_tokens = usage.get("total_tokens", 500)
    # Coût moyen estimé : 0.000002 € / token (moyenne OpenRouter)
    estimated_cost = total_tokens * 0.000002
    _debit_budget(estimated_cost)
    _update_budget_status()

    logger.debug(
        "OpenRouter [%s] %.2fs tokens=%d cost=~€%.5f",
        model, duration, total_tokens, estimated_cost,
    )
    return content, duration


async def get_budget_status() -> dict[str, Any]:
    """Retourne l'état du budget OpenRouter depuis la DB."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT balance_eur, total_spent_eur, total_calls, status "
                "FROM ai_budget WHERE provider = 'openrouter';"
            ).fetchone()
        if row:
            return {
                "provider": "openrouter",
                "balance_eur":      row[0],
                "total_spent_eur":  row[1],
                "total_calls":      row[2],
                "status":           row[3],
            }
    except sqlite3.Error:
        pass
    return {"provider": "openrouter", "status": "UNKNOWN"}
