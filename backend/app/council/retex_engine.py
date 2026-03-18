"""
AI Council v2 — Moteur RETEX (Retour d'EXpérience).

SPECS §4 — Post-trade diagnostic et apprentissage continu :
  1. record_trade_outcome()    : persiste le résultat réel en DB
  2. run_retex_analysis()      : classe la cause, met à jour agent_stats,
                                 déclenche éventuellement le Master RETEX
  3. get_active_corrective_rules() : injecté dans les prompts agents

Architecture :
  - La classification de cause (TIMING/INFORMATION/CONSEIL/MARCHÉ) est
    100 % Python pur — aucun appel IA coûteux pour chaque trade.
  - Le Master (Claude Opus) est appelé en batch quand ≥ BATCH_LOSS_TRIGGER
    pertes consécutives n'ont pas encore été traitées par le Master.
  - Toutes les règles correctives sont versionnées et datées.
"""

import json
import logging
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from app.core.config import settings
from app.council.config import (
    AGENT_NAMES,
    AGENT_STATS_LOOKBACK_DAYS,
    COUNCIL_CONFIG,
)

logger = logging.getLogger(__name__)

# Nombre de pertes non-traitées par le Master avant de déclencher un batch RETEX
BATCH_LOSS_TRIGGER: int = 3
# Durée de vie max des règles correctives (jours)
RULE_MAX_AGE_DAYS: int = 90


# ── Helpers DB ────────────────────────────────────────────────────────────────

def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ── 1. Enregistrement du résultat de trade ────────────────────────────────────

def record_trade_outcome(
    trade_id: str,
    entry_price: float,
    exit_price: float,
    exit_reason: str,          # "TP" | "SL" | "MANUAL" | "TTL_EXPIRED"
    pnl_absolute: float,
    pnl_percent: float,
    holding_duration_minutes: int,
    *,
    theoretical_sl: float | None = None,
    theoretical_tp: float | None = None,
    actual_sl_hit: bool = False,
    actual_tp_hit: bool = False,
    slippage_entry: float = 0.0,
    slippage_exit: float = 0.0,
    paper_config: str = "D",
) -> None:
    """Persiste le résultat réel du trade dans trade_performance."""
    try:
        with _db() as conn:
            conn.execute(
                """
                INSERT INTO trade_performance (
                    trade_id, entry_price, exit_price,
                    theoretical_sl, theoretical_tp,
                    actual_sl_hit, actual_tp_hit,
                    pnl_absolute, pnl_percent,
                    holding_duration_minutes, exit_reason,
                    slippage_entry, slippage_exit,
                    paper_config, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(trade_id) DO UPDATE SET
                    exit_price               = excluded.exit_price,
                    actual_sl_hit            = excluded.actual_sl_hit,
                    actual_tp_hit            = excluded.actual_tp_hit,
                    pnl_absolute             = excluded.pnl_absolute,
                    pnl_percent              = excluded.pnl_percent,
                    holding_duration_minutes = excluded.holding_duration_minutes,
                    exit_reason              = excluded.exit_reason,
                    slippage_entry           = excluded.slippage_entry,
                    slippage_exit            = excluded.slippage_exit,
                    updated_at               = CURRENT_TIMESTAMP
                """,
                (
                    trade_id, entry_price, exit_price,
                    theoretical_sl, theoretical_tp,
                    int(actual_sl_hit), int(actual_tp_hit),
                    pnl_absolute, pnl_percent,
                    holding_duration_minutes, exit_reason,
                    slippage_entry, slippage_exit,
                    paper_config,
                ),
            )
            conn.commit()
        logger.info(
            "RETEX record_trade_outcome [%s] exit=%s pnl=%.2f%%",
            trade_id, exit_reason, pnl_percent,
        )
    except sqlite3.Error as exc:
        logger.error("record_trade_outcome DB error: %s", exc)


# ── 2. Classification Python pure de la cause ─────────────────────────────────

