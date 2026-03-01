from pathlib import Path

from app.core.config import settings
from app.core.proposal import TradeProposalActionRequest, TradeProposalCreateRequest
from app.storage.database import (
    approve_trade_proposal,
    create_trade_proposal,
    execute_simulated_trade,
    get_performance_summary,
    init_db,
    insert_market_bars,
)


def test_performance_summary_uses_initial_cash_baseline(tmp_path: Path) -> None:
    original_db_path = settings.db_path
    settings.db_path = tmp_path / "perf-test.db"
    try:
        init_db()

        baseline = get_performance_summary()
        assert baseline.trades_count == 0
        assert baseline.pnl_total_eur == 0
        assert baseline.performance_since_start_pct == 0

        insert_market_bars(
            symbol="AIR.PA",
            timeframe="1d",
            source="test",
            bars=[
                {
                    "ts": "2026-01-01",
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1000.0,
                }
            ],
        )

        proposal = create_trade_proposal(
            TradeProposalCreateRequest(
                symbol="AIR.PA",
                asset_type="EQUITY",
                market="EU",
                side="BUY",
                qty=1,
                horizon_window="5-15 jours",
                thesis_json="{}",
            )
        )
        approve_trade_proposal(proposal.id, TradeProposalActionRequest(approved_by="qa"))
        execute_simulated_trade(proposal.id)

        summary = get_performance_summary()
        assert summary.trades_count == 1
        assert summary.pnl_total_eur != 0

        expected_pct = (summary.pnl_total_eur / 10000.0) * 100
        assert abs(summary.performance_since_start_pct - expected_pct) < 1e-9
    finally:
        settings.db_path = original_db_path
