from pathlib import Path

import pytest
from app.core.config import settings
from app.main import app
from app.storage.database import init_db
from fastapi.testclient import TestClient


@pytest.fixture()
def isolated_db(tmp_path: Path) -> Path:
    original_db_path = settings.db_path
    test_db_path = tmp_path / "orion-test.db"
    settings.db_path = test_db_path
    init_db()
    yield test_db_path
    settings.db_path = original_db_path


def test_health_endpoint(isolated_db: Path) -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page(isolated_db: Path) -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Orion Trader – OK" in response.text


def test_db_is_initialized(isolated_db: Path) -> None:
    assert isolated_db.exists()


def test_get_settings_returns_defaults(isolated_db: Path) -> None:
    client = TestClient(app)
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "markets_enabled": {"EU": True, "US": False},
        "max_trades_per_day": 8,
        "boost_trades_per_day": 10,
        "boost_threshold_liquid": 0.04,
        "boost_threshold_illiquid": 0.1,
        "bonds_auto_enabled": False,
        "bonds_allocation_cap": 0.25,
        "divergence_liquid": 0.02,
        "divergence_illiquid": 0.05,
        "default_order_type_equity": "LIMIT",
    }


def test_put_settings_persists_and_get_matches(isolated_db: Path) -> None:
    client = TestClient(app)
    payload = {
        "markets_enabled": {"EU": True, "US": True},
        "max_trades_per_day": 9,
        "boost_trades_per_day": 12,
        "boost_threshold_liquid": 0.06,
        "boost_threshold_illiquid": 0.12,
        "bonds_auto_enabled": True,
        "bonds_allocation_cap": 0.3,
        "divergence_liquid": 0.03,
        "divergence_illiquid": 0.06,
        "default_order_type_equity": "LIMIT",
    }

    put_response = client.put("/api/settings", json=payload)
    assert put_response.status_code == 200
    assert put_response.json() == payload

    get_response = client.get("/api/settings")
    assert get_response.status_code == 200
    assert get_response.json() == payload
