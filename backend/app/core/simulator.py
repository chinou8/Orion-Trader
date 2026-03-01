from pydantic import BaseModel


class SimulatedTrade(BaseModel):
    id: int
    proposal_id: int
    symbol: str
    side: str
    qty: float
    price: float
    ts: str
    fees_eur: float
    slippage_bps: float
    source: str
    created_at: str


class PortfolioState(BaseModel):
    id: int
    ts: str
    cash_eur: float
    equity_eur: float
    unrealized_pnl_eur: float
    realized_pnl_eur: float
    created_at: str


class Position(BaseModel):
    symbol: str
    qty: float
    avg_price: float
    market_price: float
    market_value: float
    unrealized_pnl_eur: float


class PortfolioResponse(BaseModel):
    state: PortfolioState
    positions: list[Position]


class Reflection(BaseModel):
    id: int
    ts: str
    proposal_id: int
    text: str
    json_payload: str
    created_at: str
