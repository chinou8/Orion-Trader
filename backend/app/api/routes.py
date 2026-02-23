import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.core.chat import (
    ChatMessageRequest,
    ChatMessageResponse,
    ChatThreadCreateRequest,
    ChatThreadCreateResponse,
    ChatThreadResponse,
    generate_orion_reply,
)
from app.core.rss import NewsItem, RssFeed, RssFeedCreateRequest, RssFeedUpdateRequest
from app.core.trading_settings import TradingSettings
from app.core.watchlist import WatchlistCreateRequest, WatchlistItem, WatchlistUpdateRequest
from app.rss.service import fetch_all_active_feeds
from app.storage.database import (
    add_chat_exchange,
    create_chat_thread,
    create_rss_feed,
    create_watchlist_item,
    create_watchlist_items_from_requests,
    get_chat_thread,
    get_latest_news,
    get_rss_feeds,
    get_trading_settings,
    get_watchlist_items,
    save_trading_settings,
    soft_delete_watchlist_item,
    update_rss_feed,
    update_watchlist_item,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
    <!doctype html>
    <html lang=\"en\">
      <head><meta charset=\"UTF-8\"><title>Orion Trader</title></head>
      <body><h1>Orion Trader – OK</h1></body>
    </html>
    """


@router.get("/api/settings", response_model=TradingSettings)
def get_settings() -> TradingSettings:
    return get_trading_settings()


@router.put("/api/settings", response_model=TradingSettings)
def put_settings(payload: TradingSettings) -> TradingSettings:
    return save_trading_settings(payload)


@router.get("/api/watchlist", response_model=list[WatchlistItem])
def get_watchlist() -> list[WatchlistItem]:
    return get_watchlist_items(active_only=True)


@router.post("/api/watchlist", response_model=WatchlistItem)
def post_watchlist(payload: WatchlistCreateRequest) -> WatchlistItem:
    try:
        return create_watchlist_item(payload)
    except ValueError as exc:
        if str(exc) == "symbol_required":
            raise HTTPException(status_code=422, detail="symbol is required") from exc
        raise


@router.put("/api/watchlist/{item_id}", response_model=WatchlistItem)
def put_watchlist(item_id: int, payload: WatchlistUpdateRequest) -> WatchlistItem:
    try:
        return update_watchlist_item(item_id, payload)
    except ValueError as exc:
        if str(exc) == "watchlist_not_found":
            raise HTTPException(status_code=404, detail="Watchlist item not found") from exc
        raise


@router.delete("/api/watchlist/{item_id}", response_model=WatchlistItem)
def delete_watchlist(item_id: int) -> WatchlistItem:
    try:
        return soft_delete_watchlist_item(item_id)
    except ValueError as exc:
        if str(exc) == "watchlist_not_found":
            raise HTTPException(status_code=404, detail="Watchlist item not found") from exc
        raise


@router.get("/api/rss/feeds", response_model=list[RssFeed])
def get_rss_feeds_endpoint() -> list[RssFeed]:
    return get_rss_feeds()


@router.post("/api/rss/feeds", response_model=RssFeed)
def post_rss_feed(payload: RssFeedCreateRequest) -> RssFeed:
    return create_rss_feed(payload)


@router.put("/api/rss/feeds/{feed_id}", response_model=RssFeed)
def put_rss_feed(feed_id: int, payload: RssFeedUpdateRequest) -> RssFeed:
    try:
        return update_rss_feed(feed_id, payload)
    except ValueError as exc:
        if str(exc) == "feed_not_found":
            raise HTTPException(status_code=404, detail="RSS feed not found") from exc
        raise


@router.post("/api/rss/fetch")
def post_rss_fetch() -> dict[str, int]:
    new_items = fetch_all_active_feeds()
    return {"new_items": new_items}


@router.get("/api/news", response_model=list[NewsItem])
def get_news(limit: int = Query(50, ge=1, le=500)) -> list[NewsItem]:
    return get_latest_news(limit=limit)


@router.post("/api/chat/thread", response_model=ChatThreadCreateResponse)
def post_chat_thread(payload: ChatThreadCreateRequest) -> ChatThreadCreateResponse:
    thread_id, title = create_chat_thread(payload.title)
    return ChatThreadCreateResponse(thread_id=thread_id, title=title)


@router.get("/api/chat/thread/{thread_id}", response_model=ChatThreadResponse)
def get_thread(thread_id: int) -> ChatThreadResponse:
    try:
        title, messages = get_chat_thread(thread_id)
    except ValueError as exc:
        if str(exc) == "thread_not_found":
            raise HTTPException(status_code=404, detail="Thread not found") from exc
        raise

    return ChatThreadResponse(thread_id=thread_id, title=title, messages=messages)


@router.post("/api/chat/thread/{thread_id}/message", response_model=ChatMessageResponse)
def post_thread_message(thread_id: int, payload: ChatMessageRequest) -> ChatMessageResponse:
    latest_news_titles = [item.title for item in get_latest_news(limit=3)]
    orion_reply = generate_orion_reply(payload.content, recent_news=latest_news_titles)

    try:
        user_message, orion_message = add_chat_exchange(thread_id, payload.content, orion_reply)
    except ValueError as exc:
        if str(exc) == "thread_not_found":
            raise HTTPException(status_code=404, detail="Thread not found") from exc
        raise

    watchlist_created = create_watchlist_items_from_requests(orion_reply.watch_requests)
    stored_orion_reply = json.loads(orion_message.content)
    return ChatMessageResponse(
        thread_id=thread_id,
        user_message=user_message,
        orion_message=orion_message,
        orion_reply=stored_orion_reply,
        watchlist_created=watchlist_created,
    )
