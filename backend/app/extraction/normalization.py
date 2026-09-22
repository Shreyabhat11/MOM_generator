"""Deterministic normalization of extracted fields (spec section 36:
"prefer deterministic processing" over more LLM calls where possible).
Never *adds* facts - only cleans/standardizes what's already there."""
from __future__ import annotations

from app.models.schemas import MeetingMinutes

_PLACEHOLDER_VALUES = {"", "n/a", "na", "none", "null", "tbd", "unknown"}


def _clean_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.lower() in _PLACEHOLDER_VALUES:
        return None
    return stripped


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def normalize_meeting_minutes(minutes: MeetingMinutes) -> MeetingMinutes:
    minutes.meeting_title = _clean_scalar(minutes.meeting_title)
    minutes.date = _clean_scalar(minutes.date)
    minutes.time = _clean_scalar(minutes.time)
    minutes.location = _clean_scalar(minutes.location)
    minutes.organizer = _clean_scalar(minutes.organizer)
    minutes.next_meeting = _clean_scalar(minutes.next_meeting)

    minutes.attendees = _dedupe_preserve_order(minutes.attendees)
    minutes.agenda = _dedupe_preserve_order(minutes.agenda)
    minutes.discussion_points = _dedupe_preserve_order(minutes.discussion_points)
    minutes.decisions = _dedupe_preserve_order(minutes.decisions)
    minutes.risks = _dedupe_preserve_order(minutes.risks)
    minutes.open_questions = _dedupe_preserve_order(minutes.open_questions)

    for item in minutes.action_items:
        item.task = item.task.strip()
        item.owner = _clean_scalar(item.owner)
        item.deadline = _clean_scalar(item.deadline)

    return minutes
