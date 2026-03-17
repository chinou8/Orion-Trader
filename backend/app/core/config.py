from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    execution_mode: str = "IBKR_PAPER"
    db_path: Path = Path("./data/orion.db")


settings = Settings()
