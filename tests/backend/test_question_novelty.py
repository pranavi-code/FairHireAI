from backend.app.services.question_novelty import (
    assess_question_novelty,
    compact_history_themes,
)

MONTHLY_SALES = "Which chart would you use to show monthly sales trends?"


def test_exact_duplicate_is_rejected() -> None:
    result = assess_question_novelty(MONTHLY_SALES, [MONTHLY_SALES])

    assert result.is_duplicate
    assert result.reason == "exact_duplicate"


def test_near_paraphrase_is_rejected() -> None:
    result = assess_question_novelty(
        "What visualization should be used for month-wise sales trends?",
        ["Which chart is best for monthly sales trends?"],
    )

    assert result.is_duplicate
    assert result.reason in {
        "near_verbatim",
        "near_paraphrase",
        "same_scenario_and_task",
        "borderline_paraphrase",
    }


def test_same_competency_materially_different_scenario_is_allowed() -> None:
    result = assess_question_novelty(
        (
            "A placement coordinator wants to compare interview participation, improvement, "
            "and selection rate across departments. Design the dashboard."
        ),
        [MONTHLY_SALES],
    )

    assert not result.is_duplicate


def test_controlled_relaxation_never_allows_exact_or_near_verbatim_duplicates() -> None:
    assert assess_question_novelty(
        MONTHLY_SALES,
        [MONTHLY_SALES],
        controlled_relaxation=True,
    ).is_duplicate
    assert assess_question_novelty(
        "What visualization should be used for month-wise sales trends?",
        ["Which chart is best for monthly sales trends?"],
        controlled_relaxation=True,
    ).is_duplicate


def test_generic_interview_phrases_do_not_create_false_duplicates() -> None:
    result = assess_question_novelty(
        "Explain your approach to diagnosing inconsistent patient wait-time categories.",
        ["Explain your approach to selecting a chart for monthly sales."],
    )

    assert not result.is_duplicate


def test_history_is_compacted_into_nonduplicated_scenario_structure_concepts() -> None:
    themes = compact_history_themes([MONTHLY_SALES, MONTHLY_SALES])

    assert len(themes) == 1
    assert themes[0]["scenarios"] == ["commerce"]
    assert "visualization" in themes[0]["concepts"]
