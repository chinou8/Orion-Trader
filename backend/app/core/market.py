from pydantic import BaseModel


class MarketBar(BaseModel):
    id: int
    symbol: str
    timeframe: str
    ts: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    created_at: str


class MarketIndicators(BaseModel):
    symbol: str
    sma20: float | None
    sma50: float | None
    rsi14: float | None
    volatility: float | None
    horizon_hint: str
