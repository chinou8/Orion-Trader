"""
AI Council v2 — News Aggregator.

Responsabilités :
  - Polling RSS depuis la table rss_feeds (partagée avec v1)
  - Scoring d'impact Python pur — zéro appel IA (SPECS §7.2)
  - Stockage dans news_feed (table v2, distincte de news_items v1)
  - Classification HIGH / MEDIUM / LOW + extraction de tickers
  - 3 modes de déclenchement : ALERTE_IMMEDIATE, OPPORTUNITE, PASSIF
  - Scheduler APScheduler indépendant (toutes les 5 min)

Ne touche PAS à : rss/service.py, news_items, rss_feeds (contenu/structure).
"""

import asyncio
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

import feedparser
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.council.config import (
    MACRO_POLL_INTERVAL_SECONDS,
    NEWS_IMPACT_HIGH_THRESHOLD,
    NEWS_IMPACT_MEDIUM_THRESHOLD,
    NEWS_KEYWORDS_HIGH,
    NEWS_KEYWORDS_MEDIUM,
    NEWS_POLL_INTERVAL_SECONDS,
)

logger = logging.getLogger(__name__)

# Regex pour détecter des tickers (1-5 majuscules, optionnellement .PA/.L/.DE etc.)
_TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\b")

# Mots parasites à exclure du ticker-matching (acronymes courants non-boursiers)
_TICKER_STOPWORDS = frozenset({
    "CEO", "CFO", "COO", "CTO", "IPO", "ETF", "GDP", "CPI", "FED", "ECB",
    "IMF", "WHO", "FDA", "SEC", "EUR", "USD", "GBP", "JPY", "CHF", "ATR",
    "RSI", "EMA", "SMA", "OBV", "VIX", "USA", "UK", "EU", "US", "AI", "ML",
    "API", "SQL", "RSS", "HTTP", "PDF", "IT", "IT", "A", "I",
})

_news_scheduler: AsyncIOScheduler | None = None


# ── Scoring Python pur (SPECS §7.2) ─────────────────────────────────────────

def score_impact(title: str, summary: str) -> tuple[int, str]:
    """
    Calcule le score d'impact d'un article (Python pur, zéro IA).

    Retourne (score: int, level: "HIGH"|"MEDIUM"|"LOW").

    Règles :
      +3 par mot-clé HIGH trouvé dans titre
      +2 par mot-clé HIGH trouvé dans résumé seulement
      +1 par mot-clé MEDIUM trouvé (titre ou résumé)
    """
    text_title   = title.lower()
    text_summary = summary.lower()
    text_full    = f"{text_title} {text_summary}"

    score = 0

    for kw in NEWS_KEYWORDS_HIGH:
        if kw in text_title:
            score += 3
        elif kw in text_summary:
            score += 2

    for kw in NEWS_KEYWORDS_MEDIUM:
        if kw in text_full:
            score += 1

    if score >= NEWS_IMPACT_HIGH_THRESHOLD:
        level = "HIGH"
    elif score >= NEWS_IMPACT_MEDIUM_THRESHOLD:
        level = "MEDIUM"
    else:
        level = "LOW"

    return score, level


def extract_tickers(text: str) -> list[str]:
    """
    Extrait les tickers potentiels d'un texte (heuristique Python pur).
    Filtre les stopwords et les tokens < 2 caractères.
    """
    candidates = _TICKER_RE.findall(text)
    return [
        t for t in dict.fromkeys(candidates)   # dédupliqué, ordre conservé
        if t not in _TICKER_STOPWORDS and len(t) >= 2
    ]


# ── Accès SQLite (table news_feed — v2) ─────────────────────────────────────

