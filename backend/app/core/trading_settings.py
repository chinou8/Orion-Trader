from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MarketsEnabled(BaseModel):
    model_config = ConfigDict(extra="forbid")

    EU: bool = True
    US: bool = False


class TradingSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    markets_enabled: MarketsEnabled = Field(default_factory=MarketsEnabled)
    max_trades_per_day: int = 8
    boost_trades_per_day: int = 10
    boost_threshold_liquid: float = 0.04
    boost_threshold_illiquid: float = 0.10
    bonds_auto_enabled: bool = False
    bonds_allocation_cap: float = 0.25
    divergence_liquid: float = 0.02
    divergence_illiquid: float = 0.05
    default_order_type_equity: Literal["LIMIT"] = "LIMIT"
    simulator_initial_cash_eur: float = 10000.0
    simulator_fee_per_trade_eur: float = 1.25
    simulator_slippage_bps: float = 5.0
    execution_mode: Literal["SIMULATED", "IBKR_PAPER", "IBKR_LIVE"] = "IBKR_PAPER"

    @field_validator(
        "boost_threshold_liquid",
        "boost_threshold_illiquid",
        "bonds_allocation_cap",
        "divergence_liquid",
        "divergence_illiquid",
    )
    @classmethod
    def validate_ratio_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("must be between 0 and 1")
        return value

    @field_validator("max_trades_per_day")
    @classmethod
    def validate_max_trades_per_day(cls, value: int) -> int:
        if value < 0:
            raise ValueError("must be >= 0")
        return value

    @field_validator(
        "simulator_initial_cash_eur",
        "simulator_fee_per_trade_eur",
        "simulator_slippage_bps",
    )
    @classmethod
    def validate_non_negative_simulator_values(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must be >= 0")
        return value

    @model_validator(mode="after")
    def validate_boost_vs_max(self) -> "TradingSettings":
        if self.boost_trades_per_day < self.max_trades_per_day:
            raise ValueError("boost_trades_per_day must be >= max_trades_per_day")
        return self


def default_trading_settings() -> TradingSettings:
    return TradingSettings()
