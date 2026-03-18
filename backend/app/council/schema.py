"""
AI Council v2 — Schéma SQLite.

Crée les 11 nouvelles tables sans toucher à storage/database.py.
Appelé depuis main.py au startup, après init_db() de v1.
Toutes les tables utilisent CREATE TABLE IF NOT EXISTS — idempotent.
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def init_council_db(db_path: Path) -> None:
    """Crée les tables AI Council v2 si elles n'existent pas encore."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")

        # ── 1. trade_context — Contexte technique avant le trade ─────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_context (
                trade_id        TEXT PRIMARY KEY,
                ticker          TEXT NOT NULL,
                sector          TEXT NOT NULL DEFAULT '',
                market_cap_type TEXT NOT NULL DEFAULT '',

                -- Indicateurs techniques
                rsi             REAL,
                macd_signal     TEXT,
                ema_position    TEXT,
                bollinger_position TEXT,
                atr             REAL,
                obv_trend       TEXT,
                volume_vs_average REAL,

                -- Contexte macro
                market_regime   TEXT NOT NULL DEFAULT '',
                vix_level       REAL,
                sp500_trend     TEXT,

                -- Timing
                hour_of_entry   INTEGER,
                day_of_week     INTEGER,
                macro_event_within_3days INTEGER NOT NULL DEFAULT 0,

                -- Signal
                signal_type         TEXT NOT NULL DEFAULT '',
                signal_score        REAL NOT NULL DEFAULT 0,
                signal_confirmations INTEGER NOT NULL DEFAULT 0,
                signal_ttl_minutes  INTEGER NOT NULL DEFAULT 240,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # ── 2. council_decision — Vote du conseil ────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS council_decision (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id        TEXT NOT NULL,
                vote_result     TEXT NOT NULL,   -- BUY / SELL / HOLD / WAITING
                vote_score      TEXT NOT NULL,   -- ex. "4/1", "3/2", "5/0"
                average_confidence REAL NOT NULL DEFAULT 0,
                unanimity       INTEGER NOT NULL DEFAULT 0,

                dissenting_agents          TEXT NOT NULL DEFAULT '[]',  -- JSON
                master_called              INTEGER NOT NULL DEFAULT 0,
                master_decision            TEXT,

                deliberation_ms            INTEGER NOT NULL DEFAULT 0,
                agent_weights_used         TEXT NOT NULL DEFAULT '{}',  -- JSON
                information_sufficiency_scores TEXT NOT NULL DEFAULT '{}',  -- JSON

                trade_held_for_data        INTEGER NOT NULL DEFAULT 0,
                hold_duration_minutes      INTEGER NOT NULL DEFAULT 0,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(trade_id) REFERENCES trade_context(trade_id)
            );
        """)

        # ── 3. agent_reasoning — Raisonnement détaillé par agent ─────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_reasoning (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id        TEXT NOT NULL,
                agent_slot      TEXT NOT NULL,   -- slot_1_fundamentalist, etc.
                agent_name      TEXT NOT NULL,
                model_used      TEXT NOT NULL,

                decision        TEXT NOT NULL,   -- BUY / SELL / HOLD
                confidence      REAL NOT NULL,   -- 0-100

                based_on_technical   TEXT NOT NULL DEFAULT '[]',  -- JSON
                based_on_fundamental TEXT NOT NULL DEFAULT '[]',
                based_on_sentiment   TEXT,
                based_on_historical  TEXT NOT NULL DEFAULT '[]',

                ignored_signals      TEXT NOT NULL DEFAULT '[]',
                factor_weights       TEXT NOT NULL DEFAULT '{}',
                alternatives_considered TEXT NOT NULL DEFAULT '[]',
                why_this_asset       TEXT NOT NULL DEFAULT '',

                information_sufficiency_score REAL NOT NULL DEFAULT 0,
                missing_data         TEXT NOT NULL DEFAULT '[]',
                blocking_missing     INTEGER NOT NULL DEFAULT 0,
                what_would_change_my_mind TEXT NOT NULL DEFAULT '',

                raw_response         TEXT,   -- réponse JSON brute de l'agent
                vote_valid           INTEGER NOT NULL DEFAULT 1,  -- 0 si JSON malformé
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(trade_id) REFERENCES trade_context(trade_id)
            );
        """)

        # ── 4. trade_performance — Résultats du trade ────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_performance (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id        TEXT NOT NULL UNIQUE,

                entry_price     REAL NOT NULL,
                exit_price      REAL,
                theoretical_sl  REAL,
                theoretical_tp  REAL,
                actual_sl_hit   INTEGER NOT NULL DEFAULT 0,
                actual_tp_hit   INTEGER NOT NULL DEFAULT 0,

                pnl_absolute    REAL,
                pnl_percent     REAL,
                holding_duration_minutes INTEGER,
                exit_reason     TEXT,   -- TP / SL / MANUAL / TTL_EXPIRED

                slippage_entry  REAL NOT NULL DEFAULT 0,
                slippage_exit   REAL NOT NULL DEFAULT 0,

                profit_factor_contribution REAL,
                sharpe_contribution        REAL,

                paper_config    TEXT NOT NULL DEFAULT 'D',  -- A/B/C/D
                created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY(trade_id) REFERENCES trade_context(trade_id)
            );
        """)

        # ── 5. retex_analysis — Diagnostic post-trade ────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS retex_analysis (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id        TEXT NOT NULL,

                loss_amount     REAL NOT NULL DEFAULT 0,
                loss_percentage REAL NOT NULL DEFAULT 0,

                optimal_exit_price  REAL,
                actual_exit_price   REAL,
                timing_delta_minutes INTEGER,

                grok_signal_at_entry TEXT,
                grok_signal_at_exit  TEXT,
                news_missed          TEXT NOT NULL DEFAULT '[]',  -- JSON
                dissent_was_correct  INTEGER NOT NULL DEFAULT 0,

                -- Catégories SPECS §4.3
                primary_cause    TEXT,   -- TIMING / INFORMATION / CONSEIL / MARCHÉ
                secondary_cause  TEXT,
                primary_subcause TEXT,   -- ex. entrée_trop_tôt, vote_3_2_échec

                corrective_rule  TEXT,
                rule_confidence  REAL NOT NULL DEFAULT 0,

                processed_by_master INTEGER NOT NULL DEFAULT 0,
                master_analysis     TEXT,

                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(trade_id) REFERENCES trade_context(trade_id)
            );
        """)

        # ── 6. corrective_rules — Règles apprises par le RETEX ───────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS corrective_rules (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_text       TEXT NOT NULL,
                source_trade_id TEXT NOT NULL,

                category        TEXT NOT NULL,   -- TIMING / INFORMATION / CONSEIL / MARCHÉ
                confidence_score REAL NOT NULL DEFAULT 0,

                times_applied         INTEGER NOT NULL DEFAULT 0,
                times_prevented_loss  INTEGER NOT NULL DEFAULT 0,

                active       INTEGER NOT NULL DEFAULT 1,
                created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_applied_at TEXT,

                FOREIGN KEY(source_trade_id) REFERENCES trade_context(trade_id)
            );
        """)

        # ── 7. agent_stats — Performance historique par agent ─────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agent_stats (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_slot      TEXT NOT NULL,
                agent_name      TEXT NOT NULL,
                market_regime   TEXT NOT NULL DEFAULT '',
                sector          TEXT NOT NULL DEFAULT '',
                signal_type     TEXT NOT NULL DEFAULT '',

                total_trades    INTEGER NOT NULL DEFAULT 0,
                win_count       INTEGER NOT NULL DEFAULT 0,
                win_rate        REAL NOT NULL DEFAULT 0,

                avg_confidence_when_right REAL NOT NULL DEFAULT 0,
                avg_confidence_when_wrong REAL NOT NULL DEFAULT 0,
                calibration_score         REAL NOT NULL DEFAULT 0,
                dissent_win_rate          REAL NOT NULL DEFAULT 0,

                weight_current  REAL NOT NULL DEFAULT 1.0,
                period_start    TEXT NOT NULL,
                period_end      TEXT NOT NULL,

                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(agent_slot, market_regime, sector, signal_type, period_start)
            );
        """)

        # ── 8. news_feed — Flux actualités avec scoring ───────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS news_feed (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                source          TEXT NOT NULL,
                title           TEXT NOT NULL,
                url             TEXT NOT NULL DEFAULT '',
                published_at    TEXT NOT NULL,
                fetched_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                tickers_mentioned TEXT NOT NULL DEFAULT '[]',  -- JSON
                category          TEXT NOT NULL DEFAULT '',
                impact_score      INTEGER NOT NULL DEFAULT 0,
                impact_level      TEXT NOT NULL DEFAULT 'LOW',  -- HIGH / MEDIUM / LOW

                council_triggered INTEGER NOT NULL DEFAULT 0,
                injected_in_trades TEXT NOT NULL DEFAULT '[]',  -- JSON [trade_id, ...]
                grok_summary       TEXT,

                UNIQUE(source, url, published_at)
            );
        """)

        # ── 9. market_regime_log — Historique des régimes macro ───────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_regime_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                date            TEXT NOT NULL UNIQUE,

                regime          TEXT NOT NULL,  -- BULL_STRONG / BULL_MODERATE / etc.
                vix_level       REAL,
                sp500_vs_ema200 TEXT,           -- above / below

                macro_events    TEXT NOT NULL DEFAULT '[]',  -- JSON
                agent_weights   TEXT NOT NULL DEFAULT '{}',  -- JSON

                generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # ── 10. circuit_breaker_log — Historique des déclenchements ──────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS circuit_breaker_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_type    TEXT NOT NULL,  -- CONSECUTIVE_SL / DAILY_LOSS / etc.
                level           TEXT NOT NULL,  -- YELLOW / ORANGE / RED
                description     TEXT NOT NULL,

                action_taken    TEXT NOT NULL,
                duration_minutes INTEGER,

                resolved_at  TEXT,
                created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # ── 11. ai_budget — Suivi budgets OpenRouter + xAI ────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_budget (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                provider        TEXT NOT NULL UNIQUE,  -- openrouter / xai

                balance_eur     REAL NOT NULL DEFAULT 0,
                last_reload_eur REAL NOT NULL DEFAULT 0,
                total_spent_eur REAL NOT NULL DEFAULT 0,
                total_calls     INTEGER NOT NULL DEFAULT 0,

                status      TEXT NOT NULL DEFAULT 'OK',  -- OK / LOW / CRITICAL
                updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Seed budgets initiaux (INSERT OR IGNORE — idempotent)
        conn.execute("""
            INSERT OR IGNORE INTO ai_budget (provider, balance_eur, status)
            VALUES ('openrouter', 10.0, 'OK');
        """)
        conn.execute("""
            INSERT OR IGNORE INTO ai_budget (provider, balance_eur, status)
            VALUES ('xai', 5.0, 'OK');
        """)

        # ── 12. council_config — Clés API et config Council v2 ───────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS council_config (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Seed : clés vides (ne remplace pas si déjà renseignées)
        conn.execute("INSERT OR IGNORE INTO council_config (key, value) VALUES ('openrouter_api_key', '');")
        conn.execute("INSERT OR IGNORE INTO council_config (key, value) VALUES ('xai_api_key', '');")

        conn.commit()

    logger.info("AI Council v2 schema initialized — 12 tables OK")
