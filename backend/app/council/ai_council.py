"""
AI Council v2 — Orchestrateur principal (SPECS §2, §3, §4).

Flux d'un run :
  1. Génère un trade_id (UUID)
  2. Calcule le contexte technique du ticker
  3. Récupère régime marché + news + règles RETEX
  4. Sauvegarde trade_context en DB
  5. Appelle les 5 agents votants en PARALLÈLE (asyncio)
  6. Parse + valide chaque réponse JSON
  7. Calcule le vote pondéré (SPECS §3.1 + §3.2)
  8. Convoque Master si vote 3/2 < 65% confidence
  9. Sauvegarde council_decision + agent_reasoning
 10. Retourne CouncilResult

Règles fondamentales (SPECS §13) :
  - Aucun nom de modèle codé en dur — tout passe par COUNCIL_CONFIG
  - Tous les appels IA sont async et parallèles
  - Format JSON des agents validé — vote invalidé si malformé
"""

import asyncio
import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.config import settings
from app.council.config import (
    AGENT_NAMES,
    AGENT_WEIGHT_DEFAULT,
    COUNCIL_CONFIG,
    COUNCIL_FALLBACK_CONFIG,
    VOTE_CONFIDENCE_MIN,
    VOTE_HOLD_MAX_MINUTES,
    VOTE_INFORMATION_SUFFICIENCY_MIN,
)
from app.council.market_regime import get_cached_context, get_regime_for_prompt
from app.council.news_aggregator import get_news_summary_for_prompt
from app.council.utils.openrouter import call_agent as openrouter_call
from app.council.utils.xai_client import call_grok as xai_call
from app.marketdata.indicators import compute_indicators
from app.storage.database import get_market_closes

logger = logging.getLogger(__name__)

# ── Prompts système (un par rôle) ─────────────────────────────────────────────

_SYSTEM_PROMPTS: dict[str, str] = {
    "slot_1_fundamentalist": (
        "Tu es Fundamentalist, analyste fondamental expert sur un comité de trading IA. "
        "Tu analyses les ratios financiers, la macro-économie et les tendances sectorielles. "
        "Tu es rigoureux, factuel et tu quantifies toujours ta confiance honnêtement."
    ),
    "slot_2_quant": (
        "Tu es Quant, expert en analyse quantitative et patterns techniques sur un comité de trading IA. "
        "Tu raisonnes sur les chiffres, les statistiques et les signaux techniques. "
        "Tu ignores le bruit et te concentres sur les signaux confirmés."
    ),
    "slot_3_news": (
        "Tu es News/Sentiment, spécialiste du sentiment de marché et des actualités sur un comité de trading IA. "
        "Tu analyses l'impact des news récentes, le sentiment Twitter/X et les flux d'information. "
        "Tu détectes les catalyseurs court terme et les risques d'actualité."
    ),
    "slot_4_contrarian": (
        "Tu es Contrarian, l'avocat du diable sur un comité de trading IA. "
        "Ton rôle est d'identifier TOUTES les raisons de NE PAS trader : risques cachés, "
        "timing incorrect, sur-confiance des autres agents. Tu protèges le capital."
    ),
    "slot_5_finance": (
        "Tu es Finance, analyste financier spécialisé sur un comité de trading IA. "
        "Tu analyses les états financiers, la valorisation, la liquidité et les risques bilanciel. "
        "Tu évalues la solidité financière avant toute recommandation."
    ),
    "master": (
        "Tu es Master IA, arbitre suprême d'un comité de trading IA. "
        "Tu es convoqué uniquement quand le vote est serré (3/2) et incertain. "
        "Tu analyses les votes des 5 agents, leur raisonnement et tu tranches avec sagesse. "
        "Tu prends aussi en compte l'historique RETEX pour éviter de répéter les erreurs."
    ),
}

