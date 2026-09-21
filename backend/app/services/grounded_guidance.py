"""Gemini explanations layered over evidence-derived gaps and reviewed RAG resources."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from backend.app.domain.answer_evaluation import TechnicalAnswerEvaluation
from backend.app.domain.roadmap import LearningResource, RoadmapItem, RoadmapResult, SkillGap
from backend.app.domain.roles import load_role_template
from backend.app.providers.gemini import GeminiClient, GeminiProviderError

GAP_PROMPT_VERSION = "evidence-gap-guidance-gemini-v1"
ROADMAP_PROMPT_VERSION = "grounded-roadmap-gemini-v1"


class GapGuidanceItem(BaseModel):
    skill_gap_node_id: str
    competency_id: str
    title: str = Field(min_length=3, max_length=160)
    rationale: str = Field(min_length=20, max_length=1_000)
    practice_focus: list[str] = Field(min_length=1, max_length=4)


class GapGuidanceResponse(BaseModel):
    items: list[GapGuidanceItem] = Field(max_length=6)


class DynamicRoadmapItem(BaseModel):
    skill_gap_node_id: str
    resource_id: str
    priority: int = Field(ge=1, le=6)
    rationale: str = Field(min_length=20, max_length=1_000)


class DynamicRoadmapResponse(BaseModel):
    items: list[DynamicRoadmapItem] = Field(max_length=18)


class GroundedGuidanceService:
    """Use Gemini for narrative guidance without allowing it to invent scores or URLs."""

    def __init__(self, client: GeminiClient) -> None:
        self._client = client

    def generate_gap_guidance(
        self,
        *,
        role_id: str,
        gaps: list[SkillGap],
        evaluations: list[TechnicalAnswerEvaluation],
    ) -> dict[str, GapGuidanceItem]:
        if not gaps:
            return {}
        role = load_role_template(role_id)
        evidence_by_competency: dict[str, list[dict[str, object]]] = {}
        for evaluation in evaluations:
            evidence_by_competency.setdefault(evaluation.competency_id, []).append(
                {
                    "missing_concepts": evaluation.missing_concepts,
                    "weakest_criterion": evaluation.weakest_criterion,
                    "criterion_evidence": [
                        {
                            "criterion": item.criterion,
                            "score": item.score,
                            "rationale": item.rationale,
                        }
                        for item in evaluation.criterion_evidence
                    ],
                }
            )
        payload = {
            "role": role.display_name,
            "fixed_evidence_derived_gaps": [gap.model_dump(mode="json") for gap in gaps],
            "answer_evaluation_evidence": evidence_by_competency,
            "rules": [
                "Explain every supplied gap using only the supplied evaluation evidence.",
                "Do not change, recalculate, omit, or invent any score, target, or gap ID.",
                "Give concrete junior-level practice focuses, not hiring advice.",
                "Do not infer personality, emotion, confidence, or protected traits.",
                "Return exactly one item for every supplied gap and no others.",
            ],
        }
        raw = self._client.generate_json(
            system_instruction=(
                "You explain evidence-backed student skill gaps. Numeric gaps are fixed by the "
                "application; produce only grounded learning guidance as structured JSON."
            ),
            prompt=json.dumps(payload, ensure_ascii=False),
            response_schema=GapGuidanceResponse.model_json_schema(),
        )
        result = GapGuidanceResponse.model_validate(raw)
        expected = {gap.skill_gap_node_id: gap for gap in gaps}
        actual_ids = [item.skill_gap_node_id for item in result.items]
        if len(set(actual_ids)) != len(actual_ids) or set(actual_ids) != set(expected):
            raise GeminiProviderError("Gemini changed the evidence-derived skill-gap set.")
        for item in result.items:
            if item.competency_id != expected[item.skill_gap_node_id].competency_id:
                raise GeminiProviderError("Gemini assigned guidance to the wrong competency.")
        return {item.skill_gap_node_id: item for item in result.items}

    def personalize_roadmap(
        self,
        *,
        role_id: str,
        gaps: list[SkillGap],
        draft: RoadmapResult,
        resources: list[LearningResource],
        gap_guidance: dict[str, GapGuidanceItem],
    ) -> RoadmapResult:
        if not draft.items:
            return draft.model_copy(
                update={"policy_version": "grounded-dynamic-roadmap-gemini-v1"}
            )
        resource_by_id = {item.resource_id: item for item in resources}
        allowed_pairs = {
            (item.skill_gap_node_id, item.resource_id) for item in draft.items
        }
        payload = {
            "role_id": role_id,
            "fixed_skill_gaps": [gap.model_dump(mode="json") for gap in gaps],
            "gap_guidance": {
                key: value.model_dump(mode="json") for key, value in gap_guidance.items()
            },
            "retrieved_approved_resources": [
                resource.model_dump(mode="json") for resource in resources
            ],
            "allowed_gap_resource_pairs": [
                {"skill_gap_node_id": gap_id, "resource_id": resource_id}
                for gap_id, resource_id in sorted(allowed_pairs)
            ],
            "rules": [
                "Return every allowed gap-resource pair exactly once and no other pair.",
                "Prioritize the most severe evidence-backed gap first.",
                "Explain why the specific approved resource addresses the supplied evidence.",
                "Do not invent URLs, resources, scores, credentials, or completion claims.",
                "Give student practice guidance only, never a hiring recommendation.",
            ],
        }
        raw = self._client.generate_json(
            system_instruction=(
                "You personalize a learning roadmap using only retrieved reviewer-approved "
                "resources and evidence-derived gaps. Return structured JSON only."
            ),
            prompt=json.dumps(payload, ensure_ascii=False),
            response_schema=DynamicRoadmapResponse.model_json_schema(),
        )
        result = DynamicRoadmapResponse.model_validate(raw)
        returned_pairs = [
            (item.skill_gap_node_id, item.resource_id) for item in result.items
        ]
        if len(set(returned_pairs)) != len(returned_pairs) or set(returned_pairs) != allowed_pairs:
            raise GeminiProviderError("Gemini changed the reviewed RAG roadmap resource set.")
        if any(resource_id not in resource_by_id for _, resource_id in returned_pairs):
            raise GeminiProviderError("Gemini referenced an unapproved roadmap resource.")
        ordered = sorted(result.items, key=lambda item: (item.priority, item.resource_id))
        return RoadmapResult(
            policy_version="grounded-dynamic-roadmap-gemini-v1",
            items=[
                RoadmapItem(
                    skill_gap_node_id=item.skill_gap_node_id,
                    competency_id=next(
                        gap.competency_id
                        for gap in gaps
                        if gap.skill_gap_node_id == item.skill_gap_node_id
                    ),
                    resource_id=item.resource_id,
                    priority=item.priority,
                    rationale=item.rationale,
                )
                for item in ordered
            ],
            unresolved_skill_gap_node_ids=draft.unresolved_skill_gap_node_ids,
            safety_note=(
                "Gemini personalized the sequence and rationale using only evidence-derived gaps "
                "and reviewer-approved resources returned by Hybrid RAG."
            ),
        )
