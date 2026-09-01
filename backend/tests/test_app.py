from fastapi.testclient import TestClient

from due_diligence_copilot.main import app

client = TestClient(app)


def test_liveness_is_available_without_external_services() -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
