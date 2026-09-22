"""Abstraction over the multimodal/vision backend (spec section 8: "keep
the model/provider behind a clean abstraction so it can be replaced
later"). Two implementations exist: GeminiVisionProvider (real calls) and
MockVisionProvider (deterministic, used in tests and whenever no API key
is configured)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel

from app.models.schemas import LayoutBlock


class VisionBlocksResult(BaseModel):
    raw_text: str
    blocks: List[LayoutBlock]
    low_confidence: bool = False


class VisionProvider(ABC):
    """Everything the rest of the pipeline needs from a vision/multimodal
    model. Implementations must never invent structure that isn't
    supported by what they actually saw - if the model can't confidently
    segment the page, returning it as a single low-confidence paragraph
    block is preferable to fabricating a rich layout."""

    @abstractmethod
    def extract_document_blocks(self, image_bytes: bytes, page_num: int = 1) -> VisionBlocksResult:
        """OCR + coarse layout understanding for one page/image."""

    @abstractmethod
    def extract_meeting_json(self, context_text: str, schema_json: str) -> str:
        """Ask the model to fill the MeetingMinutes JSON schema strictly
        from `context_text`. Must return a raw JSON string (no markdown
        fences) - callers are responsible for schema validation."""

    @abstractmethod
    def generate_narrative_section(self, prompt: str) -> str:
        """Free-text generation step (e.g. discussion summary, executive
        summary) used only after structured extraction+validation."""
