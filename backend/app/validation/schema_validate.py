"""Structural validation of a MeetingMinutes object beyond what Pydantic's
type-checking alone covers (e.g. flags rather than crashes)."""
from __future__ import annotations

from app.models.schemas import MeetingMinutes, ValidationIssue


def validate_structure(minutes: MeetingMinutes) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if not minutes.meeting_title and not minutes.date and not minutes.discussion_points and not minutes.action_items:
        issues.append(
            ValidationIssue(
                severity="warning",
                field="*",
                message="Almost nothing could be extracted from this document. Verify the upload is correct.",
            )
        )

    for i, item in enumerate(minutes.action_items):
        if not item.task.strip():
            issues.append(
                ValidationIssue(severity="error", field=f"action_items[{i}].task", message="Action item has no task text.")
            )
        if not item.owner:
            issues.append(
                ValidationIssue(
                    severity="info",
                    field=f"action_items[{i}].owner",
                    message="No owner identified for this action item - do not assume one.",
                )
            )
        if not item.deadline:
            issues.append(
                ValidationIssue(
                    severity="info",
                    field=f"action_items[{i}].deadline",
                    message="No deadline identified for this action item - do not assume one.",
                )
            )

    if not minutes.date:
        issues.append(ValidationIssue(severity="info", field="date", message="No meeting date was found in the source."))
    if not minutes.location:
        issues.append(ValidationIssue(severity="info", field="location", message="No location was found in the source."))

    return issues
