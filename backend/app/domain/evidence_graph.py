"""Validated Competency Evidence Graph records and transparent scorecards."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.roles import RoleTemplate, load_role_template

NodeType = Literal[
    "Student",
    "Attempt",
    "TargetRole",
    "JobDescription",
    "Competency",
    "ResumeClaim",
    "Question",
    "AnswerSegment",
    "TranscriptSpan",
    "AudioEvidence",
    "VisualEvidence",
    "ModelPrediction",
    "ShapAttribution",
    "EvidenceClaim",
    "SkillGap",
    "RoadmapItem",
    "ProgressMetric",
]
EdgeType = Literal[
    "requires",
    "claims",
    "tests",
    "answered_by",
    "transcribed_as",
    "has_audio_evidence",
    "has_visual_evidence",
    "predicted_by",
    "explained_by",
    "supports",
    "contradicts",
    "indicates_gap",
    "recommends",
    "improves_over",
]
Visibility = Literal["private", "student", "reviewer", "system"]

STRICT_EDGE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "requires": ("TargetRole", "Competency"),
    "claims": ("Student", "ResumeClaim"),
    "tests": ("Question", "Competency"),
    "answered_by": ("Question", "AnswerSegment"),
    "transcribed_as": ("AnswerSegment", "TranscriptSpan"),
    "has_audio_evidence": ("AnswerSegment", "AudioEvidence"),
    "has_visual_evidence": ("AnswerSegment", "VisualEvidence"),
    "predicted_by": ("AnswerSegment", "ModelPrediction"),
    "explained_by": ("ModelPrediction", "ShapAttribution"),
    "indicates_gap": ("Competency", "SkillGap"),
    "recommends": ("SkillGap", "RoadmapItem"),
    "improves_over": ("ProgressMetric", "ProgressMetric"),
}


class GraphNode(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    type: NodeType
    source: str = Field(min_length=1, max_length=200)
    attempt_id: UUID
    created_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    visibility: Visibility
    normalized_text: str | None = Field(default=None, max_length=10_000)
    raw_reference: str | None = Field(default=None, max_length=2_000)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timestamp(self) -> GraphNode:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        return self


class GraphEdge(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9:_-]{2,119}$")
    type: EdgeType
    source: str = Field(min_length=1, max_length=200)
    attempt_id: UUID
    created_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    visibility: Visibility
    normalized_text: str | None = Field(default=None, max_length=10_000)
    raw_reference: str | None = Field(default=None, max_length=2_000)
    source_node_id: str
    target_node_id: str
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_timestamp(self) -> GraphEdge:
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must include a timezone")
        if self.source_node_id == self.target_node_id and self.type != "improves_over":
            raise ValueError("Self-referential graph edges are not allowed")
        return self


class EvidenceGraph(BaseModel):
    schema_version: Literal["competency-evidence-graph-v1"] = "competency-evidence-graph-v1"
    attempt_id: UUID
    nodes: list[GraphNode] = Field(min_length=1, max_length=20_000)
    edges: list[GraphEdge] = Field(default_factory=list, max_length=50_000)

    @model_validator(mode="after")
    def validate_graph(self) -> EvidenceGraph:
        node_by_id = {node.id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("Graph node identifiers must be unique")
        if len({edge.id for edge in self.edges}) != len(self.edges):
            raise ValueError("Graph edge identifiers must be unique")
        if any(node.attempt_id != self.attempt_id for node in self.nodes):
            raise ValueError("Every node must belong to the graph attempt")
        if any(edge.attempt_id != self.attempt_id for edge in self.edges):
            raise ValueError("Every edge must belong to the graph attempt")
        for edge in self.edges:
            if edge.source_node_id not in node_by_id or edge.target_node_id not in node_by_id:
                raise ValueError(f"Graph edge {edge.id} references a missing node")
            expected = STRICT_EDGE_ENDPOINTS.get(edge.type)
            if expected:
                actual = (
                    node_by_id[edge.source_node_id].type,
                    node_by_id[edge.target_node_id].type,
                )
                if actual != expected:
                    raise ValueError(f"Edge {edge.type} requires {expected}, received {actual}")
        return self


class MetricEvidence(BaseModel):
    value: float | None = Field(default=None, ge=0.0, le=1.0)
    applicable: bool = True
    evidence_node_ids: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_evidence(self) -> MetricEvidence:
        if self.applicable and self.value is None:
            raise ValueError("Applicable metrics require a value")
        if self.applicable and not self.evidence_node_ids:
            raise ValueError("Applicable metrics require evidence node references")
        if not self.applicable and self.value is not None:
            raise ValueError("Non-applicable metrics cannot contain a value")
        return self


class ScorecardEvidence(BaseModel):
    competency_rubric_scores: dict[str, MetricEvidence]
    competency_coverage: dict[str, MetricEvidence]
    answer_depth_and_correctness: MetricEvidence
    technical_follow_up_quality: MetricEvidence
    resume_project_consistency: MetricEvidence
    answer_relevance: MetricEvidence
    answer_structure: MetricEvidence
    answer_completeness: MetricEvidence
    pace_and_filler_quality: MetricEvidence
    transcript_confidence: MetricEvidence
    follow_up_responsiveness: MetricEvidence
    professionalism_rubric: MetricEvidence
    evidence_confidence: MetricEvidence
    signal_quality: MetricEvidence


class ScorecardRequest(BaseModel):
    graph: EvidenceGraph
    role_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,79}$")
    role_template_version: str
    competency_weights: dict[str, float]
    evidence: ScorecardEvidence

    @model_validator(mode="after")
    def validate_weights(self) -> ScorecardRequest:
        if abs(sum(self.competency_weights.values()) - 1.0) > 1e-6:
            raise ValueError("competency_weights must total 1.0")
        return self


class CompetencyScore(BaseModel):
    competency_id: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    coverage: float = Field(ge=0.0, le=1.0)
    sufficient_evidence: bool


class ScorecardResult(BaseModel):
    formula_version: Literal["readiness-scorecard-v1"] = "readiness-scorecard-v1"
    attempt_id: UUID
    competency_scores: list[CompetencyScore]
    technical_readiness: float = Field(ge=0.0, le=1.0)
    communication_clarity: float = Field(ge=0.0, le=1.0)
    interview_response_quality: float = Field(ge=0.0, le=1.0)
    placement_readiness: float | None = Field(default=None, ge=0.0, le=1.0)
    overall_evidence_confidence: float = Field(ge=0.0, le=1.0)
    sufficient_evidence: bool
    insufficiency_reasons: list[str]
    safety_note: str


def _weighted_metric(
    weighted_values: list[tuple[float, MetricEvidence]],
) -> float:
    applicable = [(weight, metric) for weight, metric in weighted_values if metric.applicable]
    if not applicable:
        raise ValueError("At least one score component must be applicable")
    denominator = sum(weight for weight, _ in applicable)
    value = sum(weight * float(metric.value) for weight, metric in applicable) / denominator
    return max(0.0, min(1.0, value))


def _all_metric_evidence(evidence: ScorecardEvidence) -> list[MetricEvidence]:
    direct = [
        evidence.answer_depth_and_correctness,
        evidence.technical_follow_up_quality,
        evidence.resume_project_consistency,
        evidence.answer_relevance,
        evidence.answer_structure,
        evidence.answer_completeness,
        evidence.pace_and_filler_quality,
        evidence.transcript_confidence,
        evidence.follow_up_responsiveness,
        evidence.professionalism_rubric,
        evidence.evidence_confidence,
        evidence.signal_quality,
    ]
    return [
        *evidence.competency_rubric_scores.values(),
        *evidence.competency_coverage.values(),
        *direct,
    ]


def calculate_scorecard(
    request: ScorecardRequest,
    *,
    template: RoleTemplate | None = None,
) -> ScorecardResult:
    role = template or load_role_template(request.role_id)
    if request.role_id != role.role_id:
        raise ValueError("The scorecard role does not match the loaded role template")
    if request.role_template_version != role.template_version:
        raise ValueError("The scorecard role-template version is unsupported")
    competency_ids = {item.competency_id for item in role.competencies}
    if set(request.competency_weights) != competency_ids:
        raise ValueError("competency_weights must contain exactly the role competencies")
    if set(request.evidence.competency_rubric_scores) != competency_ids:
        raise ValueError("A rubric score is required for every role competency")
    if set(request.evidence.competency_coverage) != competency_ids:
        raise ValueError("Coverage is required for every role competency")

    node_ids = {node.id for node in request.graph.nodes}
    referenced = {
        node_id
        for metric in _all_metric_evidence(request.evidence)
        for node_id in metric.evidence_node_ids
    }
    missing = referenced - node_ids
    if missing:
        raise ValueError(f"Scorecard evidence references missing nodes: {sorted(missing)}")

    competency_scores: list[CompetencyScore] = []
    for competency in role.competencies:
        score_metric = request.evidence.competency_rubric_scores[
            competency.competency_id
        ]
        coverage_metric = request.evidence.competency_coverage[
            competency.competency_id
        ]
        score = round(float(score_metric.value), 6) if score_metric.applicable else None
        coverage = (
            round(float(coverage_metric.value), 6)
            if coverage_metric.applicable
            else 0.0
        )
        competency_scores.append(
            CompetencyScore(
                competency_id=competency.competency_id,
                score=score,
                coverage=coverage,
                sufficient_evidence=(score is not None and coverage >= 0.70),
            )
        )

    assessed_competencies = [item for item in competency_scores if item.score is not None]
    if not assessed_competencies:
        raise ValueError("At least one assessed competency is required")
    assessed_weight = sum(
        request.competency_weights[item.competency_id]
        for item in assessed_competencies
    )
    technical_rubric_match = sum(
        request.competency_weights[item.competency_id] * float(item.score)
        for item in assessed_competencies
    ) / assessed_weight
    # Decimal weights represented as binary floats can make an exact normalized
    # score drift just outside the schema boundary (for example,
    # 1.0000000000000002). Clamp before validating it as MetricEvidence.
    technical_rubric_match = max(0.0, min(1.0, technical_rubric_match))
    technical = _weighted_metric(
        [
            (
                0.35,
                MetricEvidence(
                    value=technical_rubric_match,
                    evidence_node_ids=[
                        node_id
                        for metric in request.evidence.competency_rubric_scores.values()
                        if metric.applicable
                        for node_id in metric.evidence_node_ids
                    ],
                ),
            ),
            (0.25, request.evidence.answer_depth_and_correctness),
            (0.20, request.evidence.technical_follow_up_quality),
            (0.20, request.evidence.resume_project_consistency),
        ]
    )
    communication = _weighted_metric(
        [
            (0.30, request.evidence.answer_relevance),
            (0.25, request.evidence.answer_structure),
            (0.20, request.evidence.answer_completeness),
            (0.15, request.evidence.pace_and_filler_quality),
            (0.10, request.evidence.transcript_confidence),
        ]
    )
    response_quality = _weighted_metric(
        [
            (0.35, request.evidence.follow_up_responsiveness),
            (0.30, request.evidence.answer_completeness),
            (0.20, request.evidence.resume_project_consistency),
            (0.15, request.evidence.professionalism_rubric),
        ]
    )
    evidence_confidence = float(request.evidence.evidence_confidence.value)
    signal_quality = float(request.evidence.signal_quality.value)
    overall_confidence = evidence_confidence * signal_quality
    insufficiency_reasons = [
        (
            f"Not assessed before interview submission: {item.competency_id}"
            if item.score is None
            else f"Insufficient evidence for {item.competency_id}"
        )
        for item in competency_scores
        if not item.sufficient_evidence
    ]
    if overall_confidence < 0.60:
        insufficiency_reasons.append(
            "Combined evidence confidence and signal quality is below 0.60"
        )
    sufficient = not insufficiency_reasons
    placement = (
        0.50 * technical + 0.25 * communication + 0.25 * response_quality if sufficient else None
    )
    return ScorecardResult(
        attempt_id=request.graph.attempt_id,
        competency_scores=competency_scores,
        technical_readiness=round(technical, 6),
        communication_clarity=round(communication, 6),
        interview_response_quality=round(response_quality, 6),
        placement_readiness=round(placement, 6) if placement is not None else None,
        overall_evidence_confidence=round(overall_confidence, 6),
        sufficient_evidence=sufficient,
        insufficiency_reasons=insufficiency_reasons,
        safety_note=(
            "Scores are evidence-backed placement-readiness feedback for student "
            "self-improvement. They are not hiring decisions or student rankings. "
            "Delivery signals are excluded from Placement Readiness."
        ),
    )
