from fastapi.testclient import TestClient

from app.mainapp import create_app


def test_health_check(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-password")
    client = TestClient(create_app())

    response = client.get("/health", auth=("tester", "test-password"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
