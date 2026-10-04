from fastapi.testclient import TestClient
from health_api.main import app


def test_healthcheck() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
