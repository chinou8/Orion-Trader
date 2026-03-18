"""
AI Council v2 — Market Regime.

Responsabilités (SPECS §8) :
  - Calculé 1 seule fois à l'ouverture du marché
  - Stocké en cache mémoire journalier + persisté dans market_regime_log
  - Injecté gratuitement dans chaque prompt agents — zéro appel IA

Régimes possibles :
  BULL_STRONG    S&P500 > EMA200, VIX < 15
  BULL_MODERATE  S&P500 > EMA200, VIX 15-20
  SIDEWAYS       S&P500 entre EMA50 et EMA200, VIX 20-25
  BEAR_MODERATE  S&P500 < EMA200, VIX 25-35
  BEAR_STRONG    S&P500 < EMA200, VIX > 35
  POST_EVENT     Dans les 24h après FED/CPI/earnings majeur

Calculs Python pur — zéro appel IA, zéro numpy (SPECS §13).
"""

import asyncio
import json
import logging
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from statistics import pstdev
from typing import Any

from app.core.config import settings
from app.council.config import (
    AGENT_NAMES,
    AGENT_WEIGHT_DEFAULT,
    AGENT_WEIGHT_MAX,
    AGENT_WEIGHT_MIN,
    AGENT_STATS_LOOKBACK_DAYS,
    MARKET_REGIME_EMA200_PERIOD,
    MARKET_REGIME_EMA50_PERIOD,
)
from app.marketdata.stooq import fetch_stooq_daily

logger = logging.getLogger(__name__)

# Symboles macro à fetcher
_SP500_SYMBOL = "^SPX"
_VIX_SYMBOL   = "^VIX"

# Cache mémoire journalier (reset à minuit)
_cache: dict[str, Any] | None = None
_cache_date: str | None = None   # "YYYY-MM-DD"

# Mots-clés indiquant un événement macro majeur dans les news (POST_EVENT)
_MACRO_EVENT_KEYWORDS = [
    "fed rate", "federal reserve", "fomc", "cpi", "inflation",
    "ecb rate", "central bank", "gdp", "nonfarm payroll", "payroll",
]


# ── Math pur ─────────────────────────────────────────────────────────────────

def compute_ema(prices: list[float], period: int) -> float | None:
    """
    Calcule l'EMA (Exponential Moving Average) d'une série de prix.
    Utilise la formule standard : k = 2/(period+1), EMA_t = price_t*k + EMA_(t-1)*(1-k)
    Retourne None si pas assez de données.
    """
    if len(prices) < period:
        return None

    k = 2.0 / (period + 1)
    # Initialisation : SMA sur les `period` premières valeurs
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = price * k + ema * (1.0 - k)
    return ema


def compute_pearson_correlation(xs: list[float], ys: list[float]) -> float | None:
    """
    Calcule la corrélation de Pearson entre deux séries de même longueur.
    Retourne None si données insuffisantes ou variance nulle.
    """
    n = min(len(xs), len(ys))
    if n < 5:
        return None

    xs, ys = xs[-n:], ys[-n:]
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    num   = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den_x = math.sqrt(sum((xs[i] - mean_x) ** 2 for i in range(n)))
    den_y = math.sqrt(sum((ys[i] - mean_y) ** 2 for i in range(n)))

    if den_x == 0 or den_y == 0:
        return None

    r = num / (den_x * den_y)
    return round(max(-1.0, min(1.0, r)), 4)


def _daily_returns(closes: list[float]) -> list[float]:
    """Convertit une série de prix en rendements journaliers."""
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1] > 0:
            returns.append((closes[i] / closes[i - 1]) - 1.0)
    return returns