_VOTE_PROMPT_TEMPLATE = """\
{regime_context}

=== DERNIÈRES NEWS (scoring automatique) ===
{news_context}

=== WATCHLIST — INDICATEURS TECHNIQUES ===
{market_context}

=== TES PERFORMANCES RÉCENTES (apprentissage RETEX) ===
{retex_context}

=== INSTRUCTION ===
Analyse toutes les données ci-dessus. Tu dois choisir LE MEILLEUR trade parmi la watchlist,
ou recommander HOLD si aucune opportunité n'est convaincante.

Réponds UNIQUEMENT en JSON valide, sans markdown, sans texte hors du JSON :
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "ticker": "<symbole exact de la watchlist, ou vide si HOLD>",
  "confidence": <entier 0-100>,
  "based_on": {{
    "technical":    ["<observation 1>", "<observation 2>"],
    "fundamental":  ["<observation>"],
    "sentiment":    ["<observation>"] | null,
    "historical":   ["<observation>"]
  }},
  "ignored_signals": [
    {{"signal": "<signal ignoré>", "why_ignored": "<raison>"}}
  ],
  "factor_weights": {{"technique": <int>, "fondamental": <int>, "historique": <int>}},
  "alternatives_considered": [
    {{"asset": "<symbole>", "score": <int 0-100>, "why_not": "<raison>"}}
  ],
  "why_this_asset": "<raison principale du choix>",
  "information_sufficiency": {{
    "score": <int 0-100>,
    "threshold": 65,
    "recommend_wait": <true|false>,
    "missing_data": ["<donnée manquante>"],
    "what_would_change_my_mind": "<condition>"
  }}
}}
"""

_MASTER_PROMPT_TEMPLATE = """\
Tu es convoqué car le vote du conseil est serré (3/2) avec une confidence insuffisante.

{regime_context}

=== VOTES DES 5 AGENTS ===
{agents_summary}

=== RÈGLES RETEX ACTIVES ===
{retex_context}

=== INSTRUCTION ===
Analyse les votes et tranche. Réponds en JSON valide uniquement :
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "ticker": "<symbole ou vide>",
  "confidence": <int 0-100>,
  "rationale": "<explication du choix en 2-3 phrases>",
  "followed_majority": <true|false>,
  "key_factor": "<facteur décisif>"
}}
"""


# ── Modèles de résultats ──────────────────────────────────────────────────────

@dataclass
class AgentResponse:
    slot:           str
    agent_name:     str
    model_used:     str
    decision:       str          # BUY / SELL / HOLD
    confidence:     float        # 0-100
    ticker:         str
    based_on:       dict[str, Any]
    ignored_signals: list[Any]
    factor_weights:  dict[str, Any]
    alternatives_considered: list[Any]
    why_this_asset:  str
    information_sufficiency: dict[str, Any]
    raw_response:    str
    vote_valid:      bool
    duration_s:      float = 0.0


@dataclass
class CouncilResult:
    trade_id:           str
    ticker:             str
    decision:           str       # BUY / SELL / HOLD / WAITING / BLOCKED
    vote_score:         str       # "4/1", "3/2", "5/0"
    average_confidence: float
    unanimity:          bool
    dissenting_agents:  list[str] = field(default_factory=list)
    master_called:      bool      = False
    master_decision:    str | None = None
    agent_responses:    list[AgentResponse] = field(default_factory=list)
    deliberation_ms:    int       = 0
    agent_weights_used: dict[str, float] = field(default_factory=dict)
    information_sufficiency_scores: dict[str, float] = field(default_factory=dict)
    trade_held_for_data: bool     = False
    hold_duration_minutes: int    = 0
    error:              str | None = None


# ── Contexte RETEX pour les prompts ──────────────────────────────────────────

