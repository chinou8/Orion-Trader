import json
import time

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
from app.core.proposal import (
    ProposalCreated,
    TradeProposal,
    TradeProposalActionRequest,
    TradeProposalCreateRequest,
    TradeProposalUpdateRequest,
)
from app.core.rss import NewsItem, RssFeed, RssFeedCreateRequest, RssFeedUpdateRequest
from app.core.simulator import (
    EquityCurvePoint,
    PerformanceSummary,
    PortfolioResponse,
    Reflection,
    SimulatedTrade,
)
from app.core.trading_settings import TradingSettings
from app.core.watchlist import WatchlistCreateRequest, WatchlistItem, WatchlistUpdateRequest
from app.marketdata.indicators import compute_indicators
from app.marketdata.stooq import fetch_stooq_daily
from app.rss.service import fetch_all_active_feeds
from app.storage.database import (
    add_chat_exchange,
    approve_trade_proposal,
    create_chat_thread,
    create_rss_feed,
    create_trade_proposal,
    create_watchlist_item,
    create_watchlist_items_from_requests,
    execute_simulated_trade,
    get_active_watchlist_symbols,
    get_chat_thread,
    get_equity_curve,
    get_latest_news,
    get_market_bars,
    get_market_closes,
    get_performance_summary,
    get_portfolio,
    get_rss_feeds,
    get_trading_settings,
    get_watchlist_items,
    insert_market_bars,
    list_reflections,
    list_simulated_trades,
    list_trade_proposals,
    reject_trade_proposal,
    save_trading_settings,
    soft_delete_watchlist_item,
    update_rss_feed,
    update_trade_proposal,
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


@router.post("/api/market/fetch")
def post_market_fetch(symbol: str = Query(..., min_length=1)) -> dict[str, object]:
    bars, candidate, errors, status = fetch_stooq_daily(symbol)
    if not bars:
        return {
            "symbol": symbol.upper(),
            "inserted": 0,
            "candidate": candidate,
            "errors": errors,
            "status": status or "empty",
        }

    payload = [
        {
            "ts": bar.ts,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]
    inserted = insert_market_bars(
        symbol=symbol.upper(),
        timeframe="1d",
        source=f"stooq:{candidate or 'unknown'}",
        bars=payload,
    )
    return {
        "symbol": symbol.upper(),
        "inserted": inserted,
        "candidate": candidate,
        "errors": errors,
        "status": "ok",
    }


@router.get("/api/market/bars")
def get_market_bars_endpoint(
    symbol: str = Query(..., min_length=1), limit: int = Query(200, ge=1, le=1000)
) -> list[dict[str, object]]:
    bars = get_market_bars(symbol=symbol.upper(), timeframe="1d", limit=limit)
    return [bar.model_dump() for bar in bars]


@router.get("/api/market/indicators")
def get_market_indicators(symbol: str = Query(..., min_length=1)) -> dict[str, object]:
    closes = get_market_closes(symbol.upper(), timeframe="1d", limit=250)
    indicators = compute_indicators(symbol.upper(), closes)
    return indicators.model_dump()


@router.post("/api/market/fetch_watchlist")
def post_market_fetch_watchlist() -> dict[str, object]:
    symbols = get_active_watchlist_symbols()
    summary: list[dict[str, object]] = []

    for symbol in symbols:
        bars, candidate, errors, status = fetch_stooq_daily(symbol)
        inserted = 0
        if bars:
            inserted = insert_market_bars(
                symbol=symbol,
                timeframe="1d",
                source=f"stooq:{candidate or 'unknown'}",
                bars=[
                    {
                        "ts": bar.ts,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ],
            )
            status = "ok"

        summary.append(
            {
                "symbol": symbol,
                "inserted": inserted,
                "candidate": candidate,
                "errors": errors,
                "status": status or "empty",
            }
        )
        time.sleep(0.2)

    return {"count": len(summary), "results": summary}




@router.get("/api/proposals", response_model=list[TradeProposal])
def get_proposals(
    status: str | None = None,
    limit: int = Query(100, ge=1, le=500),
) -> list[TradeProposal]:
    return list_trade_proposals(status=status, limit=limit)


@router.post("/api/proposals", response_model=TradeProposal)
def post_proposal(payload: TradeProposalCreateRequest) -> TradeProposal:
    return create_trade_proposal(payload)


@router.put("/api/proposals/{proposal_id}", response_model=TradeProposal)
def put_proposal(proposal_id: int, payload: TradeProposalUpdateRequest) -> TradeProposal:
    try:
        return update_trade_proposal(proposal_id, payload)
    except ValueError as exc:
        if str(exc) == "proposal_not_found":
            raise HTTPException(status_code=404, detail="Proposal not found") from exc
        if str(exc) == "bond_status_locked":
            raise HTTPException(
                status_code=422,
                detail="Bond proposals cannot change status automatically",
            ) from exc
        raise


@router.post("/api/proposals/{proposal_id}/approve", response_model=TradeProposal)
def post_proposal_approve(proposal_id: int, payload: TradeProposalActionRequest) -> TradeProposal:
    try:
        return approve_trade_proposal(proposal_id, payload)
    except ValueError as exc:
        if str(exc) == "proposal_not_found":
            raise HTTPException(status_code=404, detail="Proposal not found") from exc
        raise


@router.post("/api/proposals/{proposal_id}/reject", response_model=TradeProposal)
def post_proposal_reject(proposal_id: int, payload: TradeProposalActionRequest) -> TradeProposal:
    try:
        return reject_trade_proposal(proposal_id, payload)
    except ValueError as exc:
        if str(exc) == "proposal_not_found":
            raise HTTPException(status_code=404, detail="Proposal not found") from exc
        raise




@router.post("/api/proposals/{proposal_id}/execute_simulated")
def post_proposal_execute_simulated(proposal_id: int) -> dict[str, object]:
    try:
        proposal, trade, portfolio_state, reflection = execute_simulated_trade(proposal_id)
    except ValueError as exc:
        if str(exc) == "proposal_not_found":
            raise HTTPException(status_code=404, detail="Proposal not found") from exc
        if str(exc) == "proposal_not_approved":
            raise HTTPException(status_code=422, detail="Proposal must be APPROVED") from exc
        if str(exc) == "unsupported_asset_type":
            raise HTTPException(status_code=422, detail="Only EQUITY/ETF can be simulated") from exc
        if str(exc) == "market_data_missing":
            raise HTTPException(
                status_code=422,
                detail="No market data available for symbol",
            ) from exc
        if str(exc) == "invalid_qty":
            raise HTTPException(status_code=422, detail="Proposal qty must be > 0") from exc
        raise

    return {
        "proposal": proposal.model_dump(),
        "trade": trade.model_dump(),
        "portfolio_state": portfolio_state.model_dump(),
        "reflection": reflection.model_dump(),
    }


@router.get("/api/portfolio", response_model=PortfolioResponse)
def get_portfolio_endpoint() -> PortfolioResponse:
    return get_portfolio()




@router.get("/api/portfolio/equity_curve", response_model=list[EquityCurvePoint])
def get_portfolio_equity_curve(limit: int = Query(500, ge=1, le=2000)) -> list[EquityCurvePoint]:
    return get_equity_curve(limit=limit)


@router.get("/api/portfolio/performance_summary", response_model=PerformanceSummary)
def get_portfolio_performance_summary() -> PerformanceSummary:
    return get_performance_summary()

@router.get("/api/trades", response_model=list[SimulatedTrade])
def get_trades(limit: int = Query(200, ge=1, le=1000)) -> list[SimulatedTrade]:
    return list_simulated_trades(limit=limit)


@router.get("/api/reflections", response_model=list[Reflection])
def get_reflections(limit: int = Query(200, ge=1, le=1000)) -> list[Reflection]:
    return list_reflections(limit=limit)


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
    market_analysis: dict[str, object] | None = None
    proposal_created: ProposalCreated | None = None
    lower_text = payload.content.lower()
    if "analyse" in lower_text:
        tokens = payload.content.upper().replace(",", " ").split()
        symbol = next((t for t in tokens if "." in t or t.isalpha()), "")
        symbol = symbol.replace("ANALYSE", "").strip()
        if symbol:
            closes = get_market_closes(symbol=symbol, timeframe="1d", limit=250)
            if closes:
                indicators = compute_indicators(symbol, closes)
                trend = (
                    "bullish"
                    if (indicators.sma20 or 0) > (indicators.sma50 or 0)
                    else "neutral/bearish"
                )
                market_analysis = {
                    "symbol": symbol,
                    "trend": trend,
                    "rsi14": indicators.rsi14,
                    "volatility": indicators.volatility,
                    "horizon_hint": indicators.horizon_hint,
                }
            else:
                market_analysis = {
                    "symbol": symbol,
                    "trend": "unknown",
                    "rsi14": None,
                    "volatility": None,
                    "horizon_hint": "pas de données, lance un fetch",
                }

    if "propose un trade" in lower_text or "acheter" in lower_text:
        tokens = payload.content.upper().replace(",", " ").split()
        symbol = next(
            (
                t
                for t in tokens
                if "." in t
                or (
                    t.isalpha()
                    and t not in {"PROPOSE", "UN", "TRADE", "SUR", "ACHETER"}
                )
            ),
            "",
        )
        symbol = symbol.strip()
        if symbol:
            closes = get_market_closes(symbol=symbol, timeframe="1d", limit=250)
            indicators = compute_indicators(symbol, closes)
            horizon_window = "5-15 jours"
            if indicators.horizon_hint == "jours":
                horizon_window = "2-5 jours"
            elif indicators.horizon_hint == "semaines/mois":
                horizon_window = "1-3 mois"

            thesis = {
                "horizon_hint": indicators.horizon_hint,
                "rsi14": indicators.rsi14,
                "volatility": indicators.volatility,
                "news_refs": latest_news_titles[:3],
            }
            created = create_trade_proposal(
                TradeProposalCreateRequest(
                    symbol=symbol,
                    asset_type="EQUITY",
                    market="EU" if symbol.endswith(".PA") else "US",
                    side="BUY" if "acheter" in lower_text else "HOLD",
                    order_type="LIMIT",
                    horizon_window=horizon_window,
                    thesis_json=json.dumps(thesis),
                    status="PENDING",
                )
            )
            proposal_created = ProposalCreated(
                id=created.id,
                symbol=created.symbol,
                side=created.side,
                horizon_window=created.horizon_window,
            )

    orion_reply = generate_orion_reply(
        payload.content,
        recent_news=latest_news_titles,
        market_analysis=market_analysis,
        proposal_created=proposal_created,
    )

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
