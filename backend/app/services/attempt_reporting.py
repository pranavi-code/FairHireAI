"""Build the final evidence graph, transparent scorecard, gaps, and roadmap."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import fmean
from typing import Any
from uuid import UUID

from backend.app.domain.answer_evaluation import TechnicalAnswerEvaluation
from backend.app.domain.evidence_graph import (
    EvidenceGraph,
    GraphEdge,
    GraphNode,
    MetricEvidence,
    ScorecardEvidence,
    ScorecardRequest,
    calculate_scorecard,
)
from backend.app.domain.interviews import FOLLOW_UP_THRESHOLD
from backend.app.domain.roadmap import (
    LearningResource,
    RoadmapRequest,
    SkillGap,
    build_roadmap,
)
from backend.app.domain.roles import load_role_template


@dataclass(frozen=True)
class AttemptOutput:
    nodes: list[dict[str, object]]
    edges: list[dict[str, object]]
    scorecard: dict[str, object]
    roadmap_items: list[dict[str, object]]
    progress_metric: dict[str, object] | None


def _mean(values: list[float]) -> float:
    return float(fmean(values)) if values else 0.0


def _node(
    *,
    node_id: str,
    node_type: str,
    attempt_id: UUID,
    source: str,
    confidence: float,
    visibility: str = "student",
    text: str | None = None,
    attributes: dict[str, object] | None = None,
) -> GraphNode:
    return GraphNode(
        id=node_id,
        type=node_type,
        attempt_id=attempt_id,
        source=source,
        confidence=confidence,
        visibility=visibility,
        normalized_text=text,
        attributes=attributes or {},
        created_at=datetime.now(timezone.utc),
    )


def _edge(
    *,
    edge_id: str,
    edge_type: str,
    attempt_id: UUID,
    source_node_id: str,
    target_node_id: str,
    confidence: float,
    source: str = "attempt-report-v1",
) -> GraphEdge:
    return GraphEdge(
        id=edge_id,
        type=edge_type,
        attempt_id=attempt_id,
        source=source,
        confidence=confidence,
        visibility="student",
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        created_at=datetime.now(timezone.utc),
    )


def _metric(value: float, node_ids: list[str]) -> MetricEvidence:
    return MetricEvidence(value=max(0.0, min(1.0, value)), evidence_node_ids=node_ids)


def _not_applicable() -> MetricEvidence:
    return MetricEvidence(value=None, applicable=False)


def interview_ready_for_report(
    *,
    role_id: str,
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
) -> tuple[bool, str]:
    role = load_role_template(role_id)
    answered_question_ids = {str(answer["question_id"]) for answer in answers}
    analysis_answer_ids = {str(item["answer_id"]) for item in analyses}
    answer_by_question = {
        str(answer["question_id"]): answer
        for answer in answers
        if str(answer["id"]) in analysis_answer_ids
    }
    core_by_competency = {
        str(question["competency_id"]): question
        for question in questions
        if not question["is_follow_up"]
        and str(question["id"]) in answered_question_ids
    }
    if set(core_by_competency) != {item.competency_id for item in role.competencies}:
        return False, "core_questions_remaining"

    analysis_by_answer = {str(item["answer_id"]): item for item in analyses}
    followup_competencies = {
        str(question["competency_id"])
        for question in questions
        if question["is_follow_up"] and str(question["id"]) in answer_by_question
    }
    for competency_id, question in core_by_competency.items():
        answer = answer_by_question.get(str(question["id"]))
        if answer is None:
            return False, "answer_processing_remaining"
        raw = analysis_by_answer.get(str(answer["id"]))
        if raw is None:
            return False, "answer_processing_remaining"
        evaluation = TechnicalAnswerEvaluation.model_validate(raw["technical_evaluation"])
        needs_followup = (
            evaluation.competency_coverage
            < FOLLOW_UP_THRESHOLD["competency_coverage"]
            or evaluation.competency_rubric_score
            < FOLLOW_UP_THRESHOLD["rubric_match"]
            or evaluation.answer_completeness
            < FOLLOW_UP_THRESHOLD["answer_completeness"]
            or evaluation.evidence_confidence
            < FOLLOW_UP_THRESHOLD["evidence_confidence"]
            or evaluation.high_confidence_resume_contradiction
        )
        if needs_followup and competency_id not in followup_competencies:
            return False, "follow_up_required"
    return True, "complete"


def build_attempt_output(
    *,
    attempt: dict[str, Any],
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
    analyses: list[dict[str, Any]],
    resume_claims: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    parent_scorecard: dict[str, Any] | None = None,
) -> AttemptOutput:
    attempt_uuid = UUID(str(attempt["id"]))
    role = load_role_template(str(attempt["role_id"]))
    question_by_id = {str(item["id"]): item for item in questions}
    analysis_by_answer = {str(item["answer_id"]): item for item in analyses}

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    attempt_node = f"attempt:{attempt_uuid}"
    role_node = f"role:{role.role_id}:{str(attempt_uuid)[:8]}"
    student_node = f"student:{str(attempt['user_id'])}"
    nodes.extend(
        [
            _node(
                node_id=student_node,
                node_type="Student",
                attempt_id=attempt_uuid,
                source="supabase-auth",
                confidence=1.0,
                visibility="private",
            ),
            _node(
                node_id=attempt_node,
                node_type="Attempt",
                attempt_id=attempt_uuid,
                source="attempt-record",
                confidence=1.0,
            ),
            _node(
                node_id=role_node,
                node_type="TargetRole",
                attempt_id=attempt_uuid,
                source=role.template_version,
                confidence=1.0,
                text=role.display_name,
                attributes={"role_id": role.role_id},
            ),
        ]
    )
    competency_node_ids: dict[str, str] = {}
    for competency in role.competencies:
        node_id = f"competency:{competency.competency_id}:{str(attempt_uuid)[:8]}"
        competency_node_ids[competency.competency_id] = node_id
        nodes.append(
            _node(
                node_id=node_id,
                node_type="Competency",
                attempt_id=attempt_uuid,
                source=role.template_version,
                confidence=1.0,
                text=competency.name,
                attributes={"competency_id": competency.competency_id},
            )
        )
        edges.append(
            _edge(
                edge_id=f"edge:requires:{competency.competency_id}:{str(attempt_uuid)[:8]}",
                edge_type="requires",
                attempt_id=attempt_uuid,
                source_node_id=role_node,
                target_node_id=node_id,
                confidence=1.0,
            )
        )

    for claim in resume_claims:
        claim_id = f"resume:{str(claim['id'])}"[:120]
        nodes.append(
            _node(
                node_id=claim_id,
                node_type="ResumeClaim",
                attempt_id=attempt_uuid,
                source="resume-extractor",
                confidence=float(claim["confidence"]),
                text=str(claim["normalized_text"]),
                attributes={"resume_claim_id": str(claim["id"])},
            )
        )
        edges.append(
            _edge(
                edge_id=f"edge:claim:{str(claim['id'])}"[:120],
                edge_type="claims",
                attempt_id=attempt_uuid,
                source_node_id=student_node,
                target_node_id=claim_id,
                confidence=float(claim["confidence"]),
            )
        )

    evaluations: dict[str, list[TechnicalAnswerEvaluation]] = defaultdict(list)
    evidence_ids: dict[str, list[str]] = defaultdict(list)
    delivery_by_answer: list[dict[str, Any]] = []
    base_signals: list[float] = []
    all_evaluations: list[TechnicalAnswerEvaluation] = []

    for answer in answers:
        raw_analysis = analysis_by_answer.get(str(answer["id"]))
        if raw_analysis is None:
            continue
        question = question_by_id[str(answer["question_id"])]
        evaluation = TechnicalAnswerEvaluation.model_validate(
            raw_analysis["technical_evaluation"]
        )
        all_evaluations.append(evaluation)
        evaluations[evaluation.competency_id].append(evaluation)
        delivery_by_answer.append(raw_analysis["delivery_metrics"])
        base_signals.append(float(raw_analysis["base_multimodal_interview_signal"]))
        short = str(answer["id"])[:8]
        question_node = f"question:{short}"
        answer_node = f"answer:{short}"
        transcript_node = f"transcript:{short}"
        audio_node = f"audio:{short}"
        visual_node = f"visual:{short}"
        prediction_node = f"prediction:{short}"
        claim_node = f"evidence:{short}"
        evidence_ids[evaluation.competency_id].append(claim_node)
        transcript_text = str(raw_analysis["transcript_text"])
        nodes.extend(
            [
                _node(
                    node_id=question_node,
                    node_type="Question",
                    attempt_id=attempt_uuid,
                    source=str(question.get("question_package_version") or "role-template"),
                    confidence=1.0,
                    text=str(question["prompt_snapshot"]),
                    attributes={
                        "question": {
                            "id": str(question["id"]),
                            "prompt_snapshot": question["prompt_snapshot"],
                        },
                        "competency_id": evaluation.competency_id,
                    },
                ),
                _node(
                    node_id=answer_node,
                    node_type="AnswerSegment",
                    attempt_id=attempt_uuid,
                    source="student-video",
                    confidence=float(raw_analysis["signal_quality"]),
                ),
                _node(
                    node_id=transcript_node,
                    node_type="TranscriptSpan",
                    attempt_id=attempt_uuid,
                    source="whisper-small.en",
                    confidence=float(raw_analysis["transcript_confidence"]),
                    text=transcript_text[:10_000],
                    attributes={
                        "transcript_span": {"text": transcript_text[:2_000]},
                        "competency_id": evaluation.competency_id,
                    },
                ),
                _node(
                    node_id=audio_node,
                    node_type="AudioEvidence",
                    attempt_id=attempt_uuid,
                    source="opensmile-egemapsv02",
                    confidence=float(raw_analysis["signal_quality"]),
                    attributes=raw_analysis["delivery_metrics"],
                ),
                _node(
                    node_id=visual_node,
                    node_type="VisualEvidence",
                    attempt_id=attempt_uuid,
                    source="openface-2.2.0",
                    confidence=float(raw_analysis["signal_quality"]),
                    attributes=raw_analysis["delivery_metrics"],
                ),
                _node(
                    node_id=prediction_node,
                    node_type="ModelPrediction",
                    attempt_id=attempt_uuid,
                    source=str(raw_analysis["model_run_name"]),
                    confidence=float(raw_analysis["signal_quality"]),
                    attributes={
                        "base_multimodal_interview_signal": raw_analysis[
                            "base_multimodal_interview_signal"
                        ],
                        "model_reference": raw_analysis["model_checkpoint_sha256"],
                        "signal_quality": raw_analysis["signal_quality"],
                    },
                ),
                _node(
                    node_id=claim_node,
                    node_type="EvidenceClaim",
                    attempt_id=attempt_uuid,
                    source=str(raw_analysis["evaluator_model_id"]),
                    confidence=evaluation.evidence_confidence,
                    text=(
                        f"Rubric evidence for {evaluation.competency_id}: "
                        f"{evaluation.competency_rubric_score:.2f}"
                    ),
                    attributes={
                        "competency_id": evaluation.competency_id,
                        "criterion_evidence": [
                            item.model_dump(mode="json")
                            for item in evaluation.criterion_evidence
                        ],
                        "missing_concepts": evaluation.missing_concepts,
                    },
                ),
            ]
        )
        for relation, target in (
            ("tests", competency_node_ids[evaluation.competency_id]),
            ("answered_by", answer_node),
        ):
            edges.append(
                _edge(
                    edge_id=f"edge:{relation}:{short}",
                    edge_type=relation,
                    attempt_id=attempt_uuid,
                    source_node_id=question_node,
                    target_node_id=target,
                    confidence=1.0,
                )
            )
        for relation, target in (
            ("transcribed_as", transcript_node),
            ("has_audio_evidence", audio_node),
            ("has_visual_evidence", visual_node),
            ("predicted_by", prediction_node),
        ):
            edges.append(
                _edge(
                    edge_id=f"edge:{relation}:{short}",
                    edge_type=relation,
                    attempt_id=attempt_uuid,
                    source_node_id=answer_node,
                    target_node_id=target,
                    confidence=float(raw_analysis["signal_quality"]),
                )
            )
        edges.append(
            _edge(
                edge_id=f"edge:supports:{short}",
                edge_type="supports",
                attempt_id=attempt_uuid,
                source_node_id=claim_node,
                target_node_id=competency_node_ids[evaluation.competency_id],
                confidence=evaluation.evidence_confidence,
            )
        )

    graph = EvidenceGraph(attempt_id=attempt_uuid, nodes=nodes, edges=edges)
    competency_scores = {
        competency.competency_id: _metric(
            _mean(
                [
                    evaluation.competency_rubric_score
                    for evaluation in evaluations[competency.competency_id]
                ]
            ),
            evidence_ids[competency.competency_id],
        )
        for competency in role.competencies
    }
    competency_coverage = {
        competency.competency_id: _metric(
            _mean(
                [
                    evaluation.competency_coverage
                    for evaluation in evaluations[competency.competency_id]
                ]
            ),
            evidence_ids[competency.competency_id],
        )
        for competency in role.competencies
    }
    all_evidence_ids = [item for items in evidence_ids.values() for item in items]
    followup_values = [
        item.follow_up_responsiveness
        for item in all_evaluations
        if item.follow_up_responsiveness is not None
    ]
    delivery_ids = [
        node.id for node in nodes if node.type in {"AudioEvidence", "VisualEvidence"}
    ]
    transcript_ids = [node.id for node in nodes if node.type == "TranscriptSpan"]
    scorecard = calculate_scorecard(
        ScorecardRequest(
            graph=graph,
            role_id=role.role_id,
            role_template_version=role.template_version,
            competency_weights={
                str(key): float(value)
                for key, value in attempt["competency_weights"].items()
            },
            evidence=ScorecardEvidence(
                competency_rubric_scores=competency_scores,
                competency_coverage=competency_coverage,
                answer_depth_and_correctness=_metric(
                    _mean([item.answer_depth_and_correctness for item in all_evaluations]),
                    all_evidence_ids,
                ),
                technical_follow_up_quality=(
                    _metric(_mean([float(item) for item in followup_values]), all_evidence_ids)
                    if followup_values
                    else _not_applicable()
                ),
                resume_project_consistency=_metric(
                    _mean([item.resume_project_consistency for item in all_evaluations]),
                    all_evidence_ids,
                ),
                answer_relevance=_metric(
                    _mean([item.answer_relevance for item in all_evaluations]),
                    all_evidence_ids,
                ),
                answer_structure=_metric(
                    _mean([item.answer_structure for item in all_evaluations]),
                    all_evidence_ids,
                ),
                answer_completeness=_metric(
                    _mean([item.answer_completeness for item in all_evaluations]),
                    all_evidence_ids,
                ),
                pace_and_filler_quality=_metric(
                    _mean(
                        [
                            float(item["pace_and_filler_quality"])
                            for item in delivery_by_answer
                        ]
                    ),
                    delivery_ids,
                ),
                transcript_confidence=_metric(
                    _mean(
                        [float(item["transcript_confidence"]) for item in delivery_by_answer]
                    ),
                    transcript_ids,
                ),
                follow_up_responsiveness=(
                    _metric(_mean([float(item) for item in followup_values]), all_evidence_ids)
                    if followup_values
                    else _not_applicable()
                ),
                professionalism_rubric=_metric(
                    _mean([item.professionalism_rubric for item in all_evaluations]),
                    all_evidence_ids,
                ),
                evidence_confidence=_metric(
                    _mean([item.evidence_confidence for item in all_evaluations]),
                    all_evidence_ids,
                ),
                signal_quality=_metric(
                    _mean([float(item["signal_quality"]) for item in delivery_by_answer]),
                    delivery_ids,
                ),
            ),
        )
    )

    gaps: list[SkillGap] = []
    for item in scorecard.competency_scores:
        if item.score >= 0.70 or item.coverage < 0.70:
            continue
        gap_id = f"gap:{item.competency_id}:{str(attempt_uuid)[:8]}"
        gap_node = _node(
            node_id=gap_id,
            node_type="SkillGap",
            attempt_id=attempt_uuid,
            source=scorecard.formula_version,
            confidence=scorecard.overall_evidence_confidence,
            text=f"Evidence-backed practice gap in {item.competency_id}",
            attributes={
                "competency_id": item.competency_id,
                "current_score": item.score,
                "target_score": 0.70,
                "severity": round(0.70 - item.score, 6),
                "rationale": "Rubric score is below the reviewed practice target.",
            },
        )
        nodes.append(gap_node)
        edges.append(
            _edge(
                edge_id=f"edge:gap:{item.competency_id}:{str(attempt_uuid)[:8]}",
                edge_type="indicates_gap",
                attempt_id=attempt_uuid,
                source_node_id=competency_node_ids[item.competency_id],
                target_node_id=gap_id,
                confidence=scorecard.overall_evidence_confidence,
            )
        )
        gaps.append(
            SkillGap(
                skill_gap_node_id=gap_id,
                competency_id=item.competency_id,
                current_score=item.score,
                target_score=0.70,
                severity=round(0.70 - item.score, 6),
                evidence_node_ids=evidence_ids[item.competency_id],
            )
        )

    approved_resources = [
        LearningResource(
            resource_id=str(item["id"]),
            title=str(item["title"]),
            canonical_url=str(item["canonical_url"]),
            source_organization=str(item["source_organization"]),
            competency_ids=[str(value) for value in item["competency_ids"]],
            difficulty=str(item["difficulty"]),
            estimated_minutes=int(item["estimated_minutes"]),
            description=str(item["description"]),
            reviewer_status=str(item["reviewer_status"]),
            reviewer_id=str(item["reviewer_id"]) if item.get("reviewer_id") else None,
        )
        for item in resources
    ]
    roadmap_result = (
        build_roadmap(
            RoadmapRequest(
                role_id=role.role_id,
                gaps=gaps,
                resources=approved_resources,
            )
        )
        if gaps
        else None
    )
    roadmap_items = [
        {
            "attempt_id": str(attempt_uuid),
            "skill_gap_node_id": item.skill_gap_node_id,
            "resource_id": item.resource_id,
            "priority": item.priority,
            "rationale": item.rationale,
        }
        for item in (roadmap_result.items if roadmap_result else [])
    ]
    result_payload = scorecard.model_dump(mode="json")
    result_payload["competency_scores"] = [
        {
            **item.model_dump(mode="json"),
            "evidence_node_ids": evidence_ids[item.competency_id],
            "insufficiency_reasons": (
                [] if item.sufficient_evidence else ["Coverage below 0.70"]
            ),
        }
        for item in scorecard.competency_scores
    ]
    scorecard_row: dict[str, object] = {
        "attempt_id": str(attempt_uuid),
        "formula_version": scorecard.formula_version,
        "model_run_name": str(analyses[0]["model_run_name"]),
        "model_checkpoint_sha256": str(analyses[0]["model_checkpoint_sha256"]),
        "competency_scores": result_payload["competency_scores"],
        "technical_readiness": scorecard.technical_readiness,
        "communication_clarity": scorecard.communication_clarity,
        "interview_response_quality": scorecard.interview_response_quality,
        "placement_readiness": scorecard.placement_readiness,
        "overall_evidence_confidence": scorecard.overall_evidence_confidence,
        "sufficient_evidence": scorecard.sufficient_evidence,
        "insufficiency_reasons": scorecard.insufficiency_reasons,
    }
    progress_metric = None
    if attempt.get("parent_attempt_id") and parent_scorecard:
        parent_scores = {
            str(item["competency_id"]): float(item["score"])
            for item in parent_scorecard.get("competency_scores", [])
        }
        progress_metric = {
            "user_id": str(attempt["user_id"]),
            "earlier_attempt_id": str(attempt["parent_attempt_id"]),
            "later_attempt_id": str(attempt_uuid),
            "metric_version": "comparable-evidence-progress-v1",
            "score_deltas": {
                item.competency_id: round(
                    item.score - parent_scores.get(item.competency_id, item.score),
                    6,
                )
                for item in scorecard.competency_scores
            },
        }
    return AttemptOutput(
        nodes=[
            {
                "id": item.id,
                "attempt_id": str(item.attempt_id),
                "node_type": item.type,
                "source": item.source,
                "confidence": item.confidence,
                "visibility": item.visibility,
                "normalized_text": item.normalized_text,
                "raw_reference": item.raw_reference,
                "attributes": item.attributes,
            }
            for item in nodes
        ],
        edges=[
            {
                "id": item.id,
                "attempt_id": str(item.attempt_id),
                "edge_type": item.type,
                "source_node_id": item.source_node_id,
                "target_node_id": item.target_node_id,
                "source": item.source,
                "confidence": item.confidence,
                "visibility": item.visibility,
                "normalized_text": item.normalized_text,
                "raw_reference": item.raw_reference,
                "attributes": item.attributes,
            }
            for item in edges
        ],
        scorecard=scorecard_row,
        roadmap_items=roadmap_items,
        progress_metric=progress_metric,
    )
