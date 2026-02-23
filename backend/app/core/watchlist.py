from pydantic import BaseModel, ConfigDict, Field


class WatchlistItem(BaseModel):
    id: int
    symbol: str
    name: str
    asset_type: str
    market: str
    notes: str
    is_active: bool
    created_at: str
    updated_at: str


class WatchlistCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1)
    name: str = ""
    asset_type: str = "EQUITY"
    market: str = "EU"
    notes: str = ""


class WatchlistUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = None
    name: str | None = None
    asset_type: str | None = None
    market: str | None = None
    notes: str | None = None
    is_active: bool | None = None