def _get_retex_context(agent_slot: str, ticker: str) -> str:
    """
    Lit les règles correctives actives + performances récentes de l'agent.
    Retourne un texte formaté pour injection dans le prompt (SPECS §4.5).
    """
    try:
        with sqlite3.connect(settings.db_path) as conn:
            # 5 règles correctives actives les plus récentes
            rules = conn.execute(
                """
                SELECT rule_text, confidence_score, times_applied
                FROM corrective_rules
                WHERE active = 1
                ORDER BY created_at DESC
                LIMIT 5;
                """
            ).fetchall()

            # Stats de l'agent sur ce ticker/secteur
            stats = conn.execute(
                """
                SELECT win_rate, dissent_win_rate, total_trades
                FROM agent_stats
                WHERE agent_slot = ?
                ORDER BY period_end DESC
                LIMIT 1;
                """,
                (agent_slot,),
            ).fetchone()
    except sqlite3.Error:
        return "  (pas encore de données RETEX)"

    lines = []
    if stats:
        wr, dwr, total = stats
        lines.append(f"Ton taux de réussite global : {wr * 100:.0f}% ({total} trades)")
        lines.append(f"Taux de réussite quand tu étais dissident : {dwr * 100:.0f}%")

    if rules:
        lines.append("\nTes règles correctives actives :")
        for i, (rule_text, conf, applied) in enumerate(rules, 1):
            lines.append(f"  {i}. {rule_text} (conf={conf:.0f}%, appliquée {applied}x)")

    return "\n".join(lines) if lines else "  (pas encore de données RETEX)"


# ── Contexte technique ticker ─────────────────────────────────────────────────

def _build_market_context(tickers: list[str]) -> str:
    """Construit le contexte technique pour les agents (indicateurs par symbole)."""
    lines = []
    for symbol in tickers:
        closes = get_market_closes(symbol, timeframe="1d", limit=60)
        if not closes:
            lines.append(f"  {symbol}: pas de données historiques")
            continue
        ind = compute_indicators(symbol, closes)
        trend = "haussier" if (ind.sma20 or 0) > (ind.sma50 or 0) else "baissier"
        rsi   = f"{ind.rsi14:.1f}" if ind.rsi14 else "N/A"
        vol   = f"{ind.volatility * 100:.2f}%" if ind.volatility else "N/A"
        lines.append(
            f"  {symbol}: close={closes[-1]:.2f}  RSI14={rsi}  "
            f"tendance={trend}  volatilité={vol}  horizon={ind.horizon_hint}"
        )
    return "\n".join(lines) if lines else "  (watchlist vide)"


# ── Parsing + validation JSON ─────────────────────────────────────────────────

