"""Orchestrates grounded MoM generation (spec sections 14-16).

Pipeline for this stage:
  validated MeetingMinutes
    -> generate discussion_points prose (only if missing) and summary
    -> re-run grounding check on generated prose against source text
    -> if unsupported, the prose is DROPPED (not shown) and replaced with
       a plain notice, never silently kept
"""
from __future__ import annotations

from app.extraction.normalization import normalize_meeting_minutes
from app.generation.prompts import render_discussion_summary_prompt, render_executive_summary_prompt
from app.models.schemas import MeetingMinutes, ValidationReport
from app.validation.grounding import is_grounded, tokenize  # reuse the same heuristic
from app.vision.provider import VisionProvider

UNGROUNDED_NOTICE = "Not available: a generated summary could not be verified against the source document."


def generate_mom(minutes: MeetingMinutes, source_text: str, vision: VisionProvider) -> tuple[MeetingMinutes, ValidationReport]:
    minutes = normalize_meeting_minutes(minutes)
    source_tokens = tokenize(source_text)

    issues = []
    unsupported = []

    exec_summary = vision.generate_narrative_section(render_executive_summary_prompt(minutes))
    if is_grounded(exec_summary, source_tokens, min_overlap_ratio=0.25):
        minutes.summary = exec_summary.strip()
    else:
        minutes.summary = UNGROUNDED_NOTICE
        unsupported.append(f"summary: {exec_summary.strip()[:200]}")

    # Discussion summary is generated as a *narrative rendering aid* only
    # when there are discussion_points to work from; we never let the LLM
    # invent discussion points that extraction didn't find.
    if minutes.discussion_points:
        narrative = vision.generate_narrative_section(render_discussion_summary_prompt(minutes))
        if is_grounded(narrative, source_tokens, min_overlap_ratio=0.25):
            minutes.field_confidence["discussion_narrative"] = narrative.strip()
        else:
            unsupported.append(f"discussion_narrative: {narrative.strip()[:200]}")

    passed = len(unsupported) == 0
    report = ValidationReport(passed=passed, issues=issues, unsupported_claims=unsupported)
    return minutes, report
