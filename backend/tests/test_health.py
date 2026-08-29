from fastapi.testclient import TestClient
from app.main import app


def test_health_check() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["timezone"] == "Asia/Seoul"
    assert "openai_configured" in data
    assert data["openai_model"]
