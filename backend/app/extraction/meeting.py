"""Structured meeting extraction: text/blocks -> validated MeetingMinutes.

This is "Layer 1" and "Layer 2" of hallucination prevention (spec section
15): the model is asked ONLY to extract structured facts (not to write
prose), and the response is strictly schema-validated before anything
downstream sees it.

Also implements spec section 10 (multi-page understanding): documents
whose combined text exceeds a conservative character budget are split into
page-aligned chunks, extracted independently, and deterministically merged
- so a 40-page scanned PDF doesn't silently get truncated or blow the
model's context window.
"""
from __future__ import annotations

import json
import logging

from pydantic import ValidationError

from app.models.schemas import ActionItem, ExtractionResult, MeetingMinutes, PageResult
from app.vision.provider import VisionProvider

logger = logging.getLogger("mom_generator")

# Conservative character budget per extraction call. This is deliberately
# well under typical model context windows (which are measured in tokens,
# roughly ~4 chars/token) - the goal is headroom for the schema/prompt
# overhead and multiple chunks' worth of margin, not to use 100% of any
# specific model's limit.
_MAX_CHARS_PER_CHUNK = 12_000

_MEETING_SCHEMA_JSON = json.dumps(
    {
        "meeting_title": "string or null",
        "date": "string or null",
        "time": "string or null",
        "location": "string or null",
        "organizer": "string or null",
        "attendees": ["string"],
        "agenda": ["string"],
        "discussion_points": ["string"],
        "decisions": ["string"],
        "action_items": [
            {
                "task": "string",
                "owner": "string or null",
                "deadline": "string or null",
                "source": {"page": "int or null", "text": "string or null"},
                "confidence": {"score": "0-1 float", "needs_review": "bool", "reason": "string or null"},
            }
        ],
        "risks": ["string"],
        "open_questions": ["string"],
        "next_meeting": "string or null",
        "summary": "string",
    },
    indent=2,
)


class ExtractionFailedError(Exception):
    pass


def _coerce_action_items(raw_items: list) -> list[ActionItem]:
    items: list[ActionItem] = []
    for raw in raw_items:
        if not isinstance(raw, dict) or not raw.get("task"):
            continue  # drop malformed entries rather than crash the whole extraction
        try:
            items.append(ActionItem(**raw))
        except ValidationError:
            # Fall back to the minimum viable fact rather than dropping a
            # real action item just because confidence/source was malformed.
            items.append(ActionItem(task=str(raw.get("task", "")).strip(), owner=raw.get("owner"), deadline=raw.get("deadline")))
    return items


def _parse_model_response(raw_response: str) -> MeetingMinutes:
    """Parses+validates one model JSON response into a MeetingMinutes.
    Shared by both the single-call and chunked extraction paths."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if cleaned.lower().startswith("json") else cleaned

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("extraction_json_parse_failed", extra={"stage": "extraction"})
        raise ExtractionFailedError(f"Model did not return valid JSON: {exc}") from exc

    action_items_raw = data.pop("action_items", [])
    try:
        minutes = MeetingMinutes(**{k: v for k, v in data.items() if k in MeetingMinutes.model_fields})
    except ValidationError as exc:
        logger.warning("extraction_schema_invalid", extra={"stage": "extraction"})
        raise ExtractionFailedError(f"Model output failed schema validation: {exc}") from exc

    minutes.action_items = _coerce_action_items(action_items_raw)
    return minutes


def _chunk_pages_by_char_budget(pages: list[PageResult], max_chars: int) -> list[str]:
    """Groups whole pages into text chunks under `max_chars`, never
    splitting a page across chunks (keeps each chunk coherent). A single
    page longer than the budget becomes its own (oversized) chunk rather
    than being truncated - see docstring above re: truncation."""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for page in pages:
        page_text = f"[Page {page.page}]\n{page.raw_text}"
        if current and current_len + len(page_text) > max_chars:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(page_text)
        current_len += len(page_text)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _merge_minutes(parts: list[MeetingMinutes]) -> MeetingMinutes:
    """Deterministically merges per-chunk MeetingMinutes into one document-
    level result. Scalars: first non-null value found (a scalar fact like
    "date" typically only appears on one page/chunk, so first-found is
    correct far more often than concatenation would be). Lists: union
    across chunks, in order, duplicates removed by the normalization step
    downstream. Action items: concatenated (an action item from chunk 2 is
    just as real as one from chunk 1 - never dropped for being "later")."""
    merged = MeetingMinutes()
    for part in parts:
        merged.meeting_title = merged.meeting_title or part.meeting_title
        merged.date = merged.date or part.date
        merged.time = merged.time or part.time
        merged.location = merged.location or part.location
        merged.organizer = merged.organizer or part.organizer
        merged.next_meeting = merged.next_meeting or part.next_meeting

        merged.attendees += part.attendees
        merged.agenda += part.agenda
        merged.discussion_points += part.discussion_points
        merged.decisions += part.decisions
        merged.risks += part.risks
        merged.open_questions += part.open_questions
        merged.action_items += part.action_items

    non_empty_summaries = [p.summary.strip() for p in parts if p.summary and p.summary.strip()]
    merged.summary = " ".join(non_empty_summaries)
    return merged


def extract_meeting_minutes(extraction: ExtractionResult, vision: VisionProvider) -> MeetingMinutes:
    context_text = extraction.full_text()
    if not context_text.strip():
        # Nothing to extract from - return an all-null schema rather than
        # calling the model on empty input.
        return MeetingMinutes(summary="Not available: no text could be extracted from the source document.")

    if len(context_text) <= _MAX_CHARS_PER_CHUNK:
        raw_response = vision.extract_meeting_json(context_text, _MEETING_SCHEMA_JSON)
        return _parse_model_response(raw_response)

    # Multi-page / long-document path: chunk, extract each chunk
    # independently, and merge deterministically rather than truncating or
    # exceeding the model's context window.
    chunks = _chunk_pages_by_char_budget(extraction.pages, _MAX_CHARS_PER_CHUNK)
    logger.info(
        "extraction_chunked",
        extra={"stage": "extraction", "status": "chunking", "chunk_count": len(chunks)},
    )
    parts: list[MeetingMinutes] = []
    for chunk_text in chunks:
        raw_response = vision.extract_meeting_json(chunk_text, _MEETING_SCHEMA_JSON)
        parts.append(_parse_model_response(raw_response))
    return _merge_minutes(parts)
