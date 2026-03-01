import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
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
    init_db()
