from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeProposal(BaseModel):
    id: int
    created_at: str
    updated_at: str
    symbol: str
    asset_type: Literal["EQUITY", "ETF", "BOND"]
    market: str
    side: Literal["BUY", "SELL", "HOLD"]
    qty: float | None
    notional_eur: float | None
    order_type: Literal["LIMIT"]
    limit_price: float | None
    horizon_window: str
    thesis_json: str
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED"]
    approved_by: str | None
    approved_at: str | None
    notes: str | None


class TradeProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    asset_type: Literal["EQUITY", "ETF", "BOND"] = "EQUITY"
    market: str = "EU"
    side: Literal["BUY", "SELL", "HOLD"] = "BUY"
    qty: float | None = None
    notional_eur: float | None = None
    order_type: Literal["LIMIT"] = "LIMIT"
    limit_price: float | None = None
    horizon_window: str = "5-15 jours"
    thesis_json: str = "{}"
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED"] = "PENDING"
    notes: str | None = None


class TradeProposalUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    qty: float | None = None
    limit_price: float | None = None
    notes: str | None = None
    status: Literal["PENDING", "APPROVED", "REJECTED", "EXECUTED", "CANCELLED"] | None = None


class TradeProposalActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved_by: str | None = None
    notes: str | None = None


class ProposalCreated(BaseModel):
    id: int
    symbol: str
    side: str
    horizon_window: str