def compute_correlation_matrix(
    symbols_closes: dict[str, list[float]],
) -> dict[str, dict[str, float | None]]:
    """
    Calcule la matrice de corrélation des rendements journaliers entre symboles.
    Retourne un dict {symbol: {symbol: correlation}}.
    Calcul Python pur — zéro appel IA (SPECS §13).
    """
    returns_map: dict[str, list[float]] = {
        sym: _daily_returns(closes)
        for sym, closes in symbols_closes.items()
        if len(closes) >= 10
    }

    symbols = list(returns_map.keys())
    matrix: dict[str, dict[str, float | None]] = {}

    for sym_a in symbols:
        matrix[sym_a] = {}
        for sym_b in symbols:
            if sym_a == sym_b:
                matrix[sym_a][sym_b] = 1.0
            elif sym_b in matrix and sym_a in matrix[sym_b]:
                matrix[sym_a][sym_b] = matrix[sym_b][sym_a]  # symétrie
            else:
                matrix[sym_a][sym_b] = compute_pearson_correlation(
                    returns_map[sym_a], returns_map[sym_b]
                )

    return matrix


def determine_regime(
    sp500_closes: list[float],
    vix: float | None,
    post_event: bool = False,
) -> tuple[str, str, float | None]:
    """
    Détermine le régime de marché (SPECS §8).

    Retourne (regime, sp500_vs_ema200, vix_used).
    """
    if post_event:
        return "POST_EVENT", "unknown", vix

    ema200 = compute_ema(sp500_closes, MARKET_REGIME_EMA200_PERIOD)
    ema50  = compute_ema(sp500_closes, MARKET_REGIME_EMA50_PERIOD)
    last   = sp500_closes[-1] if sp500_closes else None

    sp500_vs_ema200 = "unknown"
    if last is not None and ema200 is not None:
        sp500_vs_ema200 = "above" if last > ema200 else "below"

    vix_lvl = vix if vix is not None else 20.0  # défaut neutre

    # Classement selon SPECS §8
    if last is not None and ema200 is not None:
        above_ema200 = last > ema200
        below_ema50  = ema50 is not None and last < ema50

        if above_ema200:
            if vix_lvl < 15:
                regime = "BULL_STRONG"
            else:
                regime = "BULL_MODERATE"
        elif below_ema50:
            if vix_lvl > 35:
                regime = "BEAR_STRONG"
            elif vix_lvl > 25:
                regime = "BEAR_MODERATE"
            else:
                regime = "SIDEWAYS"
        else:
            # Entre EMA50 et EMA200
            regime = "SIDEWAYS"
    else:
        regime = "SIDEWAYS"  # données insuffisantes → conservateur

    return regime, sp500_vs_ema200, vix


# ── Données marché ────────────────────────────────────────────────────────────

async def _fetch_closes_async(symbol: str, limit: int = 250) -> list[float]:
    """
    Fetche les prix de clôture d'un symbole (Stooq, async via thread).
    Essaie d'abord depuis market_bars (DB), sinon Stooq.
    """
    # 1. Essai depuis la DB (market_bars v1)
    try:
        with sqlite3.connect(settings.db_path) as conn:
            rows = conn.execute(
                """
                SELECT close FROM market_bars
                WHERE symbol = ? AND timeframe = '1d'
                ORDER BY ts DESC LIMIT ?;
                """,
                (symbol, limit),
            ).fetchall()
        if len(rows) >= 20:
            closes = [r[0] for r in reversed(rows)]
            logger.debug("market_regime: %s closes from DB (%d pts)", symbol, len(closes))
            return closes
    except Exception as exc:
        logger.debug("market_regime DB fetch error [%s]: %s", symbol, exc)

    # 2. Stooq fallback
    try:
        bars, _, _, err = await asyncio.to_thread(fetch_stooq_daily, symbol)
        if bars and not err:
            closes = [b.close for b in bars[-limit:]]
            logger.debug("market_regime: %s closes from Stooq (%d pts)", symbol, len(closes))
            return closes
    except Exception as exc:
        logger.warning("market_regime Stooq fetch error [%s]: %s", symbol, exc)

    return []


