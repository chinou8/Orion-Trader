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


def test_create_thread_and_post_message_and_get_thread(isolated_db: Path) -> None:
    client = TestClient(app)

    create_response = client.post("/api/chat/thread", json={"title": "Daily checks"})
    assert create_response.status_code == 200
    thread_payload = create_response.json()
    thread_id = thread_payload["thread_id"]
    assert thread_payload["title"] == "Daily checks"

    message_response = client.post(
        f"/api/chat/thread/{thread_id}/message",
        json={"content": "Surveille NVDA et TSLA"},
    )
    assert message_response.status_code == 200
    message_payload = message_response.json()
    assert message_payload["thread_id"] == thread_id
    assert message_payload["user_message"]["role"] == "user"
    assert message_payload["orion_message"]["role"] == "orion"
    assert message_payload["orion_reply"]["reply_text"]
    assert message_payload["orion_reply"]["watch_requests"]

    thread_response = client.get(f"/api/chat/thread/{thread_id}")
    assert thread_response.status_code == 200
    thread_data = thread_response.json()
    assert thread_data["thread_id"] == thread_id
    assert len(thread_data["messages"]) == 2
    assert thread_data["messages"][0]["role"] == "user"
    assert thread_data["messages"][1]["role"] == "orion"


def test_post_watchlist_item(isolated_db: Path) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/watchlist",
        json={"symbol": "AIR.PA", "notes": "Core watch candidate"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "AIR.PA"
    assert payload["is_active"] is True


def test_chat_surveille_creates_watchlist_item(isolated_db: Path) -> None:
    client = TestClient(app)

    create_thread = client.post("/api/chat/thread", json={"title": "Watchlist Thread"})
    assert create_thread.status_code == 200
    thread_id = create_thread.json()["thread_id"]

    message_response = client.post(
        f"/api/chat/thread/{thread_id}/message",
        json={"content": "surveille AIR.PA"},
    )
    assert message_response.status_code == 200
    body = message_response.json()
    assert body["watchlist_created"]
    assert body["watchlist_created"][0]["symbol"] == "AIR.PA"

    watchlist_response = client.get("/api/watchlist")
    assert watchlist_response.status_code == 200
    symbols = [item["symbol"] for item in watchlist_response.json()]
    assert "AIR.PA" in symbols


def test_trade_proposal_lifecycle_and_chat_creation(isolated_db: Path) -> None:
    client = TestClient(app)

    create_response = client.post(
        "/api/proposals",
        json={
            "symbol": "AIR.PA",
            "asset_type": "EQUITY",
            "market": "EU",
            "side": "BUY",
            "horizon_window": "5-15 jours",
            "thesis_json": "{}",
        },
    )
    assert create_response.status_code == 200
    proposal = create_response.json()
    proposal_id = proposal["id"]
    assert proposal["status"] == "PENDING"

    list_response = client.get("/api/proposals?status=PENDING&limit=10")
    assert list_response.status_code == 200
    pending_ids = [item["id"] for item in list_response.json()]
    assert proposal_id in pending_ids

    approve_response = client.post(
        f"/api/proposals/{proposal_id}/approve",
        json={"approved_by": "qa-user"},
    )
    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "APPROVED"

    reject_response = client.post(
        f"/api/proposals/{proposal_id}/reject",
        json={"notes": "Changed thesis"},
    )
    assert reject_response.status_code == 200
    assert reject_response.json()["status"] == "REJECTED"

    thread_response = client.post("/api/chat/thread", json={"title": "Trade ideas"})
    assert thread_response.status_code == 200
    thread_id = thread_response.json()["thread_id"]

    chat_response = client.post(
        f"/api/chat/thread/{thread_id}/message",
        json={"content": "propose un trade sur AIR.PA"},
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()
    assert payload["orion_reply"]["proposal_created"] is not None
    assert payload["orion_reply"]["proposal_created"]["symbol"] == "AIR.PA"
