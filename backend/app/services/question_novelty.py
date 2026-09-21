"""Deterministic, explainable anti-repetition checks for interview questions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

GENERIC_WORDS = {
    "a",
    "an",
    "and",
    "approach",
    "be",
    "best",
    "explain",
    "for",
    "how",
    "in",
    "is",
    "it",
    "of",
    "or",
    "should",
    "the",
    "to",
    "use",
    "used",
    "what",
    "which",
    "would",
    "you",
    "your",
}

TOKEN_CANONICALIZATION = {
    "analyse": "analyze",
    "analyzing": "analyze",
    "chart": "visualization",
    "charts": "visualization",
    "graph": "visualization",
    "graphs": "visualization",
    "month": "monthly",
    "months": "monthly",
    "plot": "visualization",
    "plots": "visualization",
    "revenue": "sales",
    "revenues": "sales",
    "sale": "sales",
    "trend": "trends",
    "visualisation": "visualization",
    "visualisations": "visualization",
    "visualizations": "visualization",
}

SCENARIO_TAXONOMY = {
    "education": {"campus", "college", "course", "education", "student", "university"},
    "healthcare": {"clinic", "healthcare", "hospital", "patient"},
    "hiring": {"candidate", "department", "hiring", "interview", "placement", "selection"},
    "logistics": {"carrier", "delivery", "fleet", "logistics", "region", "shipment"},
    "commerce": {"cart", "customer", "ecommerce", "order", "product", "sales"},
    "operations": {"incident", "kpi", "operations", "performance", "service"},
}

STRUCTURE_TAXONOMY = {
    "selection": {"best", "choose", "select", "which"},
    "design": {"build", "dashboard", "design", "propose"},
    "diagnosis": {"debug", "diagnose", "misleading", "problem", "wrong"},
    "interpretation": {"conclude", "interpret", "meaning", "read"},
    "comparison": {"compare", "difference", "versus"},
    "communication": {"communicate", "explain", "present", "stakeholder"},
    "verification": {"check", "test", "validate", "verify"},
}


@dataclass(frozen=True)
class QuestionTheme:
    scenarios: tuple[str, ...]
    structures: tuple[str, ...]
    concepts: tuple[str, ...]

    def as_prompt_context(self) -> dict[str, list[str]]:
        return {
            "scenarios": list(self.scenarios),
            "structures": list(self.structures),
            "concepts": list(self.concepts[:10]),
        }


@dataclass(frozen=True)
class NoveltyDecision:
    is_duplicate: bool
    reason: str | None = None
    matched_index: int | None = None
    sequence_similarity: float = 0.0
    concept_similarity: float = 0.0
    scenario_overlap: bool = False
    structure_overlap: bool = False


def normalize_question(text: str) -> str:
    normalized = re.sub(r"month[\s-]+wise", "monthly", text.casefold())
    tokens = re.findall(r"[a-z0-9]+", normalized)
    return " ".join(TOKEN_CANONICALIZATION.get(token, token) for token in tokens)


def question_theme(text: str) -> QuestionTheme:
    normalized_tokens = normalize_question(text).split()
    token_set = set(normalized_tokens)
    scenarios = tuple(
        name for name, markers in SCENARIO_TAXONOMY.items() if token_set & markers
    )
    structures = tuple(
        name for name, markers in STRUCTURE_TAXONOMY.items() if token_set & markers
    )
    concepts = tuple(
        sorted(token for token in token_set if token not in GENERIC_WORDS and len(token) > 2)
    )
    return QuestionTheme(scenarios=scenarios, structures=structures, concepts=concepts)


def compact_history_themes(prompts: list[str], *, maximum: int = 12) -> list[dict[str, list[str]]]:
    summaries: list[dict[str, list[str]]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = set()
    for prompt in reversed(prompts):
        theme = question_theme(prompt)
        key = (theme.scenarios, theme.structures, theme.concepts[:10])
        if key in seen:
            continue
        seen.add(key)
        summaries.append(theme.as_prompt_context())
        if len(summaries) >= maximum:
            break
    return list(reversed(summaries))


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def assess_question_novelty(
    candidate: str,
    history: list[str],
    *,
    controlled_relaxation: bool = False,
) -> NoveltyDecision:
    """Reject wording/scenario paraphrases without penalizing competency vocabulary.

    Controlled relaxation affects only a borderline lexical rule. Exact matches,
    near-verbatim wording, and same-scenario/same-task paraphrases remain blocked.
    """

    normalized_candidate = normalize_question(candidate)
    if not normalized_candidate:
        return NoveltyDecision(is_duplicate=True, reason="empty_candidate")
    candidate_theme = question_theme(candidate)
    candidate_concepts = set(candidate_theme.concepts)
    best = NoveltyDecision(is_duplicate=False)
    for index, historical in enumerate(history):
        normalized_history = normalize_question(historical)
        if not normalized_history:
            continue
        sequence = SequenceMatcher(None, normalized_candidate, normalized_history).ratio()
        historical_theme = question_theme(historical)
        concept = _jaccard(candidate_concepts, set(historical_theme.concepts))
        scenario_overlap = bool(
            set(candidate_theme.scenarios) & set(historical_theme.scenarios)
        )
        structure_overlap = bool(
            set(candidate_theme.structures) & set(historical_theme.structures)
        )
        if normalized_candidate == normalized_history:
            return NoveltyDecision(
                True,
                "exact_duplicate",
                index,
                1.0,
                concept,
                scenario_overlap,
                structure_overlap,
            )
        if sequence >= 0.92:
            return NoveltyDecision(
                True,
                "near_verbatim",
                index,
                sequence,
                concept,
                scenario_overlap,
                structure_overlap,
            )
        # A high concept match is still a near paraphrase when the wording is
        # strongly similar, even if shallow interrogative markers classify the
        # two prompts under different structures (for example, "which chart"
        # versus "what visualization should be used"). This protection is not
        # relaxed by the final recovery stage.
        if sequence >= 0.82 and concept >= 0.85 and (
            scenario_overlap
            or (not candidate_theme.scenarios and not historical_theme.scenarios)
        ):
            return NoveltyDecision(
                True,
                "near_paraphrase",
                index,
                sequence,
                concept,
                scenario_overlap,
                structure_overlap,
            )
        if concept >= 0.72 and structure_overlap and (
            scenario_overlap
            or (not candidate_theme.scenarios and not historical_theme.scenarios)
        ):
            return NoveltyDecision(
                True,
                "same_scenario_and_task",
                index,
                sequence,
                concept,
                scenario_overlap,
                structure_overlap,
            )
        if not controlled_relaxation and sequence >= 0.78 and concept >= 0.55:
            return NoveltyDecision(
                True,
                "borderline_paraphrase",
                index,
                sequence,
                concept,
                scenario_overlap,
                structure_overlap,
            )
        if sequence + concept > best.sequence_similarity + best.concept_similarity:
            best = NoveltyDecision(
                False,
                None,
                index,
                sequence,
                concept,
                scenario_overlap,
                structure_overlap,
            )
    return best