def _get_watchlist_closes() -> dict[str, list[float]]:
    """Retourne les closes DB pour les symboles actifs de la watchlist."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            symbols = [
                r[0] for r in conn.execute(
                    "SELECT symbol FROM watchlist_items WHERE is_active = 1;"
                ).fetchall()
            ]
        result: dict[str, list[float]] = {}
        for sym in symbols:
            rows = conn.execute(
                """
                SELECT close FROM market_bars
                WHERE symbol = ? AND timeframe = '1d'
                ORDER BY ts DESC LIMIT 60;
                """,
                (sym,),
            ).fetchall()
            if len(rows) >= 5:
                result[sym] = [r[0] for r in reversed(rows)]
        return result
    except Exception:
        return {}


# ── Poids agents ──────────────────────────────────────────────────────────────

def compute_agent_weights(market_regime: str = "") -> dict[str, float]:
    """
    Lit les stats des agents depuis agent_stats (SQLite) pour calculer
    les poids dynamiques (SPECS §3.2).
    Retourne un dict {agent_slot: weight}.
    Zéro appel IA.
    """
    weights = {slot: AGENT_WEIGHT_DEFAULT for slot in AGENT_NAMES}

    try:
        with sqlite3.connect(settings.db_path) as conn:
            rows = conn.execute(
                """
                SELECT agent_slot, win_rate, calibration_score
                FROM agent_stats
                WHERE period_end >= date('now', ?)
                  AND total_trades >= 5
                """,
                (f"-{AGENT_STATS_LOOKBACK_DAYS} days",),
            ).fetchall()
    except Exception as exc:
        logger.debug("compute_agent_weights DB error: %s", exc)
        return weights

    for slot, win_rate, calibration in rows:
        if slot not in weights:
            continue
        # Poids = win_rate normalisé + bonus calibration
        # win_rate 0.5 → poids 1.0, win_rate 0.7 → poids ~1.4
        raw_weight = (win_rate * 2.0) * (0.8 + 0.4 * calibration)
        weights[slot] = round(
            max(AGENT_WEIGHT_MIN, min(AGENT_WEIGHT_MAX, raw_weight)), 3
        )

    return weights


# ── Détection macro events ────────────────────────────────────────────────────

def detect_macro_events_today() -> list[str]:
    """
    Détecte les événements macro majeurs des dernières 24h (depuis news_feed).
    Retourne une liste de titres d'événements.
    Python pur — zéro appel IA.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    try:
        with sqlite3.connect(settings.db_path) as conn:
            rows = conn.execute(
                """
                SELECT title FROM news_feed
                WHERE impact_level = 'HIGH'
                  AND fetched_at >= ?
                ORDER BY fetched_at DESC
                LIMIT 20;
                """,
                (cutoff,),
            ).fetchall()
    except Exception:
        return []

    events = []
    for (title,) in rows:
        title_lower = title.lower()
        if any(kw in title_lower for kw in _MACRO_EVENT_KEYWORDS):
            events.append(title)

    return events


# ── Calcul du contexte journalier ─────────────────────────────────────────────

async def compute_daily_context(force: bool = False) -> dict[str, Any]:
    """
    Calcule et met en cache le DAILY_CONTEXT (SPECS §8.1).
    Si le cache existe pour aujourd'hui et force=False, retourne le cache.
    """
    global _cache, _cache_date

    today = date.today().isoformat()
    if not force and _cache is not None and _cache_date == today:
        return _cache

    logger.info("market_regime: computing daily context (date=%s)", today)

    # ── Fetch S&P500 + VIX en parallèle ──────────────────────────────────────
    sp500_closes, vix_closes = await asyncio.gather(
        _fetch_closes_async(_SP500_SYMBOL, limit=250),
        _fetch_closes_async(_VIX_SYMBOL,   limit=10),
        return_exceptions=True,
    )

    if isinstance(sp500_closes, Exception):
        sp500_closes = []
    if isinstance(vix_closes, Exception):
        vix_closes = []

    vix_level: float | None = float(vix_closes[-1]) if vix_closes else None

    # ── Détection POST_EVENT ──────────────────────────────────────────────────
    macro_events = detect_macro_events_today()
    post_event   = len(macro_events) > 0

    # ── Régime ───────────────────────────────────────────────────────────────
    regime, sp500_vs_ema200, _ = determine_regime(
        sp500_closes,   # type: ignore[arg-type]
        vix_level,
        post_event=post_event,
    )

    # ── Matrice de corrélation (watchlist) ────────────────────────────────────
    watchlist_closes = await asyncio.to_thread(_get_watchlist_closes)
    correlation_matrix = compute_correlation_matrix(watchlist_closes)

    # ── Poids agents ──────────────────────────────────────────────────────────
    agent_weights = await asyncio.to_thread(compute_agent_weights, regime)

    # ── Build DAILY_CONTEXT ───────────────────────────────────────────────────
    context: dict[str, Any] = {
        "market_regime":         regime,
        "vix_level":             round(vix_level, 2) if vix_level else None,
        "sp500_vs_ema200":       sp500_vs_ema200,
        "sp500_last_close":      round(sp500_closes[-1], 2) if sp500_closes else None,
        "correlation_matrix":    correlation_matrix,
        "agent_weights":         agent_weights,
        "circuit_breaker_status": "OK",   # mis à jour par circuit_breaker.py
        "macro_events_today":    macro_events,
        "generated_at":          datetime.now().strftime("%H:%M"),
        "date":                  today,
    }

    # ── Cache + persistance ───────────────────────────────────────────────────
    _cache      = context
    _cache_date = today
    await asyncio.to_thread(_save_regime_to_db, context)

    logger.info(
        "market_regime: regime=%s VIX=%s sp500=%s macro_events=%d",
        regime, vix_level, sp500_vs_ema200, len(macro_events),
    )
    return context


