import pytest
from fastapi.testclient import TestClient

from backend.app.domain.roles import (
    build_assessment_profile,
    list_role_summaries,
    load_role_template,
    map_supplied_jd,
)
from backend.app.main import app

client = TestClient(app)


def test_role_template_has_six_unique_weighted_competencies() -> None:
    role = load_role_template()
    assert role.role_id == "junior_backend_developer"
    assert len(role.competencies) == 6
    assert sum(item.base_weight for item in role.competencies) == pytest.approx(1.0)
    assert len({item.core_question.question_id for item in role.competencies}) == 6


def test_supplied_backend_jd_maps_only_to_approved_template() -> None:
    result = map_supplied_jd(
        """
        Junior Backend Developer
        We are looking for an entry-level developer to build REST APIs using
        Python, FastAPI, PostgreSQL, SQL, authentication, Docker, unit testing,
        logging, and Git. The engineer will review API validation and database
        indexing with the team.
        """
    )
    assert result.status == "detected"
    assert result.role_id == "junior_backend_developer"
    assert result.confidence == 1.0
    assert sum(result.competency_weights.values()) == 1.0
    assert result.competency_weights["api_design"] > 0.20


def test_catalog_contains_multiple_versioned_roles() -> None:
    roles = list_role_summaries()
    assert len(roles) == 6
    assert {role.role_id for role in roles} >= {
        "junior_backend_developer",
        "junior_frontend_developer",
        "junior_data_analyst",
        "junior_machine_learning_engineer",
    }
    assert all(len(role.competency_names) == 6 for role in roles)


def test_supported_frontend_and_senior_or_ambiguous_jds_are_handled() -> None:
    frontend = map_supplied_jd(
        "Frontend Developer role requiring React, CSS, browser performance, "
        "accessibility, TypeScript, and five years of user-interface experience."
    )
    senior = map_supplied_jd(
        "Senior Backend Engineer responsible for architecture, Java services, "
        "PostgreSQL, mentoring, platform strategy, and seven years of experience."
    )
    ambiguous = map_supplied_jd(
        "Software professional required to collaborate with a product team, "
        "write documentation, attend meetings, test changes, and support users."
    )
    assert frontend.status == "detected"
    assert frontend.role_id == "junior_frontend_developer"
    assert senior.status == "unsupported_seniority"
    assert ambiguous.status == "unsupported_role"


def test_role_api_exposes_mapping_evidence() -> None:
    response = client.post(
        "/api/v1/roles/detect",
        json={
            "job_description": (
                "Backend Intern needed to develop REST API services with Java, "
                "Spring Boot, SQL, PostgreSQL, testing, debugging, and Git."
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "detected"
    assert payload["role_id"] == "junior_backend_developer"
    assert payload["matched_title_terms"] == ["backend intern"]


def test_assessment_profile_uses_base_role_when_jd_is_omitted() -> None:
    profile = build_assessment_profile()

    assert profile.source == "approved_role"
    assert profile.profile_version == "approved-role-selection-v2"
    assert profile.jd_mapping is None
    assert profile.competency_weights["api_design"] == 0.20
    assert sum(profile.competency_weights.values()) == pytest.approx(1.0)


def test_assessment_profile_adapts_only_when_jd_is_supplied() -> None:
    profile = build_assessment_profile(
        job_description=(
            "Junior Backend Developer using REST API design, authentication, "
            "FastAPI, PostgreSQL, SQL, testing, debugging, Docker, and Git."
        )
    )

    assert profile.source == "job_description"
    assert profile.profile_version == "optional-jd-mapper-v2"
    assert profile.jd_mapping is not None
    assert profile.competency_weights["api_design"] > 0.20


def test_role_api_lists_and_loads_catalog_roles() -> None:
    catalog = client.get("/api/v1/roles")
    assert catalog.status_code == 200
    assert len(catalog.json()) == 6

    frontend = client.get("/api/v1/roles/junior_frontend_developer")
    assert frontend.status_code == 200
    assert frontend.json()["display_name"] == "Junior Frontend Developer"
