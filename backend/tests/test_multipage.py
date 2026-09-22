"""Spec section 10: multi-page documents must be treated as one coherent
document, with chunking for anything too large for a single model call."""
from app.extraction.meeting import (
    _MAX_CHARS_PER_CHUNK,
    _chunk_pages_by_char_budget,
    _merge_minutes,
    extract_meeting_minutes,
)
from app.models.schemas import ActionItem, DocumentKind, ExtractionResult, MeetingMinutes, PageResult


def _page(n: int, text: str) -> PageResult:
    return PageResult(page=n, blocks=[], raw_text=text)


def test_small_document_is_not_chunked():
    pages = [_page(1, "short text")]
    chunks = _chunk_pages_by_char_budget(pages, max_chars=1000)
    assert len(chunks) == 1


def test_large_document_splits_into_multiple_chunks_without_splitting_a_page():
    pages = [_page(i, "x" * 500) for i in range(1, 21)]  # 20 pages x 500 chars = 10,000 chars
    chunks = _chunk_pages_by_char_budget(pages, max_chars=2000)
    assert len(chunks) > 1
    # every page marker should appear in exactly one chunk, never split
    for i in range(1, 21):
        marker = f"[Page {i}]"
        containing = [c for c in chunks if marker in c]
        assert len(containing) == 1


def test_oversized_single_page_becomes_its_own_chunk():
    pages = [_page(1, "x" * 5000)]
    chunks = _chunk_pages_by_char_budget(pages, max_chars=2000)
    assert len(chunks) == 1
    assert len(chunks[0]) > 2000


def test_merge_minutes_takes_first_non_null_scalar():
    part1 = MeetingMinutes(date=None, meeting_title="Q1 Sync")
    part2 = MeetingMinutes(date="March 14, 2025", meeting_title="Should not override")
    merged = _merge_minutes([part1, part2])
    assert merged.meeting_title == "Q1 Sync"
    assert merged.date == "March 14, 2025"


def test_merge_minutes_concatenates_action_items_from_all_chunks():
    part1 = MeetingMinutes(action_items=[ActionItem(task="Task from page 1")])
    part2 = MeetingMinutes(action_items=[ActionItem(task="Task from page 2")])
    merged = _merge_minutes([part1, part2])
    assert len(merged.action_items) == 2
    assert {a.task for a in merged.action_items} == {"Task from page 1", "Task from page 2"}


def test_extract_meeting_minutes_routes_large_documents_through_chunking(mock_vision, monkeypatch):
    calls = []
    original = mock_vision.extract_meeting_json

    def tracking(context_text, schema_json):
        calls.append(context_text)
        return original(context_text, schema_json)

    monkeypatch.setattr(mock_vision, "extract_meeting_json", tracking)

    # Build a document whose total text exceeds the chunk budget.
    big_pages = [_page(i, ("Decision: item " + str(i) + ". ") * 200) for i in range(1, 5)]
    extraction = ExtractionResult(document_kind=DocumentKind.PDF_NATIVE, pages=big_pages)
    assert len(extraction.full_text()) > _MAX_CHARS_PER_CHUNK

    minutes = extract_meeting_minutes(extraction, mock_vision)
    assert len(calls) > 1  # multiple chunk calls were made, not one giant call
    assert minutes.decisions  # results from multiple chunks were merged in
