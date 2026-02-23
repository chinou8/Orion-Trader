from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.core.trading_settings import TradingSettings
from app.storage.database import get_trading_settings, save_trading_settings

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
