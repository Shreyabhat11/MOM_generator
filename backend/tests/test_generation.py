from app.extraction.meeting import extract_meeting_minutes
from app.generation.mom import generate_mom
from app.models.schemas import DocumentKind, ExtractionResult, PageResult


SOURCE_TEXT = (
    "Weekly Sync\n"
    "Date: March 14, 2025\n"
    "discussed budget timeline\n"
    "Decision: proceed with vendor A\n"
    "Action: Raj to prepare financial report by Friday\n"
)


def _extraction_result():
    return ExtractionResult(
        document_kind=DocumentKind.DOCX,
        pages=[PageResult(page=1, blocks=[], raw_text=SOURCE_TEXT)],
    )


def test_no_hallucinated_fields_when_source_is_empty(mock_vision):
    empty = ExtractionResult(document_kind=DocumentKind.UNKNOWN, pages=[PageResult(page=1, blocks=[], raw_text="")])
    minutes = extract_meeting_minutes(empty, mock_vision)
    assert minutes.meeting_title is None
    assert minutes.date is None
    assert minutes.action_items == []


def test_decisions_are_preserved_through_extraction(mock_vision):
    minutes = extract_meeting_minutes(_extraction_result(), mock_vision)
    assert any("vendor a" in d.lower() for d in minutes.decisions)


def test_action_items_owner_and_deadline_preserved_when_present(mock_vision):
    # the mock extractor is intentionally simple (rule-based); this test
    # exercises the coercion/normalization path with an explicit item.
    from app.models.schemas import ActionItem, MeetingMinutes

    minutes = MeetingMinutes(action_items=[ActionItem(task="prepare financial report", owner="Raj", deadline="Friday")])
    from app.extraction.normalization import normalize_meeting_minutes

    normalized = normalize_meeting_minutes(minutes)
    assert normalized.action_items[0].owner == "Raj"
    assert normalized.action_items[0].deadline == "Friday"


def test_generation_drops_ungrounded_summary(mock_vision, monkeypatch):
    from app.models.schemas import MeetingMinutes

    minutes = MeetingMinutes(decisions=["proceed with vendor A"])

    def fake_narrative(prompt):
        return "Completely unrelated fabricated content about dinosaurs and spaceships never in the source."

    monkeypatch.setattr(mock_vision, "generate_narrative_section", fake_narrative)
    result, report = generate_mom(minutes, SOURCE_TEXT, mock_vision)
    assert result.summary == "Not available: a generated summary could not be verified against the source document."
    assert not report.passed


def test_generation_keeps_grounded_summary(mock_vision):
    from app.models.schemas import MeetingMinutes

    minutes = MeetingMinutes(
        decisions=["proceed with vendor A"],
        discussion_points=["budget timeline"],
    )
    result, report = generate_mom(minutes, SOURCE_TEXT, mock_vision)
    assert result.summary != ""
    assert "dinosaur" not in result.summary.lower()
