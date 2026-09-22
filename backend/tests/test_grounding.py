from app.models.schemas import ActionItem, MeetingMinutes
from app.validation.grounding import check_grounding


SOURCE = (
    "Weekly Sync - Engineering Team. Date: March 14, 2025. "
    "Raj will send revised budget by Friday. Sarah will review it Monday. "
    "Decision: proceed with vendor A."
)


def test_grounded_facts_pass_without_warnings():
    minutes = MeetingMinutes(
        date="March 14, 2025",
        decisions=["proceed with vendor A"],
        action_items=[ActionItem(task="send revised budget", owner="Raj", deadline="Friday")],
    )
    report = check_grounding(minutes, SOURCE)
    assert report.passed
    assert report.unsupported_claims == []


def test_fabricated_field_is_flagged_as_unsupported():
    minutes = MeetingMinutes(location="Mars Colony Alpha Base")
    report = check_grounding(minutes, SOURCE)
    assert any("location" in c for c in report.unsupported_claims)


def test_fabricated_decision_is_flagged():
    minutes = MeetingMinutes(decisions=["The team decided to launch a satellite program"])
    report = check_grounding(minutes, SOURCE)
    assert report.unsupported_claims


def test_facts_populated_from_empty_source_is_a_hard_error():
    minutes = MeetingMinutes(meeting_title="Quarterly Board Review", decisions=["Approved the merger"])
    report = check_grounding(minutes, "")
    assert report.passed is False
    assert any(i.severity == "error" for i in report.issues)


def test_empty_minutes_against_real_source_passes():
    report = check_grounding(MeetingMinutes(), SOURCE)
    assert report.passed
