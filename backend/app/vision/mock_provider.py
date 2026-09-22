"""Deterministic mock so the whole pipeline (and the test suite) runs with
zero network access and zero API cost. Also what the backend falls back to
automatically if no GEMINI_API_KEY is configured, so the app is always
runnable end-to-end out of the box (with a clear "mock mode" warning)."""
from __future__ import annotations

import json
import re
from typing import List

from app.models.schemas import BlockType, LayoutBlock
from app.vision.provider import VisionBlocksResult, VisionProvider


class MockVisionProvider(VisionProvider):
    def extract_document_blocks(self, image_bytes: bytes, page_num: int = 1) -> VisionBlocksResult:
        # No real OCR available offline: honestly report that nothing could
        # be read, rather than fabricating plausible-looking text.
        text = (
            "[MOCK VISION MODE: no OCR was performed on this image/scanned "
            "page because no GEMINI_API_KEY is configured. Configure "
            "GEMINI_API_KEY to enable real handwriting/OCR extraction.]"
        )
        block = LayoutBlock(
            page=page_num, block_type=BlockType.UNKNOWN, text=text, order=0, source="mock_vision"
        )
        return VisionBlocksResult(raw_text=text, blocks=[block], low_confidence=True)

    def extract_meeting_json(self, context_text: str, schema_json: str) -> str:
        """Deterministic, conservative rule-based extraction used only when
        no real model is configured. Intentionally simple: it is meant to
        keep the pipeline runnable/testable, not to replace the LLM's
        semantic understanding."""
        data = {
            "meeting_title": None,
            "date": None,
            "time": None,
            "location": None,
            "organizer": None,
            "attendees": [],
            "agenda": [],
            "discussion_points": [],
            "decisions": [],
            "action_items": [],
            "risks": [],
            "open_questions": [],
            "next_meeting": None,
            "summary": "",
        }
        date_match = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\w+ \d{1,2},? \d{4})\b", context_text)
        if date_match:
            data["date"] = date_match.group(0)

        lines = [l.strip() for l in context_text.splitlines() if l.strip()]
        for line in lines:
            lower = line.lower()
            if lower.startswith("decision"):
                data["decisions"].append(line.split(":", 1)[-1].strip())
            elif "action" in lower and ":" in line:
                data["action_items"].append(
                    {"task": line.split(":", 1)[-1].strip(), "owner": None, "deadline": None,
                     "source": None, "confidence": {"score": 0.4, "needs_review": True, "reason": "mock extraction"}}
                )
            elif lower.startswith(("discussed", "-", "*")):
                data["discussion_points"].append(line.lstrip("-* ").strip())

        if lines:
            data["summary"] = "Not generated: mock mode does not perform semantic summarization."
        return json.dumps(data)

    def generate_narrative_section(self, prompt: str) -> str:
        """Rather than a useless placeholder, deterministically compose a
        plain-text section directly from the structured JSON embedded in
        the prompt (see generation/prompts.py) - every sentence is a
        near-verbatim transcription of a field that already passed
        validation, so nothing new is being invented, just formatted."""
        marker = "Structured meeting data (JSON):"
        if marker not in prompt:
            return "[MOCK MODE] No structured data was available to compose this section."
        try:
            data = json.loads(prompt.split(marker, 1)[1].strip())
        except json.JSONDecodeError:
            return "[MOCK MODE] Could not parse structured data for this section."

        sentences: List[str] = []
        if data.get("discussion_points"):
            sentences.append("Discussion covered: " + "; ".join(data["discussion_points"]) + ".")
        if data.get("decisions"):
            sentences.append("Decisions made: " + "; ".join(data["decisions"]) + ".")
        if data.get("action_items"):
            parts = []
            for a in data["action_items"]:
                owner = a.get("owner") or "an unspecified owner"
                deadline = f" by {a['deadline']}" if a.get("deadline") else ""
                parts.append(f"{a.get('task')} ({owner}{deadline})")
            sentences.append("Action items: " + "; ".join(parts) + ".")
        if data.get("risks"):
            sentences.append("Risks noted: " + "; ".join(data["risks"]) + ".")
        if data.get("open_questions"):
            sentences.append("Open questions: " + "; ".join(data["open_questions"]) + ".")

        if not sentences:
            return "Not available: no discussion points, decisions, or action items were extracted from the source document."
        return " ".join(sentences) + " [Generated in mock mode: plain transcription of extracted fields, no LLM summarization was applied.]"
