from pathlib import Path

from app.main import app
from app.storage.database import init_db
from fastapi.testclient import TestClient


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Orion Trader – OK" in response.text


def test_db_is_initialized() -> None:
    init_db()
    assert Path("data/orion.db").exists()