def _save_regime_to_db(context: dict[str, Any]) -> None:
    """Persiste le contexte journalier dans market_regime_log."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO market_regime_log
                    (date, regime, vix_level, sp500_vs_ema200,
                     macro_events, agent_weights, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (
                    context["date"],
                    context["market_regime"],
                    context["vix_level"],
                    context["sp500_vs_ema200"],
                    json.dumps(context["macro_events_today"]),
                    json.dumps(context["agent_weights"]),
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.warning("market_regime save error: %s", exc)


# ── Accès public ──────────────────────────────────────────────────────────────

def get_cached_context() -> dict[str, Any]:
    """
    Retourne le cache mémoire. Si absent, retourne un contexte SIDEWAYS par défaut.
    NE recalcule PAS (appeler compute_daily_context() pour recalculer).
    """
    if _cache is not None:
        return _cache

    # Défaut conservateur si pas encore calculé
    return {
        "market_regime":         "SIDEWAYS",
        "vix_level":             None,
        "sp500_vs_ema200":       "unknown",
        "sp500_last_close":      None,
        "correlation_matrix":    {},
        "agent_weights":         {slot: AGENT_WEIGHT_DEFAULT for slot in AGENT_NAMES},
        "circuit_breaker_status": "OK",
        "macro_events_today":    [],
        "generated_at":          "N/A",
        "date":                  date.today().isoformat(),
    }


def get_regime_for_prompt() -> str:
    """
    Retourne le contexte macro formaté pour injection dans les prompts agents.
    Compact et lisible — zéro appel IA.
    """
    ctx = get_cached_context()
    regime  = ctx.get("market_regime", "SIDEWAYS")
    vix     = ctx.get("vix_level")
    sp500   = ctx.get("sp500_vs_ema200", "unknown")
    cb      = ctx.get("circuit_breaker_status", "OK")
    events  = ctx.get("macro_events_today", [])
    gen_at  = ctx.get("generated_at", "N/A")

    vix_str    = f"{vix:.1f}" if vix is not None else "N/A"
    events_str = "\n".join(f"  ⚡ {e}" for e in events[:3]) if events else "  (aucun)"

    return (
        f"=== CONTEXTE MACRO (calculé à {gen_at}) ===\n"
        f"Régime       : {regime}\n"
        f"VIX          : {vix_str}\n"
        f"S&P500/EMA200: {sp500}\n"
        f"Circuit Breaker: {cb}\n"
        f"Événements macro aujourd'hui :\n{events_str}"
    )


def update_circuit_breaker_status(status: str) -> None:
    """
    Permet à circuit_breaker.py de mettre à jour le statut dans le cache.
    status : "OK" | "YELLOW" | "ORANGE" | "RED"
    """
    global _cache
    if _cache is not None:
        _cache["circuit_breaker_status"] = status