def _upsert_news_item(
    source: str,
    title: str,
    url: str,
    published_at: str,
    tickers: list[str],
    impact_score: int,
    impact_level: str,
) -> bool:
    """
    Insère un article dans news_feed.
    Retourne True si inséré, False si déjà présent (UNIQUE constraint).
    """
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO news_feed
                    (source, title, url, published_at, tickers_mentioned,
                     impact_score, impact_level)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    source, title, url, published_at,
                    json.dumps(tickers),
                    impact_score, impact_level,
                ),
            )
            conn.commit()
            return conn.total_changes > 0
    except sqlite3.Error as exc:
        logger.warning("news_feed insert error: %s", exc)
        return False


def get_recent_high_news(limit: int = 10) -> list[dict[str, Any]]:
    """Retourne les dernières news HIGH impact (pour déclencher le conseil)."""
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM news_feed
            WHERE impact_level = 'HIGH'
            ORDER BY fetched_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_news_for_ticker(ticker: str, limit: int = 5) -> list[dict[str, Any]]:
    """Retourne les news mentionnant un ticker spécifique."""
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM news_feed
            WHERE tickers_mentioned LIKE ?
            ORDER BY fetched_at DESC
            LIMIT ?;
            """,
            (f'%"{ticker}"%', limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_passive_context(limit: int = 20) -> list[dict[str, Any]]:
    """
    Retourne les news MEDIUM + LOW récentes pour injection passive dans les prompts.
    Utilisé par ai_council pour enrichir le contexte sans déclencher de vote.
    """
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT source, title, published_at, impact_level, tickers_mentioned
            FROM news_feed
            WHERE impact_level IN ('MEDIUM', 'LOW')
            ORDER BY fetched_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_news_summary_for_prompt(limit: int = 10) -> str:
    """
    Formate les dernières news (HIGH + MEDIUM) en texte lisible pour les prompts agents.
    Format compact : "[HIGH] Titre — Source (date)"
    """
    with sqlite3.connect(settings.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT title, source, published_at, impact_level, tickers_mentioned
            FROM news_feed
            WHERE impact_level IN ('HIGH', 'MEDIUM')
            ORDER BY fetched_at DESC
            LIMIT ?;
            """,
            (limit,),
        ).fetchall()

    if not rows:
        return "  (aucune news récente)"

    lines = []
    for r in rows:
        tickers = json.loads(r["tickers_mentioned"] or "[]")
        ticker_str = f" [{', '.join(tickers[:3])}]" if tickers else ""
        pub = r["published_at"][:16] if r["published_at"] else ""
        lines.append(
            f"  [{r['impact_level']}] {r['title']}{ticker_str} — {r['source']} {pub}"
        )
    return "\n".join(lines)


def classify_trigger_mode(
    news_item: dict[str, Any],
    portfolio_tickers: list[str],
    watchlist_tickers: list[str],
) -> str:
    """
    Détermine le mode de déclenchement d'une news HIGH (SPECS §7.3).

    Retourne :
      "ALERTE_IMMEDIATE"   — HIGH + ticker en portefeuille
      "OPPORTUNITE"        — HIGH + ticker sur watchlist (pas en portefeuille)
      "ENRICHISSEMENT"     — MEDIUM / LOW ou ticker non suivi
    """
    if news_item.get("impact_level") != "HIGH":
        return "ENRICHISSEMENT"

    tickers: list[str] = json.loads(news_item.get("tickers_mentioned") or "[]")

    for t in tickers:
        if t in portfolio_tickers:
            return "ALERTE_IMMEDIATE"

    for t in tickers:
        if t in watchlist_tickers:
            return "OPPORTUNITE"

    return "ENRICHISSEMENT"


# ── Récupération RSS async ───────────────────────────────────────────────────

