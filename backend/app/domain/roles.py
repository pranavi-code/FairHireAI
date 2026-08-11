"""Versioned approved-role catalog and bounded optional-JD adaptation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ROLE_CONFIG_ROOT = Path(__file__).resolve().parents[3] / "configs" / "roles"
PRIMARY_ROLE_TEMPLATE_PATH = ROLE_CONFIG_ROOT / "junior_backend_developer.v1.json"
ROLE_CATALOG_PATH = ROLE_CONFIG_ROOT / "role_catalog.v1.json"
COMPETENCY_LIBRARY_PATH = ROLE_CONFIG_ROOT / "competency_library.v1.json"
MAPPING_VERSION = "optional-jd-mapper-v2"
ROLE_SELECTION_VERSION = "approved-role-selection-v2"


class QuestionTemplate(BaseModel):
    question_id: str
    prompt: str
    expected_evidence: list[str]


class FollowUpTemplate(BaseModel):
    question_id: str
    trigger_criterion: str
    prompt: str


class CompetencyTemplate(BaseModel):
    competency_id: str
    name: str
    base_weight: float = Field(ge=0.0, le=1.0)
    description: str
    approved_skill_terms: list[str]
    rubric_criteria: list[str]
    core_question: QuestionTemplate
    follow_ups: list[FollowUpTemplate] = Field(min_length=1, max_length=3)


class RoleTemplate(BaseModel):
    schema_version: Literal["role-template-v1"]
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    display_name: str = Field(min_length=3, max_length=120)
    template_version: str
    review_status: Literal["pending_faculty_review", "faculty_approved"]
    supported_title_terms: list[str] = Field(min_length=1)
    supported_seniority_terms: list[str]
    unsupported_title_terms: list[str] = Field(default_factory=list)
    unsupported_seniority_terms: list[str]
    competencies: list[CompetencyTemplate] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_template(self) -> RoleTemplate:
        identifiers = [item.competency_id for item in self.competencies]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Competency identifiers must be unique")
        question_ids = [
            question_id
            for competency in self.competencies
            for question_id in (
                competency.core_question.question_id,
                *(follow_up.question_id for follow_up in competency.follow_ups),
            )
        ]
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("Question identifiers must be unique")
        if abs(sum(item.base_weight for item in self.competencies) - 1.0) > 1e-8:
            raise ValueError("Competency base weights must total 1.0")
        return self


class RoleSummary(BaseModel):
    role_id: str
    display_name: str
    template_version: str
    review_status: Literal["pending_faculty_review", "faculty_approved"]
    supported_title_terms: list[str]
    competency_names: list[str]


class JDMappingRequest(BaseModel):
    job_description: str = Field(min_length=40, max_length=50_000)
    selected_role_id: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]{2,79}$",
    )


class JDMappingResult(BaseModel):
    status: Literal["detected", "unsupported_role", "unsupported_seniority"]
    mapping_version: Literal["optional-jd-mapper-v2"] = MAPPING_VERSION
    role_id: str | None = None
    display_name: str | None = None
    role_template_version: str | None = None
    role_review_status: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    matched_title_terms: list[str] = Field(default_factory=list)
    matched_seniority_terms: list[str] = Field(default_factory=list)
    matched_skills_by_competency: dict[str, list[str]] = Field(default_factory=dict)
    competency_weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_detected_result(self) -> JDMappingResult:
        if self.status == "detected":
            if not self.role_id or not self.competency_weights:
                raise ValueError("Detected roles require an identity and weights")
            if abs(sum(self.competency_weights.values()) - 1.0) > 1e-6:
                raise ValueError("Detected competency weights must total 1.0")
        return self


class AssessmentProfile(BaseModel):
    schema_version: Literal["assessment-profile-v1"] = "assessment-profile-v1"
    source: Literal["approved_role", "job_description"]
    profile_version: str
    role_id: str
    display_name: str
    role_template_version: str
    role_review_status: Literal["pending_faculty_review", "faculty_approved"]
    competency_weights: dict[str, float]
    jd_mapping: JDMappingResult | None = None

    @model_validator(mode="after")
    def validate_profile(self) -> AssessmentProfile:
        if abs(sum(self.competency_weights.values()) - 1.0) > 1e-6:
            raise ValueError("Assessment-profile competency weights must total 1.0")
        if self.source == "job_description":
            if self.jd_mapping is None or self.jd_mapping.status != "detected":
                raise ValueError("JD-based profiles require a detected JD mapping")
        elif self.jd_mapping is not None:
            raise ValueError("Approved-role profiles cannot contain a JD mapping")
        return self


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _primary_role() -> RoleTemplate:
    return RoleTemplate.model_validate(_read_json(PRIMARY_ROLE_TEMPLATE_PATH))


def _load_competency_library() -> dict[str, dict[str, object]]:
    payload = _read_json(COMPETENCY_LIBRARY_PATH)
    if not isinstance(payload, dict) or not isinstance(payload.get("competencies"), list):
        raise ValueError("Invalid competency library")
    result: dict[str, dict[str, object]] = {}
    for item in payload["competencies"]:
        if not isinstance(item, dict) or not isinstance(item.get("competency_id"), str):
            raise ValueError("Invalid competency-library item")
        result[item["competency_id"]] = item
    return result


def _catalog_roles() -> list[RoleTemplate]:
    primary = _primary_role()
    library = {
        item.competency_id: item.model_dump()
        for item in primary.competencies
    }
    library.update(_load_competency_library())
    payload = _read_json(ROLE_CATALOG_PATH)
    if not isinstance(payload, dict) or not isinstance(payload.get("roles"), list):
        raise ValueError("Invalid role catalog")

    roles = [primary]
    for role_definition in payload["roles"]:
        if not isinstance(role_definition, dict):
            raise ValueError("Invalid role definition")
        competency_refs = role_definition.get("competencies")
        if not isinstance(competency_refs, list):
            raise ValueError("Role competencies must be a list")
        competencies: list[dict[str, object]] = []
        for reference in competency_refs:
            if not isinstance(reference, dict):
                raise ValueError("Invalid role competency reference")
            competency_id = reference.get("competency_id")
            if not isinstance(competency_id, str) or competency_id not in library:
                raise ValueError(f"Unknown competency reference: {competency_id}")
            item = dict(library[competency_id])
            item["base_weight"] = reference.get("base_weight")
            competencies.append(item)
        roles.append(
            RoleTemplate.model_validate(
                {
                    "schema_version": "role-template-v1",
                    **role_definition,
                    "competencies": competencies,
                }
            )
        )
    identifiers = [role.role_id for role in roles]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Role identifiers must be unique")
    return roles


def list_role_templates() -> list[RoleTemplate]:
    return _catalog_roles()


def list_role_summaries() -> list[RoleSummary]:
    return [
        RoleSummary(
            role_id=role.role_id,
            display_name=role.display_name,
            template_version=role.template_version,
            review_status=role.review_status,
            supported_title_terms=role.supported_title_terms,
            competency_names=[item.name for item in role.competencies],
        )
        for role in list_role_templates()
    ]


def load_role_template(
    role_id: str = "junior_backend_developer",
    path: str | Path | None = None,
) -> RoleTemplate:
    if path is not None:
        return RoleTemplate.model_validate(_read_json(Path(path)))
    try:
        return next(role for role in list_role_templates() if role.role_id == role_id)
    except StopIteration as exc:
        raise ValueError(f"Unsupported role: {role_id}") from exc


def _normalise(text: str) -> str:
    lowered = text.casefold().replace("â€“", "-").replace("â€”", "-")
    return re.sub(r"\s+", " ", lowered).strip()


def _matches(text: str, terms: list[str]) -> list[str]:
    return sorted({term for term in terms if term.casefold() in text})


def _adjust_weights(
    template: RoleTemplate,
    skill_matches: dict[str, list[str]],
) -> dict[str, float]:
    raw = {
        competency.competency_id: competency.base_weight
        + min(0.03, 0.005 * len(skill_matches[competency.competency_id]))
        for competency in template.competencies
    }
    total = sum(raw.values())
    weights = {key: round(value / total, 8) for key, value in raw.items()}
    final_key = template.competencies[-1].competency_id
    weights[final_key] = round(
        weights[final_key] + round(1.0 - sum(weights.values()), 8),
        8,
    )
    return weights


def _select_role_from_jd(
    normalised: str,
    selected_role_id: str | None,
) -> tuple[RoleTemplate | None, list[str]]:
    if selected_role_id:
        role = load_role_template(selected_role_id)
        return role, _matches(normalised, role.supported_title_terms)
    candidates = [
        (role, _matches(normalised, role.supported_title_terms))
        for role in list_role_templates()
    ]
    candidates = [(role, matches) for role, matches in candidates if matches]
    if not candidates:
        return None, []
    candidates.sort(key=lambda pair: (-len(pair[1]), pair[0].display_name))
    return candidates[0]


def map_supplied_jd(
    job_description: str,
    *,
    selected_role_id: str | None = None,
    template: RoleTemplate | None = None,
) -> JDMappingResult:
    normalised = _normalise(job_description)
    role = template
    title_matches: list[str]
    if role is None:
        role, title_matches = _select_role_from_jd(normalised, selected_role_id)
    else:
        title_matches = _matches(normalised, role.supported_title_terms)
    if role is None:
        return JDMappingResult(
            status="unsupported_role",
            confidence=0.0,
            reason=(
                "The JD does not match an approved role template. Select an "
                "available role or add a reviewed role template before assessment."
            ),
        )

    if not title_matches:
        conflicting_titles = sorted(
            {
                term
                for candidate in list_role_templates()
                if candidate.role_id != role.role_id
                for term in _matches(normalised, candidate.supported_title_terms)
            }
        )
        if conflicting_titles:
            return JDMappingResult(
                status="unsupported_role",
                confidence=1.0,
                reason=(
                    f"The JD title matches a different approved role, not the "
                    f"selected {role.display_name} template."
                ),
                matched_title_terms=conflicting_titles,
            )

    unsupported_seniority = _matches(normalised, role.unsupported_seniority_terms)
    if unsupported_seniority:
        return JDMappingResult(
            status="unsupported_seniority",
            confidence=1.0,
            reason=(
                "The JD targets senior, lead, management, or architecture "
                "responsibility outside the student/early-career assessment scope."
            ),
            matched_seniority_terms=unsupported_seniority,
        )

    seniority = _matches(normalised, role.supported_seniority_terms)
    skill_matches = {
        competency.competency_id: _matches(normalised, competency.approved_skill_terms)
        for competency in role.competencies
    }
    unique_skills = {
        skill for competency_skills in skill_matches.values() for skill in competency_skills
    }
    # A selected role can be confirmed when the JD omits an exact title only if
    # its contents still contain enough approved skill evidence for that rubric.
    if not title_matches and len(unique_skills) < 2:
        return JDMappingResult(
            status="unsupported_role",
            confidence=0.0,
            reason=(
                f"The JD does not contain enough evidence for the selected "
                f"{role.display_name} template."
            ),
        )
    confidence = min(
        1.0,
        0.55
        + (0.20 if title_matches else 0.0)
        + (0.10 if seniority else 0.0)
        + 0.025 * min(len(unique_skills), 6),
    )
    return JDMappingResult(
        status="detected",
        role_id=role.role_id,
        display_name=role.display_name,
        role_template_version=role.template_version,
        role_review_status=role.review_status,
        confidence=confidence,
        reason=(
            f"The JD matched the versioned {role.display_name} template. "
            "Only its approved skill terms adjusted competency weights."
        ),
        matched_title_terms=title_matches,
        matched_seniority_terms=seniority,
        matched_skills_by_competency=skill_matches,
        competency_weights=_adjust_weights(role, skill_matches),
    )


def build_assessment_profile(
    *,
    role_id: str = "junior_backend_developer",
    job_description: str | None = None,
    template: RoleTemplate | None = None,
) -> AssessmentProfile:
    role = template or load_role_template(role_id)
    if job_description is None:
        return AssessmentProfile(
            source="approved_role",
            profile_version=ROLE_SELECTION_VERSION,
            role_id=role.role_id,
            display_name=role.display_name,
            role_template_version=role.template_version,
            role_review_status=role.review_status,
            competency_weights={
                competency.competency_id: competency.base_weight
                for competency in role.competencies
            },
        )
    mapping = map_supplied_jd(job_description, template=role)
    if mapping.status != "detected":
        raise ValueError(mapping.reason)
    return AssessmentProfile(
        source="job_description",
        profile_version=mapping.mapping_version,
        role_id=role.role_id,
        display_name=role.display_name,
        role_template_version=role.template_version,
        role_review_status=role.review_status,
        competency_weights=mapping.competency_weights,
        jd_mapping=mapping,
    )
