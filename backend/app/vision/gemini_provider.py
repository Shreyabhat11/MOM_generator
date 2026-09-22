"""Real multimodal provider using the current `google-genai` SDK
(spec section 8: "use its current supported API consistently, do not mix
incompatible SDK generations" - the old prototype mixed `google.genai` and
`google.generativeai`, which are different packages; this file uses only
`google.genai`).

NOTE: this file has not been exercised against a live API key in this
build (see README "Testing" / "Known limitations") - it was written
against the documented google-genai client interface and is covered by
unit tests only through the VisionProvider mock, not integration tests.
Treat it as a first pass; verify against a real key before production use.
"""
from __future__ import annotations

import json
from typing import List

from google import genai
from google.genai import types

from app.config import get_settings
from app.models.schemas import BlockType, LayoutBlock
from app.vision.provider import VisionBlocksResult, VisionProvider

DOCUMENT_BLOCKS_PROMPT = """You are a document layout and OCR engine. You will be shown one page of a
(possibly handwritten) meeting document.

Return ONLY a JSON object (no markdown fences, no commentary) of the shape:
{
  "raw_text": "<all text on the page, reading order, best transcription>",
  "blocks": [
    {"block_type": "heading|paragraph|bullet|numbered_item|table|checkbox|
       action_item|decision|date|time|person|organization|location|
       annotation|handwritten_note|unknown",
     "text": "...", "order": 0}
  ],
  "low_confidence": true|false
}

Rules:
- Transcribe exactly what is visually present. Do not guess words you cannot
  read; represent illegible text as [illegible].
- Do not infer information that is not visually present (e.g. do not invent
  a date, name, or location if none is written).
- Preserve tables as a single block per table with text using " | " as the
  column separator and newlines between rows.
- Set "low_confidence": true if handwriting, image quality, or ambiguity
  make you meaningfully unsure of the transcription.
"""

EXTRACTION_SYSTEM_PROMPT = """You are a strict information-extraction engine for meeting documents.
You will be given the already-extracted text/layout of a document.

Return ONLY a JSON object matching this schema (no markdown fences, no
commentary):
{schema_json}

Hard rules:
1. Every field must be grounded in the provided text. If a fact is not
   present, use null (for scalars) or an empty list (for lists). Never
   invent a plausible-sounding value.
2. Do not infer a location as "Online" or a date as "today" unless the text
   actually says so.
3. For each action_item, only fill "owner" or "deadline" if explicitly
   stated or unambiguously implied by adjacent text; otherwise use null.
4. Attach a "source" object {{"page": <int or null>, "text": "<the exact
   snippet you used>"}} to every action_item and, where feasible, to other
   fields, so facts can be traced back to the document.
5. Attach a "confidence" object {{"score": 0-1 float, "needs_review": bool,
   "reason": "..."}} to fields derived from ambiguous or handwritten text.

Document text:
{context_text}
"""


class GeminiVisionProvider(VisionProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model_name = settings.model_name

    def extract_document_blocks(self, image_bytes: bytes, page_num: int = 1) -> VisionBlocksResult:
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[
                DOCUMENT_BLOCKS_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
            ],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            # Model didn't return valid JSON: fail safe rather than crash
            # the whole pipeline, and mark clearly low-confidence.
            text = getattr(response, "text", "") or ""
            block = LayoutBlock(page=page_num, block_type=BlockType.UNKNOWN, text=text, order=0, source="vision_model")
            return VisionBlocksResult(raw_text=text, blocks=[block], low_confidence=True)

        blocks: List[LayoutBlock] = []
        for i, b in enumerate(data.get("blocks", [])):
            try:
                block_type = BlockType(b.get("block_type", "unknown"))
            except ValueError:
                block_type = BlockType.UNKNOWN
            blocks.append(
                LayoutBlock(
                    page=page_num,
                    block_type=block_type,
                    text=b.get("text", ""),
                    order=b.get("order", i),
                    source="vision_model",
                )
            )
        return VisionBlocksResult(
            raw_text=data.get("raw_text", ""),
            blocks=blocks,
            low_confidence=bool(data.get("low_confidence", False)),
        )

    def extract_meeting_json(self, context_text: str, schema_json: str) -> str:
        prompt = EXTRACTION_SYSTEM_PROMPT.format(schema_json=schema_json, context_text=context_text)
        response = self._client.models.generate_content(
            model=self._model_name,
            contents=[prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return response.text

    def generate_narrative_section(self, prompt: str) -> str:
        response = self._client.models.generate_content(model=self._model_name, contents=[prompt])
        return response.text
