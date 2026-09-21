from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/resume-evidence/validate",
            {
                "document_sha256": "a" * 64,
                "extractor_name": "test",
                "extractor_version": "1.0.0",
                "claims": [],
            },
        ),
        (
            "/api/v1/interviews/next-question",
            {
                "attempt_id": str(uuid4()),
                "role_id": "junior_backend_developer",
                "role_template_version": "1.0.0",
                "competency_weights": {
                    "programming_fundamentals": 0.2,
                    "api_design": 0.2,
                    "database_reasoning": 0.2,
                    "debugging_problem_solving": 0.15,
                    "system_design_basics": 0.15,
                    "technical_communication": 0.1,
                },
                "progress": [],
                "answered_question_ids": [],
            },
        ),
        ("/api/v1/evidence/validate", {"attempt_id": str(uuid4()), "nodes": [], "edges": []}),
        ("/api/v1/evidence/scorecard", {}),
        ("/api/v1/roadmap/plan", {}),
    ],
)
def test_internal_utility_endpoints_reject_anonymous_callers(
    path: str,
    payload: dict[str, object],
) -> None:
    response = TestClient(app).post(path, json=payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "A Supabase user access token is required."
