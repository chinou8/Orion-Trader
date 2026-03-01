from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from app.core.simulator import Reflection, SimulatedTrade
from app.storage.database import execute_simulated_trade


class ExecutionResult(BaseModel):
    mode: Literal["SIMULATED", "IBKR_PAPER", "IBKR_LIVE"]
    status: str
    message: str
    proposal: dict[str, object] | None = None
    trade: SimulatedTrade | None = None
    portfolio_state: dict[str, object] | None = None
    reflection: Reflection | None = None


class ExecutionProvider(ABC):
    @abstractmethod
    def execute_proposal(self, proposal_id: int) -> ExecutionResult:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> dict[str, object]:
        raise NotImplementedError


class SimulatorExecutionProvider(ExecutionProvider):
    def execute_proposal(self, proposal_id: int) -> ExecutionResult:
        proposal, trade, portfolio_state, reflection = execute_simulated_trade(proposal_id)
        return ExecutionResult(
            mode="SIMULATED",
            status="ok",
            message="Proposal executed in simulator",
            proposal=proposal.model_dump(),
            trade=trade,
            portfolio_state=portfolio_state.model_dump(),
            reflection=reflection,
        )

    def status(self) -> dict[str, object]:
        return {
            "provider": "simulator",
            "configured": True,
            "message": "Simulator execution is active",
        }


class IbkrExecutionProvider(ExecutionProvider):
    def __init__(self, mode: Literal["IBKR_PAPER", "IBKR_LIVE"]) -> None:
        self.mode = mode

    def execute_proposal(self, proposal_id: int) -> ExecutionResult:
        raise ValueError("ibkr_not_configured")

    def status(self) -> dict[str, object]:
        return {
            "provider": "ibkr",
            "configured": False,
            "mode": self.mode,
            "message": "IBKR provider stub: configure gateway/TWS later on VM.",
        }
