"""Traceable resume evidence contracts; extraction is performed by a real parser."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.domain.documents import ExtractedDocument, iter_nonempty_lines, page_for_offset

ResumeClaimType = Literal[
    "skill",
    "project",
    "internship",
    "certification",
    "achievement",
]


class SourceSpan(BaseModel):
    page: int | None = Field(default=None, ge=1)
    start_character: int = Field(ge=0)
    end_character: int = Field(gt=0)
    source_text: str = Field(min_length=1, max_length=5_000)

    @model_validator(mode="after")
    def validate_offsets(self) -> SourceSpan:
        if self.end_character <= self.start_character:
            raise ValueError("end_character must be greater than start_character")
        return self


class ResumeClaim(BaseModel):
    claim_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,79}$")
    claim_type: ResumeClaimType
    normalized_text: str = Field(min_length=2, max_length=1_000)
    source: SourceSpan
    confidence: float = Field(ge=0.0, le=1.0)
    normalized_skills: list[str] = Field(default_factory=list, max_length=30)


class ResumeEvidence(BaseModel):
    schema_version: Literal["resume-evidence-v1"] = "resume-evidence-v1"
    document_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    extractor_name: str = Field(min_length=2, max_length=100)
    extractor_version: str = Field(min_length=1, max_length=50)
    claims: list[ResumeClaim] = Field(max_length=300)

    @model_validator(mode="after")
    def validate_unique_claims(self) -> ResumeEvidence:
        identifiers = [claim.claim_id for claim in self.claims]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Resume claim identifiers must be unique")
        return self


class ResumeEvidenceValidation(BaseModel):
    valid: Literal[True] = True
    schema_version: Literal["resume-evidence-v1"]
    claim_count: int
    counts_by_type: dict[ResumeClaimType, int]
    low_confidence_claim_ids: list[str]


def summarize_resume_evidence(
    evidence: ResumeEvidence,
    *,
    low_confidence_threshold: float = 0.60,
) -> ResumeEvidenceValidation:
    counts = Counter(claim.claim_type for claim in evidence.claims)
    return ResumeEvidenceValidation(
        schema_version=evidence.schema_version,
        claim_count=len(evidence.claims),
        counts_by_type={
            claim_type: counts[claim_type]
            for claim_type in (
                "skill",
                "project",
                "internship",
                "certification",
                "achievement",
            )
        },
        low_confidence_claim_ids=[
            claim.claim_id
            for claim in evidence.claims
            if claim.confidence < low_confidence_threshold
        ],
    )


SECTION_ALIASES: dict[str, ResumeClaimType] = {
    "skills": "skill",
    "technical skills": "skill",
    "technologies": "skill",
    "projects": "project",
    "project experience": "project",
    "internships": "internship",
    "internship experience": "internship",
    "work experience": "internship",
    "experience": "internship",
    "certifications": "certification",
    "certificates": "certification",
    "achievements": "achievement",
    "awards": "achievement",
}
HEADING_PATTERN = re.compile(
    r"^(?P<header>[A-Za-z][A-Za-z /&-]{1,40}?)(?:\s*:\s*(?P<inline>.+))?$"
)
BULLET_PATTERN = re.compile(r"^[\s\u2022\u25cf\u25e6\u25aa*-]+")
SKILL_SEPARATOR = re.compile(r"[,;|]")


def _normalise_claim_text(text: str) -> str:
    return re.sub(r"\s+", " ", BULLET_PATTERN.sub("", text)).strip(" .;:-")


def _claim_id(document_sha256: str, claim_type: str, start: int, end: int) -> str:
    digest = hashlib.sha256(
        f"{document_sha256}:{claim_type}:{start}:{end}".encode()
    ).hexdigest()[:20]
    return f"resume_{claim_type}_{digest}"


def _append_claim(
    claims: list[ResumeClaim],
    *,
    document: ExtractedDocument,
    claim_type: ResumeClaimType,
    source_text: str,
    start: int,
    end: int,
    confidence: float,
) -> None:
    normalized = _normalise_claim_text(source_text)
    if len(normalized) < 2 or len(claims) >= 300:
        return
    claims.append(
        ResumeClaim(
            claim_id=_claim_id(document.sha256, claim_type, start, end),
            claim_type=claim_type,
            normalized_text=normalized,
            source=SourceSpan(
                page=page_for_offset(document, start),
                start_character=start,
                end_character=end,
                source_text=source_text,
            ),
            confidence=confidence,
            normalized_skills=[normalized.casefold()] if claim_type == "skill" else [],
        )
    )


def extract_resume_evidence(document: ExtractedDocument) -> ResumeEvidence:
    """Extract conservative heading-scoped claims while retaining exact source spans."""
    claims: list[ResumeClaim] = []
    active_section: ResumeClaimType | None = None
    for start, end, line in iter_nonempty_lines(document.text):
        heading = HEADING_PATTERN.fullmatch(line.strip())
        inline_text: str | None = None
        if heading:
            header = re.sub(r"\s+", " ", heading.group("header")).strip().casefold()
            matched_section = SECTION_ALIASES.get(header)
            if matched_section:
                active_section = matched_section
                inline_text = heading.group("inline")
                if inline_text:
                    inline_start = start + line.index(inline_text)
                    line = inline_text
                    start = inline_start
                    end = inline_start + len(inline_text)
                else:
                    continue
            elif line.isupper() and len(line.split()) <= 5:
                active_section = None
                continue
        if active_section is None:
            continue
        if active_section == "skill":
            for match in re.finditer(r"[^,;|]+", line):
                raw = match.group(0)
                left_trim = len(raw) - len(raw.lstrip())
                right = len(raw.rstrip())
                item_start = start + match.start() + left_trim
                item_end = start + match.start() + right
                if item_end > item_start:
                    _append_claim(
                        claims,
                        document=document,
                        claim_type="skill",
                        source_text=document.text[item_start:item_end],
                        start=item_start,
                        end=item_end,
                        confidence=0.94,
                    )
        else:
            _append_claim(
                claims,
                document=document,
                claim_type=active_section,
                source_text=document.text[start:end],
                start=start,
                end=end,
                confidence=0.86,
            )
    return ResumeEvidence(
        document_sha256=document.sha256,
        extractor_name="roleready-heading-scoped-resume-parser",
        extractor_version="1.0.0",
        claims=claims,
    )