def _classify_loss_cause(
    council_row: sqlite3.Row,
    agent_rows: list[sqlite3.Row],
    perf_row: sqlite3.Row,
) -> tuple[str, str | None, str | None]:
    """
    Détermine (primary_cause, secondary_cause, primary_subcause) selon SPECS §4.3.
    Retourne un tuple de 3 str (peut être None pour secondary / subcause).

    Catégories :
      TIMING      — bonne direction, mauvais timing d'entrée/sortie
      INFORMATION — news manquante ou signal Grok contradictoire
      CONSEIL     — vote 3/2 et la minorité avait raison
      MARCHÉ      — événement macro imprévisible
    """
    vote_score: str = council_row["vote_score"]            # ex "3/2"
    master_called: bool = bool(council_row["master_called"])
    dissenting: list[str] = json.loads(council_row["dissenting_agents"] or "[]")
    holding: int = perf_row["holding_duration_minutes"] or 0
    exit_reason: str = perf_row["exit_reason"] or ""
    pnl_pct: float = perf_row["pnl_percent"] or 0.0

    # ── CONSEIL : vote 3/2 — la minorité avait raison ────────────────────────
    if vote_score == "3/2" and dissenting:
        # Si la perte est significative (> -2%) le vote serré est le signal principal
        if pnl_pct <= -2.0:
            subcause = "vote_3_2_echec_master" if master_called else "vote_3_2_echec"
            return ("CONSEIL", "TIMING", subcause)

    # ── TIMING : SL déclenché très vite (<30 min) ou très tard ───────────────
    if exit_reason == "SL":
        if holding < 30:
            return ("TIMING", "CONSEIL", "entree_trop_tot")
        if holding > 480:
            return ("TIMING", None, "sortie_tardive")
        return ("TIMING", None, "sl_normal")

    # ── INFORMATION : agent News (slot_3) avait confiance < 50 ──────────────
    news_agents = [r for r in agent_rows if r["agent_slot"] == "slot_3_news"]
    if news_agents and news_agents[0]["information_sufficiency_score"] < 50:
        return ("INFORMATION", "TIMING", "grok_insuffisant")

    # ── MARCHÉ : régime défavorable (lu depuis trade_context) ────────────────
    # Note : primary_cause MARCHÉ est assigné par défaut si rien d'autre ne colle
    return ("MARCHÉ", None, None)


def _dissent_was_correct(
    council_row: sqlite3.Row,
    agent_rows: list[sqlite3.Row],
    outcome_win: bool,
) -> bool:
    """
    Retourne True si les agents dissidents avaient le bon vote.
    (décision finale ≠ résultat → les dissidents qui avaient l'autre camp avaient raison)
    """
    if outcome_win:
        return False  # Le conseil avait raison — les dissidents avaient tort

    dissenting: list[str] = json.loads(council_row["dissenting_agents"] or "[]")
    if not dissenting:
        return False  # Vote unanime → pas de dissident

    final_decision: str = council_row["vote_result"]
    # Les dissidents ont voté l'opposé du conseil → ils avaient raison sur une perte
    return bool(dissenting)


# ── 3. Mise à jour agent_stats ────────────────────────────────────────────────

