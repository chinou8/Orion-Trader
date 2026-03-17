"""APScheduler — runs the AI committee every 30 min during US market hours."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.decision.committee import is_market_open, run_committee

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="Europe/Paris")


def _committee_job() -> None:
    if not is_market_open():
        logger.debug("Committee job skipped — market closed")
        return
    logger.info("Committee job triggered")
    try:
        result = run_committee()
        logger.info(
            "Committee run #%d completed: %s %s proposal=%s",
            result.id,
            result.winning_action,
            result.winning_ticker,
            result.proposal_id,
        )
    except Exception as exc:
        logger.error("Committee job failed: %s", exc)


def start_scheduler() -> None:
    _scheduler.add_job(_committee_job, "interval", minutes=30, id="committee")
    _scheduler.start()
    logger.info("Committee scheduler started (every 30 min, market hours only)")


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
