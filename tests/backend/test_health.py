from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.app.config import Settings
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


def test_public_api_accepts_a_separately_supervised_trusted_worker() -> None:
    settings = Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="publishable-test-key",
        gemini_api_key=SecretStr("private-test-key"),
        trusted_worker_available=True,
        model_checkpoint_path="Z:/intentionally-not-mounted/best.pt",
        model_run_name="fi_v2_mag_bert",
        model_checkpoint_sha256="a" * 64,
    )

    assert settings.model_ready is False
    assert settings.worker_configured is False
    assert settings.worker_runtime_ready is True
    assert settings.processing_ready is True
