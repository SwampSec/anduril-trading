import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.mark.unit
def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["api_port"] == 9001


@pytest.mark.unit
def test_bot_status_endpoint():
    client = TestClient(app)
    response = client.get("/bot/status")
    assert response.status_code == 200
    data = response.json()
    assert "armed" in data
    assert data["armed"] is False


@pytest.mark.unit
def test_ibkr_status_without_connect():
    client = TestClient(app)
    response = client.get("/ibkr/status")
    assert response.status_code == 200
    assert response.json()["connected"] is False
