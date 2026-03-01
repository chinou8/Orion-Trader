from pathlib import Path

from app.core.config import settings
from app.marketdata.indicators import compute_indicators
from app.marketdata.stooq import parse_stooq_csv
from app.storage.database import get_market_bars, init_db, insert_market_bars


def test_parse_stooq_csv_and_insert_bars(tmp_path: Path) -> None:
    original_db = settings.db_path
    settings.db_path = tmp_path / "market-test.db"
    try:
        init_db()

        raw_csv = Path("backend/tests/fixtures/sample_stooq.csv").read_text(encoding="utf-8")
        bars = parse_stooq_csv(raw_csv)
        assert len(bars) == 5

        inserted = insert_market_bars(
            symbol="AIR.PA",
            timeframe="1d",
            source="stooq:air.fr",
            bars=[
                {
                    "ts": bar.ts,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in bars
            ],
        )
        assert inserted == 5

        stored = get_market_bars("AIR.PA", limit=10)
        assert len(stored) == 5
        assert stored[0].symbol == "AIR.PA"
    finally:
        settings.db_path = original_db


def test_compute_indicators_on_known_series() -> None:
    closes = [
        100.0,
        101.0,
        102.0,
        103.0,
        104.0,
        105.0,
        106.0,
        107.0,
        108.0,
        109.0,
        110.0,
        111.0,
        112.0,
        113.0,
        114.0,
        115.0,
        116.0,
        117.0,
        118.0,
        119.0,
        120.0,
        121.0,
        122.0,
        123.0,
        124.0,
        125.0,
        126.0,
        127.0,
        128.0,
        129.0,
        130.0,
        131.0,
        132.0,
        133.0,
        134.0,
        135.0,
        136.0,
        137.0,
        138.0,
        139.0,
        140.0,
        141.0,
        142.0,
        143.0,
        144.0,
        145.0,
        146.0,
        147.0,
        148.0,
        149.0,
        150.0,
    ]

    indicators = compute_indicators("AIR.PA", closes)
    assert indicators.sma20 is not None
    assert indicators.sma50 is not None
    assert indicators.rsi14 is not None
    assert indicators.volatility is not None
    assert indicators.horizon_hint in {"jours", "jours/semaines", "semaines/mois"}
