"""Grounding / hallucination checks: "Layer 4" of spec section 15.

After structured extraction (which is already constrained/schema-validated),
this does one more deterministic pass: every scalar/list fact in the
MeetingMinutes must have reasonable lexical overlap with the source text.
Facts that don't are flagged as unsupported - not silently removed, so a
human reviewer can see exactly what's in question (spec section 17).

This is a heuristic (word-overlap) check, not a semantic entailment model.
It catches the common/serious failure mode (fields invented wholesale with
no textual basis) but will not catch subtle paraphrase drift. This
limitation is stated explicitly in the README rather than oversold.
"""
from __future__ import annotations

import re

from app.models.schemas import MeetingMinutes, ValidationIssue, ValidationReport

_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "is", "are",
    "will", "by", "at", "as", "be", "this", "that", "it", "we", "i",
}


def tokenize(text: str) -> set[str]:
    """Public: significant (non-stopword) lowercase tokens in `text`. Used
    both by this module's own field-level checks and by generation/mom.py
    when it re-checks generated prose against the source."""
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS and len(t) > 1}


def is_grounded(claim: str, source_tokens: set[str], min_overlap_ratio: float = 0.4) -> bool:
    """Public: does `claim` have enough lexical overlap with `source_tokens`
    to be considered supported? See module docstring for the heuristic's
    known limitations."""
    claim_tokens = tokenize(claim)
    if not claim_tokens:
        return True  # nothing substantive to check
    overlap = claim_tokens & source_tokens
    return (len(overlap) / len(claim_tokens)) >= min_overlap_ratio


def check_grounding(minutes: MeetingMinutes, source_text: str) -> ValidationReport:
    source_tokens = tokenize(source_text)
    issues: list[ValidationIssue] = []
    unsupported: list[str] = []

    def check_field(field_name: str, value: str | None):
        if not value:
            return
        if not is_grounded(value, source_tokens):
            issues.append(
                ValidationIssue(
                    severity="warning",
                    field=field_name,
                    message=f"'{value}' has low lexical overlap with the source document and may be unsupported.",
                )
            )
            unsupported.append(f"{field_name}: {value}")

    check_field("meeting_title", minutes.meeting_title)
    check_field("date", minutes.date)
    check_field("location", minutes.location)
    check_field("organizer", minutes.organizer)

    for i, decision in enumerate(minutes.decisions):
        check_field(f"decisions[{i}]", decision)
    for i, item in enumerate(minutes.action_items):
        check_field(f"action_items[{i}].task", item.task)
        if item.owner:
            check_field(f"action_items[{i}].owner", item.owner)

    if not source_text.strip() and any(
        [minutes.meeting_title, minutes.date, minutes.decisions, minutes.action_items]
    ):
        issues.append(
            ValidationIssue(
                severity="error",
                field="*",
                message="Fields were populated despite empty source text - this indicates fabrication.",
            )
        )

    passed = not any(i.severity == "error" for i in issues)
    return ValidationReport(passed=passed, issues=issues, unsupported_claims=unsupported)
