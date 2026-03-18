"""
AI Council v2 — Circuit Breaker automatique.

SPECS §6 — Mécanisme de sécurité 100 % Python (aucun appel IA).

Niveaux :
  GREEN  → trading normal
  YELLOW → mode défensif (taille position ÷ 2, VIX > 25)
  ORANGE → pause temporaire (3 SL consécutifs OU perte jour > 5%)
  RED    → arrêt complet (perte semaine > 10% OU VIX > 35)

Déclencheurs surveillés (SPECS §6.2) :
  - CB_CONSECUTIVE_SL_TRIGGER  : 3 SL d'affilée       → ORANGE
  - CB_MAX_LOSS_DAILY_PCT      : 5% perte/jour        → ORANGE
  - CB_MAX_LOSS_WEEKLY_PCT     : 10% perte/semaine    → RED
  - CB_VIX_YELLOW_THRESHOLD    : VIX > 25             → YELLOW
  - CB_VIX_RED_THRESHOLD       : VIX > 35             → RED
  - CB_INSUFFICIENCY_AGENTS_MIN: ≥3 agents insuffisants → YELLOW

Intégration :
  - ai_council.run_council() appelle is_trading_allowed() au début
  - execution.py appelle get_position_multiplier() pour réduire la taille
  - retex_engine.run_retex_analysis() déclenche evaluate() après chaque trade
"""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings
from app.council.config import (
    CB_CONSECUTIVE_SL_TRIGGER,
    CB_INSUFFICIENCY_AGENTS_MIN,
    CB_INSUFFICIENCY_SCORE_MIN,
    CB_MAX_LOSS_DAILY_PCT,
    CB_MAX_LOSS_WEEKLY_PCT,
    CB_VIX_RED_THRESHOLD,
    CB_VIX_YELLOW_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ── État interne (in-memory) ───────────────────────────────────────────────────
# Initialisé GREEN au démarrage, mis à jour à chaque evaluate()

_state: dict[str, Any] = {
    "level":        "GREEN",
    "trigger_type": None,
    "description":  "Initialisation — aucun déclencheur actif",
    "set_at":       datetime.utcnow().isoformat(),
    "duration_minutes": None,
}

# Niveaux par priorité (index = sévérité croissante)
_LEVELS = ["GREEN", "YELLOW", "ORANGE", "RED"]


def _level_index(level: str) -> int:
    try:
        return _LEVELS.index(level)
    except ValueError:
        return 0


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Logging DB ────────────────────────────────────────────────────────────────

def _log_event(
    trigger_type: str,
    level: str,
    description: str,
    action_taken: str,
    duration_minutes: int | None = None,
) -> None:
    try:
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO circuit_breaker_log
                    (trigger_type, level, description, action_taken, duration_minutes)
                VALUES (?, ?, ?, ?, ?)
                """,
                (trigger_type, level, description, action_taken, duration_minutes),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.debug("circuit_breaker_log insert error: %s", exc)


# ── Déclencheurs individuels ──────────────────────────────────────────────────

def _check_consecutive_sl() -> tuple[str, str | None]:
    """
    Lit les N derniers trades depuis trade_performance.
    Si les CB_CONSECUTIVE_SL_TRIGGER derniers ont tous exit_reason='SL' → ORANGE.
    Retourne (level, description|None).
    """
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT exit_reason FROM trade_performance "
                "ORDER BY created_at DESC LIMIT ?",
                (CB_CONSECUTIVE_SL_TRIGGER,),
            ).fetchall()

        if len(rows) < CB_CONSECUTIVE_SL_TRIGGER:
            return "GREEN", None

        if all(r["exit_reason"] == "SL" for r in rows):
            desc = f"{CB_CONSECUTIVE_SL_TRIGGER} SL consécutifs détectés"
            return "ORANGE", desc
    except sqlite3.Error:
        pass
    return "GREEN", None


def _check_daily_loss(portfolio_value: float) -> tuple[str, str | None]:
    """
    Somme les P&L absolus d'aujourd'hui.
    Si perte > CB_MAX_LOSS_DAILY_PCT × portfolio_value → ORANGE.
    """
    if portfolio_value <= 0:
        return "GREEN", None
    today = datetime.utcnow().strftime("%Y-%m-%d")
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(pnl_absolute), 0) AS total "
                "FROM trade_performance "
                "WHERE DATE(created_at) = ?",
                (today,),
            ).fetchone()
        daily_pnl = row["total"] if row else 0.0
        daily_loss_pct = (-daily_pnl) / portfolio_value

        if daily_loss_pct >= CB_MAX_LOSS_DAILY_PCT:
            desc = (
                f"Perte journalière {daily_loss_pct*100:.1f}% "
                f"≥ seuil {CB_MAX_LOSS_DAILY_PCT*100:.0f}%"
            )
            return "ORANGE", desc
    except sqlite3.Error:
        pass
    return "GREEN", None


def _check_weekly_loss(portfolio_value: float) -> tuple[str, str | None]:
    """
    Somme les P&L absolus de la semaine glissante (7 jours).
    Si perte > CB_MAX_LOSS_WEEKLY_PCT × portfolio_value → RED.
    """
    if portfolio_value <= 0:
        return "GREEN", None
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(pnl_absolute), 0) AS total "
                "FROM trade_performance "
                "WHERE created_at >= ?",
                (week_ago,),
            ).fetchone()
        weekly_pnl = row["total"] if row else 0.0
        weekly_loss_pct = (-weekly_pnl) / portfolio_value

        if weekly_loss_pct >= CB_MAX_LOSS_WEEKLY_PCT:
            desc = (
                f"Perte hebdomadaire {weekly_loss_pct*100:.1f}% "
                f"≥ seuil {CB_MAX_LOSS_WEEKLY_PCT*100:.0f}%"
            )
            return "RED", desc
    except sqlite3.Error:
        pass
    return "GREEN", None


def _check_vix(vix_level: float | None) -> tuple[str, str | None]:
    """
    VIX > CB_VIX_RED_THRESHOLD → RED.
    VIX > CB_VIX_YELLOW_THRESHOLD → YELLOW.
    """
    if vix_level is None:
        return "GREEN", None

    if vix_level >= CB_VIX_RED_THRESHOLD:
        return "RED", f"VIX={vix_level:.1f} ≥ seuil rouge {CB_VIX_RED_THRESHOLD}"
    if vix_level >= CB_VIX_YELLOW_THRESHOLD:
        return "YELLOW", f"VIX={vix_level:.1f} ≥ seuil défensif {CB_VIX_YELLOW_THRESHOLD}"
    return "GREEN", None


def _check_agent_insufficiency(insufficiency_scores: dict[str, float]) -> tuple[str, str | None]:
    """
    Si ≥ CB_INSUFFICIENCY_AGENTS_MIN agents ont un score < CB_INSUFFICIENCY_SCORE_MIN → YELLOW.
    insufficiency_scores : {agent_slot: score} depuis CouncilResult.
    """
    if not insufficiency_scores:
        return "GREEN", None

    low_agents = [
        slot for slot, score in insufficiency_scores.items()
        if score < CB_INSUFFICIENCY_SCORE_MIN
    ]
    if len(low_agents) >= CB_INSUFFICIENCY_AGENTS_MIN:
        desc = (
            f"{len(low_agents)} agents avec insufficiency < {CB_INSUFFICIENCY_SCORE_MIN}: "
            + ", ".join(low_agents)
        )
        return "YELLOW", desc
    return "GREEN", None


# ── Évaluation globale ────────────────────────────────────────────────────────

def evaluate(
    *,
    portfolio_value: float = 0.0,
    vix_level: float | None = None,
    insufficiency_scores: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Évalue tous les déclencheurs et met à jour l'état interne.
    Retourne l'état courant après évaluation.

    Appelé par :
      - retex_engine.run_retex_analysis() après chaque trade
      - market_regime.compute_daily_context() chaque matin
      - Directement depuis l'endpoint /api/council/v2/status

    Paramètres :
      portfolio_value     : valeur totale du portefeuille en EUR
      vix_level           : VIX courant (None = lecture depuis cache market_regime)
      insufficiency_scores: {slot: score} du dernier CouncilResult (optionnel)
    """
    global _state

    # Lecture VIX depuis le cache market_regime si non fourni
    if vix_level is None:
        try:
            from app.council.market_regime import get_cached_context
            ctx = get_cached_context()
            vix_level = ctx.get("vix_level")
        except Exception:
            vix_level = None

    # Exécuter tous les checks — garder le pire niveau
    checks = [
        _check_consecutive_sl(),
        _check_daily_loss(portfolio_value),
        _check_weekly_loss(portfolio_value),
        _check_vix(vix_level),
        _check_agent_insufficiency(insufficiency_scores or {}),
    ]

    worst_level = "GREEN"
    worst_trigger = "NONE"
    worst_desc = "Tous les indicateurs dans les seuils normaux"

    for level, desc in checks:
        if _level_index(level) > _level_index(worst_level):
            worst_level = level
            worst_desc = desc or ""

    # Identifier le trigger pour les logs
    trigger_map = {
        0: "CONSECUTIVE_SL",
        1: "DAILY_LOSS",
        2: "WEEKLY_LOSS",
        3: "VIX",
        4: "AGENT_INSUFFICIENCY",
    }
    for i, (level, desc) in enumerate(checks):
        if level == worst_level and desc:
            worst_trigger = trigger_map.get(i, "UNKNOWN")
            break

    # Mettre à jour l'état si changement de niveau
    previous_level = _state["level"]
    if worst_level != previous_level:
        action = _describe_action(worst_level)
        _log_event(
            trigger_type=worst_trigger,
            level=worst_level,
            description=worst_desc,
            action_taken=action,
            duration_minutes=_get_duration_minutes(worst_level),
        )
        logger.warning(
            "Circuit Breaker: %s → %s | %s | action: %s",
            previous_level, worst_level, worst_desc, action,
        )

        # Hook vers market_regime pour mise à jour du cache
        try:
            from app.council.market_regime import update_circuit_breaker_status
            update_circuit_breaker_status(worst_level)
        except Exception:
            pass

    _state = {
        "level":            worst_level,
        "trigger_type":     worst_trigger,
        "description":      worst_desc,
        "set_at":           datetime.utcnow().isoformat(),
        "duration_minutes": _get_duration_minutes(worst_level),
    }

    return get_status()


def _describe_action(level: str) -> str:
    actions = {
        "GREEN":  "Trading normal — aucune restriction",
        "YELLOW": "Mode défensif — taille position ÷ 2, stop élargi",
        "ORANGE": "Pause temporaire — trades suspendus jusqu'à reset manuel ou timeout",
        "RED":    "ARRÊT COMPLET — tous les trades bloqués, révision obligatoire",
    }
    return actions.get(level, "Action inconnue")


def _get_duration_minutes(level: str) -> int | None:
    durations = {
        "GREEN":  None,
        "YELLOW": None,    # persiste jusqu'au prochain evaluate()
        "ORANGE": 240,     # 4h de pause
        "RED":    None,    # reset manuel uniquement
    }
    return durations.get(level)


# ── API publique ──────────────────────────────────────────────────────────────

def get_status() -> dict[str, Any]:
    """Retourne l'état courant du circuit breaker (lecture seule)."""
    return dict(_state)


def is_trading_allowed() -> bool:
    """
    Retourne True si le trading est autorisé.
    RED → False ; GREEN / YELLOW / ORANGE → True (ORANGE = pause mais pas blocage total).
    Note : ORANGE suspend les nouveaux trades via le scheduler,
           mais is_trading_allowed() retourne False seulement sur RED
           pour ne pas bloquer les clôtures de positions existantes.
    """
    return _state["level"] != "RED"


def is_new_trade_allowed() -> bool:
    """
    Plus strict que is_trading_allowed() — bloque aussi ORANGE.
    Utilisé par run_council() avant de lancer un nouveau trade.
    """
    return _state["level"] in ("GREEN", "YELLOW")


def get_position_multiplier() -> float:
    """
    Retourne le multiplicateur de taille de position :
      GREEN  → 1.0  (taille normale)
      YELLOW → 0.5  (mode défensif)
      ORANGE → 0.25 (position minimale si trade exceptionnel autorisé)
      RED    → 0.0  (aucun trade)
    """
    multipliers = {
        "GREEN":  1.0,
        "YELLOW": 0.5,
        "ORANGE": 0.25,
        "RED":    0.0,
    }
    return multipliers.get(_state["level"], 1.0)


def reset(reason: str = "Manuel") -> dict[str, Any]:
    """
    Remet le circuit breaker à GREEN (reset manuel ou automatique après timeout).
    Logue l'événement de résolution.
    """
    global _state
    previous = _state["level"]
    if previous == "GREEN":
        return get_status()

    _log_event(
        trigger_type="RESET",
        level="GREEN",
        description=f"Reset depuis {previous} — raison : {reason}",
        action_taken="Retour au trading normal",
    )
    # Marque le log précédent comme résolu
    try:
        with _db() as conn:
            conn.execute(
                "UPDATE circuit_breaker_log SET resolved_at = CURRENT_TIMESTAMP "
                "WHERE level = ? AND resolved_at IS NULL",
                (previous,),
            )
            conn.commit()
    except sqlite3.Error:
        pass

    _state = {
        "level":            "GREEN",
        "trigger_type":     "RESET",
        "description":      f"Reset depuis {previous} — {reason}",
        "set_at":           datetime.utcnow().isoformat(),
        "duration_minutes": None,
    }

    logger.info("Circuit Breaker reset → GREEN (%s)", reason)

    try:
        from app.council.market_regime import update_circuit_breaker_status
        update_circuit_breaker_status("GREEN")
    except Exception:
        pass

    return get_status()


def auto_reset_if_timeout() -> bool:
    """
    Vérifie si l'ORANGE timeout (4h) est écoulé et reset automatiquement.
    Retourne True si un reset a été effectué.
    Appelé par le scheduler toutes les 30 min.
    """
    if _state["level"] != "ORANGE":
        return False

    set_at_str = _state.get("set_at", "")
    try:
        set_at = datetime.fromisoformat(set_at_str)
    except ValueError:
        return False

    duration = _state.get("duration_minutes") or 240
    if datetime.utcnow() >= set_at + timedelta(minutes=duration):
        reset(reason=f"Timeout automatique après {duration} min")
        return True
    return False


def get_recent_events(limit: int = 20) -> list[dict[str, Any]]:
    """Retourne les derniers événements circuit breaker depuis la DB."""
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT trigger_type, level, description, action_taken, "
                "duration_minutes, resolved_at, created_at "
                "FROM circuit_breaker_log "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
