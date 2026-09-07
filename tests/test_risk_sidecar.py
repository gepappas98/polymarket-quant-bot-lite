from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_is_live():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
