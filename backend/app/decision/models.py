from typing import Literal

from pydantic import BaseModel


class AgentVote(BaseModel):
    agent: Literal["claude", "gpt4o", "grok"]
    action: Literal["BUY", "SELL", "HOLD"]
    ticker: str
    notional_eur: float | None = None
    reasoning: str
    confidence: float = 0.5  # 0.0 - 1.0


class CommitteeRun(BaseModel):
    id: int
    run_at: str
    votes_round1: list[AgentVote]
    votes_round2: list[AgentVote]
    winning_action: Literal["BUY", "SELL", "HOLD"] | None
    winning_ticker: str | None
    winning_notional_eur: float | None
    proposal_id: int | None
    error: str | None
