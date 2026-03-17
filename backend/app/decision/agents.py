"""AI agents for the trading committee."""

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import anthropic
import openai

from app.decision.models import AgentVote

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert quantitative trader on a 3-agent AI committee.
Your role is to analyse market data and recommend a single trade (BUY/SELL/HOLD).
Be concise, data-driven, and decisive. Do not hedge excessively."""

_INITIAL_PROMPT_TEMPLATE = """Market context (Paris time: {paris_time}):

WATCHLIST WITH INDICATORS:
{market_context}

RECENT NEWS HEADLINES:
{news_headlines}

Pick the SINGLE BEST opportunity from the watchlist above.
Reply with valid JSON only, no markdown, no extra text:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "ticker": "<symbol from watchlist>",
  "notional_eur": <amount in EUR, e.g. 500.0, or null for HOLD>,
  "reasoning": "<max 2 sentences>",
  "confidence": <0.0-1.0>
}}"""

_DEBATE_PROMPT_TEMPLATE = """You previously recommended:
{own_vote}

Your two colleagues recommended:
{peer_votes}

Given this information, do you maintain or revise your recommendation?
Reply with valid JSON only, no markdown, no extra text:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "ticker": "<symbol from watchlist>",
  "notional_eur": <amount in EUR or null for HOLD>,
  "reasoning": "<max 2 sentences>",
  "confidence": <0.0-1.0>
}}"""


def _parse_vote(agent_name: str, raw: str, round_num: int) -> AgentVote:
    """Parse JSON response from agent into AgentVote."""
    data: dict[str, Any] = json.loads(raw.strip())
    action = str(data.get("action", "HOLD")).upper()
    if action not in ("BUY", "SELL", "HOLD"):
        action = "HOLD"
    return AgentVote(
        agent=agent_name,  # type: ignore[arg-type]
        action=action,  # type: ignore[arg-type]
        ticker=str(data.get("ticker", "")).upper(),
        notional_eur=float(data["notional_eur"]) if data.get("notional_eur") else None,
        reasoning=str(data.get("reasoning", "")),
        confidence=float(data.get("confidence", 0.5)),
    )


class BaseAgent(ABC):
    name: str

    def _fallback(self, round_num: int) -> AgentVote:
        return AgentVote(
            agent=self.name,  # type: ignore[arg-type]
            action="HOLD",
            ticker="",
            reasoning=f"{self.name} unavailable — defaulting to HOLD",
            confidence=0.0,
        )

    @abstractmethod
    def initial_vote(self, market_context: str, news_headlines: str, paris_time: str) -> AgentVote:
        raise NotImplementedError

    @abstractmethod
    def debate_vote(self, own_vote: AgentVote, peer_votes: list[AgentVote]) -> AgentVote:
        raise NotImplementedError


class ClaudeAgent(BaseAgent):
    name = "claude"

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

    def _call(self, user_prompt: str) -> str:
        msg = self._client.messages.create(
            model="claude-opus-4-6",
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return msg.content[0].text  # type: ignore[index]

    def initial_vote(self, market_context: str, news_headlines: str, paris_time: str) -> AgentVote:
        try:
            prompt = _INITIAL_PROMPT_TEMPLATE.format(
                paris_time=paris_time,
                market_context=market_context,
                news_headlines=news_headlines,
            )
            raw = self._call(prompt)
            return _parse_vote(self.name, raw, 1)
        except Exception as exc:
            logger.warning("ClaudeAgent initial_vote failed: %s", exc)
            return self._fallback(1)

    def debate_vote(self, own_vote: AgentVote, peer_votes: list[AgentVote]) -> AgentVote:
        try:
            prompt = _DEBATE_PROMPT_TEMPLATE.format(
                own_vote=own_vote.model_dump_json(indent=2),
                peer_votes="\n".join(v.model_dump_json(indent=2) for v in peer_votes),
            )
            raw = self._call(prompt)
            return _parse_vote(self.name, raw, 2)
        except Exception as exc:
            logger.warning("ClaudeAgent debate_vote failed: %s", exc)
            return own_vote  # keep round-1 vote on failure


class GPT4oAgent(BaseAgent):
    name = "gpt4o"

    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENAI_API_KEY", "")
        self._client = openai.OpenAI(api_key=self._api_key) if self._api_key else None

    def _call(self, user_prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model="gpt-4o",
            max_tokens=256,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"

    def initial_vote(self, market_context: str, news_headlines: str, paris_time: str) -> AgentVote:
        if not self._api_key:
            logger.info("GPT4oAgent skipped — OPENAI_API_KEY not set")
            return self._fallback(1)
        try:
            prompt = _INITIAL_PROMPT_TEMPLATE.format(
                paris_time=paris_time,
                market_context=market_context,
                news_headlines=news_headlines,
            )
            raw = self._call(prompt)
            return _parse_vote(self.name, raw, 1)
        except Exception as exc:
            logger.warning("GPT4oAgent initial_vote failed: %s", exc)
            return self._fallback(1)

    def debate_vote(self, own_vote: AgentVote, peer_votes: list[AgentVote]) -> AgentVote:
        if not self._api_key:
            return own_vote
        try:
            prompt = _DEBATE_PROMPT_TEMPLATE.format(
                own_vote=own_vote.model_dump_json(indent=2),
                peer_votes="\n".join(v.model_dump_json(indent=2) for v in peer_votes),
            )
            raw = self._call(prompt)
            return _parse_vote(self.name, raw, 2)
        except Exception as exc:
            logger.warning("GPT4oAgent debate_vote failed: %s", exc)
            return own_vote


class GrokAgent(BaseAgent):
    """Grok via xAI OpenAI-compatible API."""

    name = "grok"

    def __init__(self) -> None:
        self._api_key = os.environ.get("XAI_API_KEY", "")
        self._client = (
            openai.OpenAI(api_key=self._api_key, base_url="https://api.x.ai/v1")
            if self._api_key
            else None
        )

    def _call(self, user_prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model="grok-3",
            max_tokens=256,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return resp.choices[0].message.content or "{}"

    def initial_vote(self, market_context: str, news_headlines: str, paris_time: str) -> AgentVote:
        if not self._api_key:
            logger.info("GrokAgent skipped — XAI_API_KEY not set")
            return self._fallback(1)
        try:
            prompt = _INITIAL_PROMPT_TEMPLATE.format(
                paris_time=paris_time,
                market_context=market_context,
                news_headlines=news_headlines,
            )
            raw = self._call(prompt)
            return _parse_vote(self.name, raw, 1)
        except Exception as exc:
            logger.warning("GrokAgent initial_vote failed: %s", exc)
            return self._fallback(1)

    def debate_vote(self, own_vote: AgentVote, peer_votes: list[AgentVote]) -> AgentVote:
        if not self._api_key:
            return own_vote
        try:
            prompt = _DEBATE_PROMPT_TEMPLATE.format(
                own_vote=own_vote.model_dump_json(indent=2),
                peer_votes="\n".join(v.model_dump_json(indent=2) for v in peer_votes),
            )
            raw = self._call(prompt)
            return _parse_vote(self.name, raw, 2)
        except Exception as exc:
            logger.warning("GrokAgent debate_vote failed: %s", exc)
            return own_vote
