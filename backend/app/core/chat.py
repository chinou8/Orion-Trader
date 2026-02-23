from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.watchlist import WatchlistItem


class ChatMessage(BaseModel):
    id: int
    thread_id: int
    role: Literal["user", "orion"]
    content: str
    created_at: str


class ChatThreadCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None


class ChatThreadCreateResponse(BaseModel):
    thread_id: int
    title: str


class OrionReplyPayload(BaseModel):
    reply_text: str
    recommendations: list[str]
    watch_requests: list[str]
    news_brief: list[str]
    market_analysis: dict[str, object] | None
    meta: dict[str, str]


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


class ChatMessageResponse(BaseModel):
    thread_id: int
    user_message: ChatMessage
    orion_message: ChatMessage
    orion_reply: OrionReplyPayload
    watchlist_created: list[WatchlistItem]


class ChatThreadResponse(BaseModel):
    thread_id: int
    title: str
    messages: list[ChatMessage]


def generate_orion_reply(
    user_content: str,
    recent_news: list[str] | None = None,
    market_analysis: dict[str, object] | None = None,
) -> OrionReplyPayload:
    normalized = user_content.lower()
    watch_requests: list[str] = []
    recommendations: list[str] = []
    news_brief: list[str] = []

    if "surveille" in normalized:
        watch_requests.append(user_content.strip())
        recommendations.append("Watch request enregistré en mode tech-only.")

    if "divergence" in normalized:
        recommendations.append("Vérifier divergence liquid/illiquid avant proposition d'ordre.")

    if recent_news and ("news" in normalized or "marché" in normalized or "marche" in normalized):
        news_brief = recent_news[:3]
        recommendations.append("Brief news ajouté depuis les flux RSS institutionnels.")

    if market_analysis is not None:
        recommendations.append("Analyse marché ajoutée en mode tech-only.")

    reply_text = (
        "Orion (tech-only): message reçu. "
        "Je stocke le contexte et prépare les prochaines vérifications techniques."
    )

    return OrionReplyPayload(
        reply_text=reply_text,
        recommendations=recommendations,
        watch_requests=watch_requests,
        news_brief=news_brief,
        market_analysis=market_analysis,
        meta={"mode": "tech-only", "timestamp": datetime.now(timezone.utc).isoformat()},
    )
