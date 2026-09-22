import pytest
from pydantic import ValidationError

from app.models.schemas import ActionItem, Confidence, MeetingMinutes


def test_meeting_minutes_defaults_are_all_absent():
    m = MeetingMinutes()
    assert m.meeting_title is None
    assert m.date is None
    assert m.location is None
    assert m.attendees == []
    assert m.action_items == []


def test_action_item_requires_task_but_not_owner_or_deadline():
    item = ActionItem(task="Prepare report")
    assert item.owner is None
    assert item.deadline is None


def test_action_item_without_task_is_rejected():
    with pytest.raises(ValidationError):
        ActionItem()  # task is required


def test_low_confidence_score_flags_needs_review():
    c = Confidence(score=0.3)
    assert c.needs_review is True


def test_high_confidence_score_does_not_force_review():
    c = Confidence(score=0.95)
    assert c.needs_review is False


def test_action_item_confidence_flows_through_when_provided():
    item = ActionItem(task="Send report", confidence=Confidence(score=0.4))
    assert item.confidence.needs_review is True
