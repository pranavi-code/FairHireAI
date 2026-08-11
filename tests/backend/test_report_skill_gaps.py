from backend.app.repositories.supabase import SupabaseAttemptRepository


def test_skill_gap_evidence_is_exposed_to_the_report_contract() -> None:
    view = SupabaseAttemptRepository._evidence_node_view(
        {
            "id": "gap_api_design",
            "node_type": "SkillGap",
            "normalized_text": "API design needs stronger evidence",
            "confidence": 0.91,
            "attributes": {
                "competency_id": "api_design",
                "current_score": 0.48,
                "target_score": 0.75,
                "severity": 0.27,
                "rationale": "The answer did not cover versioning or error contracts.",
            },
        }
    )

    assert view.kind == "SkillGap"
    assert view.competency_id == "api_design"
    assert view.skill_gap is not None
    assert view.skill_gap.current_score == 0.48
    assert view.skill_gap.target_score == 0.75
    assert view.skill_gap.severity == 0.27
    assert "versioning" in str(view.skill_gap.rationale)


def test_non_gap_evidence_does_not_receive_gap_details() -> None:
    view = SupabaseAttemptRepository._evidence_node_view(
        {
            "id": "transcript_1",
            "node_type": "TranscriptSpan",
            "normalized_text": "A transcript span",
            "confidence": 0.88,
            "attributes": {"competency_id": "api_design"},
        }
    )

    assert view.skill_gap is None
