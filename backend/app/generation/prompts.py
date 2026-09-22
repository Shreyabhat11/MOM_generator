"""All prompt text lives here (spec section 35: avoid hard-coded prompts
scattered through the code)."""
from __future__ import annotations

import json

from app.models.schemas import MeetingMinutes

DISCUSSION_SUMMARY_PROMPT = """You are writing the "Discussion Summary" section of a Minutes of Meeting
document. You are given ONLY the structured, already-validated facts below
(not the raw document) - do not add any fact that is not in this data.

Rules:
- Do not invent names, dates, numbers, or commitments.
- Preserve every decision, action item, owner, deadline, risk, and open
  question that appears in the data - do not compress them away into vague
  language (e.g. do not write "the team discussed next steps" if a
  specific commitment with an owner and deadline is present in the data).
- If a field is null/empty, do not mention it or make something up for it.
- Write 3-8 sentences of plain, professional prose. No headings, no
  markdown, no bullet points - just the paragraph(s).

Structured meeting data (JSON):
{data_json}
"""

EXECUTIVE_SUMMARY_PROMPT = """Write a 2-4 sentence executive summary of this meeting for someone who did
not attend, using ONLY the structured facts below. Do not add any fact not
present in the data. If very little information is available, say so
plainly rather than padding with generic language.

Structured meeting data (JSON):
{data_json}
"""


def render_discussion_summary_prompt(minutes: MeetingMinutes) -> str:
    return DISCUSSION_SUMMARY_PROMPT.format(data_json=json.dumps(minutes.model_dump(exclude={"field_confidence"}), indent=2))


def render_executive_summary_prompt(minutes: MeetingMinutes) -> str:
    return EXECUTIVE_SUMMARY_PROMPT.format(data_json=json.dumps(minutes.model_dump(exclude={"field_confidence"}), indent=2))
