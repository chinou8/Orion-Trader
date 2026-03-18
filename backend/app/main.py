import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.council.market_regime import compute_daily_context
from app.council.news_aggregator import start_news_scheduler, stop_news_scheduler
from app.council.schema import init_council_db
from app.core.config import settings
from app.decision.scheduler import start_scheduler, stop_scheduler
from app.storage.database import init_db

app = FastAPI(title="Orion Trader API", version="0.1.0")

app_env = os.getenv("APP_ENV", "dev").lower()
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

if app_env == "dev":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin, "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(router)


@app.on_event("startup")
def startup_event() -> None:
    init_db()                           # v1 tables
    init_council_db(settings.db_path)  # v2 tables (AI Council)
    start_scheduler()                   # v1 committee (toutes les 30 min)
    start_news_scheduler()              # v2 news polling (toutes les 5 min)
    # Calcul async du contexte marché — lancé en arrière-plan, sans bloquer le startup
    asyncio.get_event_loop().create_task(compute_daily_context())


@app.on_event("shutdown")
def shutdown_event() -> None:
    stop_scheduler()
    stop_news_scheduler()