def _update_agent_stats(
    trade_id: str,
    outcome_win: bool,
    agent_rows: list[sqlite3.Row],
    market_regime: str,
    sector: str,
    signal_type: str,
) -> None:
    """
    Met à jour les stats de chaque agent pour la fenêtre glissante courante.
    Recalcule win_rate, calibration_score, dissent_win_rate.
    """
    period_start = (datetime.utcnow() - timedelta(days=AGENT_STATS_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    period_end   = date.today().strftime("%Y-%m-%d")

    try:
        with _db() as conn:
            for row in agent_rows:
                slot       = row["agent_slot"]
                agent_name = row["agent_name"]
                confidence = row["confidence"] or 0.0
                decision   = row["decision"]

                # La décision de l'agent correspond-elle au résultat du trade ?
                agent_correct = (
                    (outcome_win and decision in ("BUY", "HOLD")) or
                    (not outcome_win and decision == "HOLD")
                )

                # ── Upsert stats ──────────────────────────────────────────────
                conn.execute(
                    """
                    INSERT INTO agent_stats (
                        agent_slot, agent_name, market_regime, sector, signal_type,
                        total_trades, win_count, win_rate,
                        avg_confidence_when_right, avg_confidence_when_wrong,
                        calibration_score, dissent_win_rate,
                        weight_current, period_start, period_end
                    ) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 0, 0, 1.0, ?, ?)
                    ON CONFLICT(agent_slot, market_regime, sector, signal_type, period_start)
                    DO UPDATE SET
                        total_trades = total_trades + 1,
                        win_count    = win_count + ?,
                        win_rate     = CAST(win_count + ? AS REAL) / (total_trades + 1),
                        avg_confidence_when_right = CASE
                            WHEN ? = 1 THEN (avg_confidence_when_right * win_count + ?) / (win_count + 1)
                            ELSE avg_confidence_when_right
                        END,
                        avg_confidence_when_wrong = CASE
                            WHEN ? = 0 THEN (avg_confidence_when_wrong * (total_trades - win_count) + ?) / (total_trades - win_count + 1)
                            ELSE avg_confidence_when_wrong
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        # INSERT values
                        slot, agent_name, market_regime, sector, signal_type,
                        int(agent_correct),  # win_count initial
                        confidence if agent_correct else 0.0,   # avg_conf_right
                        0.0 if agent_correct else confidence,   # avg_conf_wrong
                        period_start, period_end,
                        # ON CONFLICT SET values
                        int(agent_correct),  # win_count +
                        int(agent_correct),  # for win_rate calc
                        int(agent_correct), confidence,  # avg_conf_right
                        int(agent_correct), confidence,  # avg_conf_wrong
                    ),
                )

            conn.commit()
    except sqlite3.Error as exc:
        logger.error("_update_agent_stats DB error: %s", exc)


# ── 4. Génération de règle corrective Python pure ─────────────────────────────

def _generate_python_rule(
    primary_cause: str,
    subcause: str | None,
    ticker: str,
    market_regime: str,
) -> str | None:
    """
    Génère une règle corrective simple à partir de la classification.
    Ces règles sont injected dans les prompts agents avant le Master RETEX.
    """
    rules_map: dict[str, str] = {
        "vote_3_2_echec":        f"ATTENTION : pour {ticker} en régime {market_regime}, les votes 3/2 ont historiquement échoué. Exiger conf ≥ 70% ou attendre Master.",
        "vote_3_2_echec_master": f"ATTENTION : le Master RETEX a validé un vote 3/2 erroné sur {ticker}. Prudence accrue sur ce signal.",
        "entree_trop_tot":       f"TIMING : entrée trop rapide sur {ticker} — le SL a été déclenché en < 30 min. Attendre confirmation sur la barre suivante.",
        "sortie_tardive":        f"TIMING : sortie tardive sur {ticker} — holding > 8h a amplifié la perte. Réévaluer position dès 4h.",
        "sl_normal":             f"SL standard déclenché sur {ticker} en régime {market_regime}. Vérifier ATR avant entrée.",
        "grok_insuffisant":      f"INFORMATION : Grok (News) avait insufficiency < 50 sur {ticker}. Ne pas trader sans au moins 3 sources d'actualité.",
    }
    return rules_map.get(subcause or "", None)


# ── 5. Batch Master RETEX (Claude Opus) ───────────────────────────────────────

async def _call_master_retex(unprocessed_losses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Appelle Claude Opus (Master) avec un batch de pertes non-analysées.
    Retourne une liste de règles correctives structurées.
    """
    from app.council.utils.openrouter import call_agent

    losses_text = "\n\n".join(
        f"Trade {i+1} [{l['trade_id']}] — {l['ticker']} | "
        f"Cause: {l['primary_cause']} ({l['primary_subcause']}) | "
        f"Vote: {l['vote_score']} | P&L: {l['pnl_percent']:.1f}% | "
        f"Agents dissidents: {l['dissenting_agents']}\n"
        f"Raisonnements: {l['agent_summaries']}"
        for i, l in enumerate(unprocessed_losses)
    )

    system_prompt = (
        "Tu es le Master de l'AI Council Orion, spécialiste en analyse post-trade. "
        "Tu analyses les trades perdants et génères des règles correctives précises "
        "pour améliorer les décisions futures. Réponds UNIQUEMENT en JSON valide."
    )

    user_prompt = f"""
Analyse ces {len(unprocessed_losses)} trades perdants et génère des règles correctives :

{losses_text}

Réponds avec ce JSON exact :
{{
  "rules": [
    {{
      "rule_text": "Règle précise et actionnable",
      "category": "TIMING|INFORMATION|CONSEIL|MARCHÉ",
      "confidence_score": 0.0-1.0,
      "applies_to_agent": "slot_1_fundamentalist|slot_2_quant|...|all",
      "source_trade_ids": ["trade_id_1", ...]
    }}
  ],
  "global_insight": "Observation macro sur la série de pertes"
}}
"""

    try:
        content, _ = await call_agent(
            model=COUNCIL_CONFIG["master"],
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            is_master=True,
        )
        data = json.loads(content)
        return data.get("rules", [])
    except Exception as exc:
        logger.error("Master RETEX call failed: %s", exc)
        return []


def _get_unprocessed_losses() -> list[dict[str, Any]]:
    """Retourne les trades perdants non encore analysés par le Master."""
    try:
        with _db() as conn:
            rows = conn.execute(
                """
                SELECT
                    ra.trade_id,
                    tc.ticker,
                    ra.primary_cause,
                    ra.primary_subcause,
                    ra.loss_percentage,
                    cd.vote_score,
                    cd.dissenting_agents
                FROM retex_analysis ra
                JOIN trade_context tc   ON tc.trade_id = ra.trade_id
                JOIN council_decision cd ON cd.trade_id = ra.trade_id
                WHERE ra.processed_by_master = 0
                  AND ra.loss_percentage < -1.0
                ORDER BY ra.created_at DESC
                LIMIT 10
                """
            ).fetchall()

            result = []
            for r in rows:
                # Récupère un court résumé des raisonnements agents
                agent_rows = conn.execute(
                    "SELECT agent_name, decision, confidence, why_this_asset "
                    "FROM agent_reasoning WHERE trade_id = ?",
                    (r["trade_id"],),
                ).fetchall()

                summaries = "; ".join(
                    f"{a['agent_name']}={a['decision']}({a['confidence']:.0f}%)"
                    for a in agent_rows
                )
                result.append({
                    "trade_id":         r["trade_id"],
                    "ticker":           r["ticker"],
                    "primary_cause":    r["primary_cause"] or "",
                    "primary_subcause": r["primary_subcause"] or "",
                    "pnl_percent":      r["loss_percentage"],
                    "vote_score":       r["vote_score"],
                    "dissenting_agents": r["dissenting_agents"],
                    "agent_summaries":  summaries,
                })
        return result
    except sqlite3.Error as exc:
        logger.error("_get_unprocessed_losses error: %s", exc)
        return []


def _save_corrective_rules(rules: list[dict[str, Any]], trade_id: str) -> None:
    """Persiste les règles générées par le Master en base."""
    try:
        with _db() as conn:
            for rule in rules:
                conn.execute(
                    """
                    INSERT INTO corrective_rules
                        (rule_text, source_trade_id, category, confidence_score)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        rule.get("rule_text", ""),
                        trade_id,
                        rule.get("category", "MARCHÉ"),
                        float(rule.get("confidence_score", 0.5)),
                    ),
                )
            conn.commit()
    except sqlite3.Error as exc:
        logger.error("_save_corrective_rules error: %s", exc)


def _mark_master_processed(trade_ids: list[str], master_analysis: str) -> None:
    """Marque les RETEX comme traités par le Master."""
    try:
        with _db() as conn:
            for tid in trade_ids:
                conn.execute(
                    "UPDATE retex_analysis SET processed_by_master = 1, "
                    "master_analysis = ? WHERE trade_id = ?",
                    (master_analysis, tid),
                )
            conn.commit()
    except sqlite3.Error as exc:
        logger.error("_mark_master_processed error: %s", exc)


# ── 6. Point d'entrée principal ───────────────────────────────────────────────

async def run_retex_analysis(trade_id: str) -> dict[str, Any]:
    """
    Point d'entrée RETEX — appelé après la clôture d'un trade.

    Flux :
      1. Lit trade_performance, council_decision, agent_reasoning depuis DB
      2. Calcule outcome_win, met à jour agent_stats
      3. Si perte : classifie la cause, génère une règle Python pure
      4. Sauvegarde en retex_analysis
      5. Si ≥ BATCH_LOSS_TRIGGER pertes non traitées → appelle Master batch RETEX

    Retourne un dict résumé pour les logs.
    """
    result: dict[str, Any] = {"trade_id": trade_id, "processed": False}

    try:
        with _db() as conn:
            perf_row = conn.execute(
                "SELECT * FROM trade_performance WHERE trade_id = ?", (trade_id,)
            ).fetchone()
            if not perf_row:
                logger.warning("RETEX: no trade_performance for trade_id=%s", trade_id)
                return result

            council_row = conn.execute(
                "SELECT * FROM council_decision WHERE trade_id = ? "
                "ORDER BY id DESC LIMIT 1", (trade_id,)
            ).fetchone()
            if not council_row:
                logger.warning("RETEX: no council_decision for trade_id=%s", trade_id)
                return result

            agent_rows = conn.execute(
                "SELECT * FROM agent_reasoning WHERE trade_id = ?", (trade_id,)
            ).fetchall()

            ctx_row = conn.execute(
                "SELECT * FROM trade_context WHERE trade_id = ?", (trade_id,)
            ).fetchone()

    except sqlite3.Error as exc:
        logger.error("RETEX read error: %s", exc)
        return result

    pnl_pct    = perf_row["pnl_percent"] or 0.0
    outcome_win = pnl_pct > 0

    # ── a. Mise à jour agent_stats ────────────────────────────────────────────
    market_regime = ctx_row["market_regime"] if ctx_row else ""
    sector        = ctx_row["sector"]        if ctx_row else ""
    signal_type   = ctx_row["signal_type"]   if ctx_row else ""
    ticker        = ctx_row["ticker"]        if ctx_row else ""

    _update_agent_stats(
        trade_id, outcome_win, list(agent_rows),
        market_regime, sector, signal_type,
    )

    # ── b. Analyse uniquement si perte ───────────────────────────────────────
    if outcome_win:
        result["outcome"] = "WIN"
        result["processed"] = True
        return result

    # ── c. Classification Python pure ─────────────────────────────────────────
    primary_cause, secondary_cause, subcause = _classify_loss_cause(
        council_row, list(agent_rows), perf_row
    )
    dissent_correct = _dissent_was_correct(council_row, list(agent_rows), outcome_win)
    python_rule     = _generate_python_rule(subcause, subcause, ticker, market_regime)

    # ── d. Sauvegarde retex_analysis ──────────────────────────────────────────
    try:
        with _db() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO retex_analysis (
                    trade_id, loss_amount, loss_percentage,
                    actual_exit_price,
                    dissent_was_correct,
                    primary_cause, secondary_cause, primary_subcause,
                    corrective_rule, rule_confidence,
                    processed_by_master
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    trade_id,
                    abs(perf_row["pnl_absolute"] or 0.0),
                    pnl_pct,
                    perf_row["exit_price"],
                    int(dissent_correct),
                    primary_cause,
                    secondary_cause,
                    subcause,
                    python_rule,
                    0.6 if python_rule else 0.0,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.error("retex_analysis insert error: %s", exc)
        return result

    # ── e. Règle corrective Python → corrective_rules ─────────────────────────
    if python_rule:
        _save_corrective_rules(
            [{"rule_text": python_rule, "category": primary_cause, "confidence_score": 0.6}],
            trade_id,
        )

    # ── f. Trigger batch Master si seuil atteint ──────────────────────────────
    unprocessed = _get_unprocessed_losses()
    if len(unprocessed) >= BATCH_LOSS_TRIGGER:
        logger.info(
            "RETEX: %d pertes non-traitées — déclenchement Master batch RETEX",
            len(unprocessed),
        )
        master_rules = await _call_master_retex(unprocessed)
        if master_rules:
            _save_corrective_rules(master_rules, trade_id)
            trade_ids = [u["trade_id"] for u in unprocessed]
            _mark_master_processed(trade_ids, json.dumps(master_rules))
            logger.info("Master RETEX: %d règles générées", len(master_rules))

    result.update({
        "outcome":        "LOSS",
        "primary_cause":  primary_cause,
        "subcause":       subcause,
        "rule_generated": bool(python_rule),
        "processed":      True,
    })

    logger.info(
        "RETEX [%s] %s | cause=%s/%s | dissent_correct=%s",
        trade_id, ticker, primary_cause, subcause, dissent_correct,
    )
    return result


# ── 7. Accès aux règles pour injection dans les prompts ───────────────────────

def get_active_corrective_rules(
    agent_slot: str | None = None,
    ticker: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Retourne les règles correctives actives les plus récentes.
    Filtrage optionnel par agent_slot et/ou ticker (via source_trade_id → ticker).
    Utilisé par ai_council.py/_get_retex_context().
    """
    try:
        with _db() as conn:
            if ticker:
                rows = conn.execute(
                    """
                    SELECT cr.rule_text, cr.category, cr.confidence_score,
                           cr.times_applied, cr.created_at
                    FROM corrective_rules cr
                    JOIN trade_context tc ON tc.trade_id = cr.source_trade_id
                    WHERE cr.active = 1
                      AND tc.ticker = ?
                    ORDER BY cr.confidence_score DESC, cr.created_at DESC
                    LIMIT ?
                    """,
                    (ticker, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT rule_text, category, confidence_score,
                           times_applied, created_at
                    FROM corrective_rules
                    WHERE active = 1
                    ORDER BY confidence_score DESC, created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.error("get_active_corrective_rules error: %s", exc)
        return []


def format_rules_for_prompt(
    agent_slot: str | None = None,
    ticker: str | None = None,
) -> str:
    """
    Formate les règles correctives pour injection dans un prompt agent.
    Retourne une chaîne vide si aucune règle active.
    """
    rules = get_active_corrective_rules(agent_slot=agent_slot, ticker=ticker, limit=5)
    if not rules:
        return ""

    lines = ["## Règles correctives RETEX (apprises des trades passés) :"]
    for r in rules:
        conf_pct = int(r["confidence_score"] * 100)
        lines.append(f"- [{r['category']} — conf {conf_pct}%] {r['rule_text']}")
    return "\n".join(lines)


# ── 8. Nettoyage des règles expirées ──────────────────────────────────────────

def cleanup_expired_rules(max_age_days: int = RULE_MAX_AGE_DAYS) -> int:
    """
    Désactive (active=0) les règles créées il y a plus de max_age_days.
    Retourne le nombre de règles désactivées.
    """
    cutoff = (datetime.utcnow() - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            cur = conn.execute(
                "UPDATE corrective_rules SET active = 0 "
                "WHERE active = 1 AND created_at < ?",
                (cutoff,),
            )
            conn.commit()
            count = cur.rowcount
        if count:
            logger.info("RETEX cleanup: %d règles expirées désactivées", count)
        return count
    except sqlite3.Error as exc:
        logger.error("cleanup_expired_rules error: %s", exc)
        return 0


# ── 9. Statistiques globales RETEX ────────────────────────────────────────────

def get_retex_stats() -> dict[str, Any]:
    """Retourne un résumé des statistiques RETEX pour le dashboard."""
    try:
        with _db() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM retex_analysis"
            ).fetchone()[0]
            by_cause = conn.execute(
                "SELECT primary_cause, COUNT(*) as cnt "
                "FROM retex_analysis GROUP BY primary_cause"
            ).fetchall()
            active_rules = conn.execute(
                "SELECT COUNT(*) FROM corrective_rules WHERE active = 1"
            ).fetchone()[0]
            unprocessed = conn.execute(
                "SELECT COUNT(*) FROM retex_analysis WHERE processed_by_master = 0"
                " AND loss_percentage < -1.0"
            ).fetchone()[0]

        return {
            "total_retex":       total,
            "active_rules":      active_rules,
            "unprocessed_losses": unprocessed,
            "by_cause": {r["primary_cause"]: r["cnt"] for r in by_cause},
        }
    except sqlite3.Error as exc:
        logger.error("get_retex_stats error: %s", exc)
        return {}
