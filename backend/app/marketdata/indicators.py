import math
from statistics import pstdev

from app.core.market import MarketIndicators


def compute_indicators(symbol: str, closes: list[float]) -> MarketIndicators:
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    rsi14 = _rsi(closes, 14)
    volatility = _volatility(closes, 20)

    horizon_hint = "jours/semaines"
    if sma20 is not None and sma50 is not None and rsi14 is not None:
        if sma20 > sma50 and 50 <= rsi14 <= 70:
            horizon_hint = "semaines/mois"
        elif rsi14 > 70 or (volatility is not None and volatility > 0.03):
            horizon_hint = "jours"

    return MarketIndicators(
        symbol=symbol,
        sma20=sma20,
        sma50=sma50,
        rsi14=rsi14,
        volatility=volatility,
        horizon_hint=horizon_hint,
    )


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    window = values[-period:]
    return sum(window) / period


def _rsi(values: list[float], period: int) -> float | None:
    if len(values) < period + 1:
        return None

    deltas = [values[i] - values[i - 1] for i in range(len(values) - period, len(values))]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _volatility(values: list[float], period: int) -> float | None:
    if len(values) < period + 1:
        return None

    closes = values[-(period + 1) :]
    returns: list[float] = []
    for i in range(1, len(closes)):
        if closes[i - 1] <= 0:
            continue
        returns.append((closes[i] / closes[i - 1]) - 1)

    if len(returns) < 2:
        return None

    vol = pstdev(returns)
    return float(vol) if math.isfinite(vol) else None
