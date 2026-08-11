from fastapi.testclient import TestClient

from backend.app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "fairhireai-backend",
        "version": "0.2.0",
    }


def test_openapi_metadata() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "FairHireAI API"
    assert schema["info"]["version"] == "0.2.0"


def test_capabilities_publish_the_verified_selected_checkpoint() -> None:
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    payload = response.json()
    assert payload["backend"] == "ready"
    assert payload["role_catalog_ready"] is True
    assert payload["model_inference"] == "ready"