async def _fetch_and_score_feed(feed_url: str, feed_name: str) -> dict[str, int]:
    """
    Fetche un flux RSS, score chaque article, insère les nouveaux dans news_feed.
    Retourne un dict {total, inserted, high, medium, low}.
    """
    counts = {"total": 0, "inserted": 0, "high": 0, "medium": 0, "low": 0}

    try:
        # feedparser est synchrone → exécution dans un thread séparé
        parsed = await asyncio.to_thread(feedparser.parse, feed_url)
    except Exception as exc:
        logger.warning("Feed fetch failed [%s]: %s", feed_name, exc)
        return counts

    for entry in parsed.entries:
        title   = str(getattr(entry, "title",   "")).strip()
        summary = str(getattr(entry, "summary", "")).strip()
        link    = str(getattr(entry, "link",    "")).strip()

        if not title:
            continue

        published = _extract_published(entry)
        score, level = score_impact(title, summary)
        tickers = extract_tickers(f"{title} {summary}")

        counts["total"] += 1
        counts[level.lower()] += 1

        inserted = _upsert_news_item(
            source=feed_name,
            title=title,
            url=link,
            published_at=published,
            tickers=tickers,
            impact_score=score,
            impact_level=level,
        )
        if inserted:
            counts["inserted"] += 1
            if level == "HIGH":
                logger.info(
                    "HIGH news [%s] score=%d tickers=%s : %s",
                    feed_name, score, tickers, title[:80],
                )

    return counts


async def poll_all_feeds() -> dict[str, int]:
    """
    Fetche tous les flux RSS actifs en parallèle et retourne les compteurs agrégés.
    Utilise les feeds déjà configurés dans la table rss_feeds (partagée avec v1).
    """
    with sqlite3.connect(settings.db_path) as conn:
        rows = conn.execute(
            "SELECT name, url FROM rss_feeds WHERE is_active = 1;"
        ).fetchall()

    if not rows:
        logger.debug("poll_all_feeds: aucun flux RSS actif")
        return {"total": 0, "inserted": 0, "high": 0, "medium": 0, "low": 0}

    tasks = [_fetch_and_score_feed(url, name) for name, url in rows]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    totals: dict[str, int] = {"total": 0, "inserted": 0, "high": 0, "medium": 0, "low": 0}
    for r in results:
        if isinstance(r, Exception):
            logger.warning("Feed task error: %s", r)
            continue
        for k in totals:
            totals[k] += r.get(k, 0)

    logger.info(
        "News poll done — %d feeds, %d new articles (HIGH=%d MEDIUM=%d LOW=%d)",
        len(rows), totals["inserted"], totals["high"], totals["medium"], totals["low"],
    )
    return totals


# ── Scheduler APScheduler (indépendant du scheduler v1) ─────────────────────

def _poll_job() -> None:
    """Job synchrone wrapper pour APScheduler → lance la coroutine async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(poll_all_feeds())
        else:
            loop.run_until_complete(poll_all_feeds())
    except Exception as exc:
        logger.error("News poll job failed: %s", exc)


def start_news_scheduler() -> None:
    """Démarre le scheduler de polling RSS (toutes les 5 min par défaut)."""
    global _news_scheduler
    _news_scheduler = AsyncIOScheduler(timezone="Europe/Paris")
    _news_scheduler.add_job(
        _poll_job,
        "interval",
        seconds=NEWS_POLL_INTERVAL_SECONDS,
        id="news_poll",
        max_instances=1,
        coalesce=True,
    )
    _news_scheduler.start()
    logger.info(
        "News scheduler started (interval=%ds)", NEWS_POLL_INTERVAL_SECONDS
    )


def stop_news_scheduler() -> None:
    """Arrête le scheduler de polling RSS."""
    global _news_scheduler
    if _news_scheduler and _news_scheduler.running:
        _news_scheduler.shutdown(wait=False)
        logger.info("News scheduler stopped")


# ── Helpers internes ─────────────────────────────────────────────────────────

def _extract_published(entry: Any) -> str:
    """Extrait la date de publication d'une entrée feedparser."""
    for attr in ("published", "updated", "created"):
        val = str(getattr(entry, attr, "")).strip()
        if val:
            return val
    return datetime.now(timezone.utc).isoformat()