def _parse_agent_response(
    slot: str,
    agent_name: str,
    model: str,
    raw: str,
    duration: float,
) -> AgentResponse:
    """
    Parse + valide la réponse JSON d'un agent (SPECS §3.3).
    Retourne un AgentResponse avec vote_valid=False si JSON malformé.
    """
    try:
        data = json.loads(raw.strip())
        decision   = str(data.get("decision", "HOLD")).upper()
        if decision not in ("BUY", "SELL", "HOLD"):
            decision = "HOLD"
        ticker     = str(data.get("ticker", "")).upper().strip()
        confidence = float(data.get("confidence", 0))
        confidence = max(0.0, min(100.0, confidence))

        inf_suf    = data.get("information_sufficiency", {})
        return AgentResponse(
            slot=slot,
            agent_name=agent_name,
            model_used=model,
            decision=decision,
            confidence=confidence,
            ticker=ticker,
            based_on=data.get("based_on", {}),
            ignored_signals=data.get("ignored_signals", []),
            factor_weights=data.get("factor_weights", {}),
            alternatives_considered=data.get("alternatives_considered", []),
            why_this_asset=str(data.get("why_this_asset", "")),
            information_sufficiency=inf_suf,
            raw_response=raw,
            vote_valid=True,
            duration_s=duration,
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("Agent [%s] JSON invalid: %s — raw: %.200s", slot, exc, raw)
        return AgentResponse(
            slot=slot,
            agent_name=agent_name,
            model_used=model,
            decision="HOLD",
            confidence=0.0,
            ticker="",
            based_on={},
            ignored_signals=[],
            factor_weights={},
            alternatives_considered=[],
            why_this_asset="Vote invalidé — JSON malformé",
            information_sufficiency={"score": 0},
            raw_response=raw[:2000],
            vote_valid=False,
            duration_s=duration,
        )


# ── Appel d'un agent individuel ───────────────────────────────────────────────

async def _call_single_agent(
    slot: str,
    model: str,
    market_context: str,
    news_context: str,
    regime_context: str,
    retex_context: str,
    fallback_model: str | None = None,
) -> AgentResponse:
    """
    Appelle un agent (OpenRouter ou xAI), avec fallback en cas d'erreur.
    Retourne un AgentResponse (vote_valid=False si les deux échouent).
    """
    agent_name  = AGENT_NAMES.get(slot, slot)
    system_prompt = _SYSTEM_PROMPTS.get(slot, _SYSTEM_PROMPTS["slot_5_finance"])

    user_prompt = _VOTE_PROMPT_TEMPLATE.format(
        regime_context=regime_context,
        news_context=news_context,
        market_context=market_context,
        retex_context=retex_context,
    )

    is_xai = slot == "slot_3_news"

    for attempt_model in [model, fallback_model]:
        if not attempt_model:
            continue
        try:
            if is_xai and attempt_model == model:
                raw, duration = await xai_call(attempt_model, system_prompt, user_prompt)
            else:
                raw, duration = await openrouter_call(
                    attempt_model, system_prompt, user_prompt
                )
            return _parse_agent_response(slot, agent_name, attempt_model, raw, duration)
        except Exception as exc:
            logger.warning(
                "Agent [%s] model=%s failed: %s", slot, attempt_model, exc
            )

    # Les deux tentatives ont échoué → vote invalide HOLD
    logger.error("Agent [%s] all attempts failed — returning HOLD fallback", slot)
    return AgentResponse(
        slot=slot,
        agent_name=agent_name,
        model_used=model,
        decision="HOLD",
        confidence=0.0,
        ticker="",
        based_on={},
        ignored_signals=[],
        factor_weights={},
        alternatives_considered=[],
        why_this_asset=f"{agent_name} indisponible",
        information_sufficiency={"score": 0},
        raw_response="",
        vote_valid=False,
    )


# ── Vote pondéré ──────────────────────────────────────────────────────────────

def _compute_weighted_vote(
    responses: list[AgentResponse],
    agent_weights: dict[str, float],
    primary_decision: str,
    primary_ticker: str,
) -> tuple[float, float]:
    """
    Calcule la confidence pondérée et le score de vote pour la décision majoritaire.
    Retourne (weighted_confidence, weighted_vote_share).
    """
    total_weight = 0.0
    weighted_conf = 0.0
    decision_weight = 0.0

    for resp in responses:
        if not resp.vote_valid:
            continue
        w = agent_weights.get(resp.slot, AGENT_WEIGHT_DEFAULT)
        total_weight += w
        weighted_conf += resp.confidence * w
        if resp.decision == primary_decision and resp.ticker == primary_ticker:
            decision_weight += w

    if total_weight == 0:
        return 0.0, 0.0

    return weighted_conf / total_weight, decision_weight / total_weight


def _majority_decision(
    responses: list[AgentResponse],
    agent_weights: dict[str, float],
) -> tuple[str, str, int, int, list[str]]:
    """
    Détermine la décision majoritaire (par vote pondéré).
    Retourne (decision, ticker, for_count, against_count, dissenting_slots).
    """
    valid = [r for r in responses if r.vote_valid and r.decision != "HOLD"]
    if not valid:
        # Tout le monde HOLD ou tous invalides
        return "HOLD", "", 0, len(responses), []

    # Compte par (decision, ticker)
    vote_counts: dict[tuple[str, str], float] = {}
    for r in valid:
        key = (r.decision, r.ticker)
        w = agent_weights.get(r.slot, AGENT_WEIGHT_DEFAULT)
        vote_counts[key] = vote_counts.get(key, 0.0) + w

    # Décision avec le score pondéré le plus élevé
    best_key = max(vote_counts, key=lambda k: vote_counts[k])
    best_decision, best_ticker = best_key

    for_count  = sum(1 for r in responses if r.vote_valid and r.decision == best_decision and r.ticker == best_ticker)
    total_valid = sum(1 for r in responses if r.vote_valid)
    against_count = total_valid - for_count

    dissenting = [
        r.slot for r in responses
        if r.vote_valid and (r.decision != best_decision or r.ticker != best_ticker)
    ]

    return best_decision, best_ticker, for_count, against_count, dissenting


# ── Master ────────────────────────────────────────────────────────────────────

async def _call_master(
    responses: list[AgentResponse],
    regime_context: str,
    retex_context: str,
) -> str:
    """Convoque le Master pour trancher un vote 3/2 incertain."""
    from app.council.keys import get_model_for_slot
    master_model    = get_model_for_slot("master")
    master_fallback = COUNCIL_FALLBACK_CONFIG["master"]

    agents_summary = "\n\n".join(
        f"[{r.agent_name}] {r.decision} {r.ticker} "
        f"(confidence={r.confidence:.0f}%)\n"
        f"Raison: {r.why_this_asset}\n"
        f"Suffisance info: {r.information_sufficiency.get('score', 'N/A')}/100"
        for r in responses if r.vote_valid
    )

    master_retex = _get_retex_context("master", "")

    user_prompt = _MASTER_PROMPT_TEMPLATE.format(
        regime_context=regime_context,
        agents_summary=agents_summary,
        retex_context=retex_context or master_retex,
    )

    for model in [master_model, master_fallback]:
        try:
            raw, _ = await openrouter_call(
                model, _SYSTEM_PROMPTS["master"], user_prompt, is_master=True
            )
            data = json.loads(raw.strip())
            decision = str(data.get("decision", "HOLD")).upper()
            return decision if decision in ("BUY", "SELL", "HOLD") else "HOLD"
        except Exception as exc:
            logger.warning("Master model=%s failed: %s", model, exc)

    return "HOLD"


# ── Persistance DB ────────────────────────────────────────────────────────────

def _save_trade_context(
    trade_id: str,
    ticker: str,
    market_context_str: str,
    signal_type: str,
) -> None:
    """Sauvegarde le contexte technique dans trade_context."""
    closes = get_market_closes(ticker, timeframe="1d", limit=60)
    ind = compute_indicators(ticker, closes) if closes else None

    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trade_context
                    (trade_id, ticker, rsi, market_regime, signal_type, created_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (
                    trade_id,
                    ticker,
                    ind.rsi14 if ind else None,
                    get_cached_context().get("market_regime", "SIDEWAYS"),
                    signal_type,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.warning("save_trade_context error: %s", exc)


def _save_council_decision(
    trade_id: str,
    result: CouncilResult,
) -> None:
    """Sauvegarde le résultat du vote dans council_decision."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.execute(
                """
                INSERT INTO council_decision
                    (trade_id, vote_result, vote_score, average_confidence,
                     unanimity, dissenting_agents, master_called, master_decision,
                     deliberation_ms, agent_weights_used,
                     information_sufficiency_scores,
                     trade_held_for_data, hold_duration_minutes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    trade_id,
                    result.decision,
                    result.vote_score,
                    result.average_confidence,
                    int(result.unanimity),
                    json.dumps(result.dissenting_agents),
                    int(result.master_called),
                    result.master_decision,
                    result.deliberation_ms,
                    json.dumps(result.agent_weights_used),
                    json.dumps(result.information_sufficiency_scores),
                    int(result.trade_held_for_data),
                    result.hold_duration_minutes,
                ),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.warning("save_council_decision error: %s", exc)


def _save_agent_reasonings(trade_id: str, responses: list[AgentResponse]) -> None:
    """Sauvegarde les raisonnements détaillés dans agent_reasoning."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            for r in responses:
                conn.execute(
                    """
                    INSERT INTO agent_reasoning
                        (trade_id, agent_slot, agent_name, model_used,
                         decision, confidence,
                         based_on_technical, based_on_fundamental,
                         based_on_sentiment, based_on_historical,
                         ignored_signals, factor_weights,
                         alternatives_considered, why_this_asset,
                         information_sufficiency_score, missing_data,
                         blocking_missing, what_would_change_my_mind,
                         raw_response, vote_valid)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                    """,
                    (
                        trade_id,
                        r.slot,
                        r.agent_name,
                        r.model_used,
                        r.decision,
                        r.confidence,
                        json.dumps(r.based_on.get("technical", [])),
                        json.dumps(r.based_on.get("fundamental", [])),
                        json.dumps(r.based_on.get("sentiment") or []),
                        json.dumps(r.based_on.get("historical", [])),
                        json.dumps(r.ignored_signals),
                        json.dumps(r.factor_weights),
                        json.dumps(r.alternatives_considered),
                        r.why_this_asset,
                        float(r.information_sufficiency.get("score", 0)),
                        json.dumps(r.information_sufficiency.get("missing_data", [])),
                        int(r.information_sufficiency.get("recommend_wait", False)),
                        str(r.information_sufficiency.get("what_would_change_my_mind", "")),
                        r.raw_response[:4000] if r.raw_response else "",
                        int(r.vote_valid),
                    ),
                )
            conn.commit()
    except sqlite3.Error as exc:
        logger.warning("save_agent_reasonings error: %s", exc)


# ── Point d'entrée principal ──────────────────────────────────────────────────

async def run_council(
    ticker: str,
    signal_type: str = "MOMENTUM",
    watchlist_tickers: list[str] | None = None,
) -> CouncilResult:
    """
    Lance un run complet du conseil IA v2 pour un ticker donné.

    Args:
        ticker:            Symbole principal à analyser
        signal_type:       Type de signal (MOMENTUM/BREAKOUT/NEWS_HIGH/FUNDAMENTAL)
        watchlist_tickers: Tous les symboles disponibles (pour comparaison par les agents)
    """
    trade_id = str(uuid.uuid4())
    t_start  = time.monotonic()

    logger.info("Council run start — trade_id=%s ticker=%s signal=%s",
                trade_id, ticker, signal_type)

    # ── Contexte commun ───────────────────────────────────────────────────────
    all_tickers      = watchlist_tickers or [ticker]
    market_context   = _build_market_context(all_tickers)
    news_context     = get_news_summary_for_prompt(limit=8)
    regime_context   = get_regime_for_prompt()
    daily_ctx        = get_cached_context()
    agent_weights    = daily_ctx.get("agent_weights", {})
    cb_status        = daily_ctx.get("circuit_breaker_status", "OK")

    # ── Circuit Breaker check (Python pur — zéro IA) ──────────────────────────
    if cb_status == "RED":
        logger.warning("Council blocked by circuit breaker (RED)")
        return CouncilResult(
            trade_id=trade_id,
            ticker=ticker,
            decision="BLOCKED",
            vote_score="0/0",
            average_confidence=0.0,
            unanimity=False,
            error=f"Circuit breaker actif : {cb_status}",
        )

    # ── Sauvegarde contexte trade ─────────────────────────────────────────────
    _save_trade_context(trade_id, ticker, market_context, signal_type)

    # ── Appels agents en parallèle (SPECS §11.1) ──────────────────────────────
    tasks = []
    for slot in [
        "slot_1_fundamentalist",
        "slot_2_quant",
        "slot_3_news",
        "slot_4_contrarian",
        "slot_5_finance",
    ]:
        from app.council.keys import get_model_for_slot
        model          = get_model_for_slot(slot)
        fallback_model = COUNCIL_FALLBACK_CONFIG[slot]
        retex_ctx      = _get_retex_context(slot, ticker)

        tasks.append(
            _call_single_agent(
                slot=slot,
                model=model,
                market_context=market_context,
                news_context=news_context,
                regime_context=regime_context,
                retex_context=retex_ctx,
                fallback_model=fallback_model,
            )
        )

    responses: list[AgentResponse] = await asyncio.gather(*tasks)

    deliberation_ms = int((time.monotonic() - t_start) * 1000)

    # ── Analyse des scores d'information sufficiency ──────────────────────────
    inf_scores = {
        r.slot: r.information_sufficiency.get("score", 100)
        for r in responses
    }
    insufficient_count = sum(
        1 for s in inf_scores.values() if s < VOTE_INFORMATION_SUFFICIENCY_MIN
    )

    # Attente si ≥ 3 agents ont un score d'info insuffisant (SPECS §3.1)
    if insufficient_count >= 3:
        logger.info(
            "Council waiting — %d agents have insufficient data (< %d)",
            insufficient_count, VOTE_INFORMATION_SUFFICIENCY_MIN,
        )
        result = CouncilResult(
            trade_id=trade_id,
            ticker=ticker,
            decision="WAITING",
            vote_score="?/?",
            average_confidence=0.0,
            unanimity=False,
            agent_responses=list(responses),
            deliberation_ms=deliberation_ms,
            agent_weights_used=agent_weights,
            information_sufficiency_scores=inf_scores,
            trade_held_for_data=True,
            hold_duration_minutes=VOTE_HOLD_MAX_MINUTES,
        )
        _save_council_decision(trade_id, result)
        _save_agent_reasonings(trade_id, list(responses))
        return result

    # ── Vote majoritaire ──────────────────────────────────────────────────────
    primary_decision, primary_ticker, for_count, against_count, dissenting = \
        _majority_decision(responses, agent_weights)

    total_valid     = for_count + against_count
    vote_score_str  = f"{for_count}/{against_count}"
    unanimity       = (against_count == 0 and for_count > 0)

    # Confidence pondérée sur la décision majoritaire
    w_confidence, _ = _compute_weighted_vote(
        responses, agent_weights, primary_decision, primary_ticker
    )

    # ── Règles de vote (SPECS §3.1) ───────────────────────────────────────────
    master_called   = False
    master_decision = None

    if primary_decision == "HOLD" or for_count == 0:
        final_decision = "HOLD"
        final_ticker   = ""

    elif for_count >= 4:
        # 4/1 ou 5/0 → exécution directe
        final_decision = primary_decision
        final_ticker   = primary_ticker
        logger.info("Strong majority %s — direct execution", vote_score_str)

    elif for_count == 3 and against_count == 2:
        if w_confidence >= VOTE_CONFIDENCE_MIN:
            # 3/2 + confidence ≥ 65% → direct
            final_decision = primary_decision
            final_ticker   = primary_ticker
            logger.info("3/2 vote, confidence=%.1f >= %d — direct", w_confidence, VOTE_CONFIDENCE_MIN)
        else:
            # 3/2 + confidence < 65% → Master convoqué
            logger.info("3/2 vote, confidence=%.1f < %d — calling Master", w_confidence, VOTE_CONFIDENCE_MIN)
            master_called    = True
            master_dec       = await _call_master(
                list(responses), regime_context, _get_retex_context("master", ticker)
            )
            master_decision  = master_dec
            final_decision   = master_dec
            final_ticker     = primary_ticker if master_dec != "HOLD" else ""
    else:
        final_decision = "HOLD"
        final_ticker   = ""

    # ── Résultat final ────────────────────────────────────────────────────────
    deliberation_ms = int((time.monotonic() - t_start) * 1000)

    result = CouncilResult(
        trade_id=trade_id,
        ticker=final_ticker or ticker,
        decision=final_decision,
        vote_score=vote_score_str,
        average_confidence=round(w_confidence, 1),
        unanimity=unanimity,
        dissenting_agents=dissenting,
        master_called=master_called,
        master_decision=master_decision,
        agent_responses=list(responses),
        deliberation_ms=deliberation_ms,
        agent_weights_used=agent_weights,
        information_sufficiency_scores=inf_scores,
    )

    # ── Persistance ───────────────────────────────────────────────────────────
    _save_council_decision(trade_id, result)
    _save_agent_reasonings(trade_id, list(responses))

    logger.info(
        "Council run complete — trade_id=%s decision=%s ticker=%s score=%s "
        "confidence=%.1f master=%s deliberation=%dms",
        trade_id, final_decision, final_ticker, vote_score_str,
        w_confidence, master_called, deliberation_ms,
    )
    return result


# ── Helpers publics ───────────────────────────────────────────────────────────

def get_last_council_run(trade_id: str) -> dict[str, Any] | None:
    """Retourne la décision du conseil pour un trade_id donné."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM council_decision WHERE trade_id = ?;",
                (trade_id,),
            ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None


def get_agent_reasonings(trade_id: str) -> list[dict[str, Any]]:
    """Retourne les raisonnements détaillés de tous les agents pour un trade_id."""
    try:
        with sqlite3.connect(settings.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM agent_reasoning WHERE trade_id = ? ORDER BY id;",
                (trade_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []
