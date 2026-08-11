"""Constrained Gemini evaluator for frozen interview questions and transcripts."""

from __future__ import annotations

import json
from typing import Any

from backend.app.domain.answer_evaluation import TechnicalAnswerEvaluation
from backend.app.providers.gemini import GeminiClient

EVALUATOR_PROMPT_VERSION = "technical-evidence-gemini-v1"


def technical_answer_response_schema(*, is_follow_up: bool) -> dict[str, object]:
    """Return the supported Gemini JSON-Schema subset; Pydantic revalidates it."""

    score: dict[str, object] = {"type": "number", "minimum": 0, "maximum": 1}
    criterion = {
        "type": "object",
        "properties": {
            "criterion": {"type": "string"},
            "score": score,
            "rationale": {"type": "string"},
            "citation_text": {"type": "string"},
            "citation_start_seconds": {"type": "number", "minimum": 0},
            "citation_end_seconds": {"type": "number", "minimum": 0},
        },
        "required": ["criterion", "score", "rationale"],
        "additionalProperties": False,
    }
    score_fields = (
        "competency_rubric_score",
        "competency_coverage",
        "answer_depth_and_correctness",
        "answer_relevance",
        "answer_structure",
        "answer_completeness",
        "resume_project_consistency",
        "professionalism_rubric",
        "evidence_confidence",
    )
    properties: dict[str, object] = {
        "competency_id": {"type": "string"},
        **{field: score for field in score_fields},
        "criterion_evidence": {
            "type": "array",
            "items": criterion,
            "minItems": 1,
            "maxItems": 20,
        },
        "missing_concepts": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "weakest_criterion": {"type": "string"},
        "high_confidence_resume_contradiction": {"type": "boolean"},
        "safety_note": {"type": "string"},
    }
    required = [
        "competency_id",
        *score_fields,
        "criterion_evidence",
        "safety_note",
    ]
    if is_follow_up:
        properties["follow_up_responsiveness"] = score
        required.append("follow_up_responsiveness")
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


class AnswerEvaluationService:
    def __init__(self, client: GeminiClient) -> None:
        self._client = client

    def evaluate(
        self,
        *,
        competency_id: str,
        prompt_snapshot: str,
        expected_concepts: list[str],
        rubric: dict[str, str],
        source_mapping: dict[str, list[str]],
        transcript: dict[str, Any],
        resume_claims: list[dict[str, Any]],
        is_follow_up: bool,
    ) -> TechnicalAnswerEvaluation:
        minimized_claims = [
            {
                "id": claim.get("id"),
                "type": claim.get("claim_type"),
                "text": claim.get("normalized_text"),
                "confidence": claim.get("confidence"),
            }
            for claim in resume_claims[:30]
        ]
        payload = {
            "competency_id": competency_id,
            "question": prompt_snapshot,
            "expected_concepts": expected_concepts,
            "frozen_rubric": rubric,
            "reviewed_source_to_concept_mapping": source_mapping,
            "is_follow_up": is_follow_up,
            "transcript": {
                "text": transcript.get("text"),
                "segments": transcript.get("segments"),
                "average_word_confidence": transcript.get("average_word_confidence"),
            },
            "minimized_resume_claims": minimized_claims,
            "rules": [
                "Use only the transcript, frozen rubric, expected concepts, and supplied claims.",
                "Cite exact transcript spans for positive technical evidence.",
                "Do not treat delivery style as technical knowledge.",
                "Do not infer emotion, personality, confidence, nervousness, or protected traits.",
                "If evidence is missing or unclear, lower confidence; never invent it.",
                "Resume consistency is neutral (0.5) when no relevant claim exists.",
                "Follow-up responsiveness must be null for a core question.",
                "Professionalism means task relevance and respectful language only.",
                "Return values in the inclusive range 0 to 1.",
            ],
        }
        raw_result = self._client.generate_json(
            system_instruction=(
                "You are a constrained evidence extractor for student practice "
                "interviews. You do not make hiring decisions. Return only the "
                "requested JSON and ground every judgment in supplied evidence."
            ),
            prompt=json.dumps(payload, ensure_ascii=False),
            response_schema=technical_answer_response_schema(is_follow_up=is_follow_up),
        )
        raw_criteria = raw_result.get("criterion_evidence")
        if isinstance(raw_criteria, list):
            normalized_criteria: list[dict[str, object]] = []
            for raw_criterion in raw_criteria:
                if not isinstance(raw_criterion, dict):
                    continue
                normalized: dict[str, object] = {
                    "criterion": raw_criterion.get("criterion"),
                    "score": raw_criterion.get("score"),
                    "rationale": raw_criterion.get("rationale"),
                    "citations": (
                        raw_criterion["citations"]
                        if isinstance(raw_criterion.get("citations"), list)
                        else []
                    ),
                }
                citation_text = raw_criterion.get("citation_text")
                citation_start = raw_criterion.get("citation_start_seconds")
                citation_end = raw_criterion.get("citation_end_seconds")
                if (
                    isinstance(citation_text, str)
                    and citation_text.strip()
                    and isinstance(citation_start, (int, float))
                    and isinstance(citation_end, (int, float))
                    and citation_end > citation_start >= 0
                ):
                    normalized["citations"] = [
                        {
                            "text": citation_text,
                            "start_seconds": citation_start,
                            "end_seconds": citation_end,
                        }
                    ]
                normalized_criteria.append(normalized)
            raw_result["criterion_evidence"] = normalized_criteria
        safety_note = raw_result.get("safety_note")
        if not isinstance(safety_note, str) or len(safety_note.strip()) < 20:
            raw_result["safety_note"] = (
                "Evidence-only student practice assessment; no hiring decision was made."
            )
        result = TechnicalAnswerEvaluation.model_validate(raw_result)
        if result.competency_id != competency_id:
            raise ValueError("Evaluator returned the wrong competency")
        if is_follow_up and result.follow_up_responsiveness is None:
            raise ValueError("Follow-up evaluation omitted responsiveness")
        if not is_follow_up and result.follow_up_responsiveness is not None:
            raise ValueError("Core-answer evaluation included follow-up responsiveness")
        return result
