"""
AI Council v2 — Client xAI (Grok) async.

Slot 3 (News/Sentiment) utilise xAI directement.
API compatible OpenAI — même format de payload.
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
    API_TEMPERATURE_AGENT,
    API_TIMEOUT_SECONDS,
    XAI_BASE_URL,
)

logger = logging.getLogger(__name__)

def _get_api_key() -> str:
    from app.council.keys import get_key
    return get_key("xai_api_key")


def _debit_xai_budget(cost_eur: float) -> None:
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                UPDATE ai_budget
                SET total_spent_eur = total_spent_eur + ?,
                    total_calls     = total_calls + 1,
                    balance_eur     = MAX(0, balance_eur - ?),
                    updated_at      = CURRENT_TIMESTAMP
                WHERE provider = 'xai';
                """,
                (cost_eur, cost_eur),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.debug("xai budget debit error: %s", exc)


def _update_xai_budget_status() -> None:
    from app.council.config import XAI_BUDGET_MIN_EUR
    try:
        with sqlite3.connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT balance_eur FROM ai_budget WHERE provider = 'xai';"
            ).fetchone()
            if not row:
                return
            status = "CRITICAL" if row[0] <= XAI_BUDGET_MIN_EUR else "OK"
            conn.execute(
                "UPDATE ai_budget SET status = ? WHERE provider = 'xai';",
                (status,),
            )
            conn.commit()
    except sqlite3.Error:
        pass


async def call_grok(
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, float]:
    """
    Appel xAI async — retourne (content, duration_seconds).
    Lève httpx.HTTPError en cas d'échec.
    """
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type":  "application/json",
    }

    payload: dict[str, Any] = {
        "model": model.replace("x-ai/", ""),   # xAI n'utilise pas le préfixe provider
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  API_MAX_TOKENS_AGENT,
        "temperature": API_TEMPERATURE_AGENT,
    }

    t0 = time.monotonic()
    async with httpx.AsyncClient(timeout=API_TIMEOUT_SECONDS) as client:
        response = await client.post(XAI_BASE_URL, headers=headers, json=payload)
        response.raise_for_status()

    duration = time.monotonic() - t0
    data = response.json()
    content: str = data["choices"][0]["message"]["content"] or "{}"

    usage = data.get("usage", {})
    total_tokens = usage.get("total_tokens", 500)
    estimated_cost = total_tokens * 0.000005  # xAI légèrement plus cher
    _debit_xai_budget(estimated_cost)
    _update_xai_budget_status()

    logger.debug(
        "xAI [%s] %.2fs tokens=%d cost=~€%.5f",
        model, duration, total_tokens, estimated_cost,
    )
    return content, duration


async def get_budget_status() -> dict[str, Any]:
    try:
        with sqlite3.connect(settings.db_path) as conn:
            row = conn.execute(
                "SELECT balance_eur, total_spent_eur, total_calls, status "
                "FROM ai_budget WHERE provider = 'xai';"
            ).fetchone()
        if row:
            return {
                "provider":        "xai",
                "balance_eur":     row[0],
                "total_spent_eur": row[1],
                "total_calls":     row[2],
                "status":          row[3],
            }
    except sqlite3.Error:
        pass
    return {"provider": "xai", "status": "UNKNOWN"}
