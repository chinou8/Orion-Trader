from fastapi import FastAPI

from app.api.routes import router
from app.storage.database import init_db

app = FastAPI(title="Orion Trader API", version="0.1.0")
app.include_router(router)


@app.on_event("startup")
def startup_event() -> None:
    init_db()
