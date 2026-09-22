"""
Core data contracts for the MoM pipeline.

Design principle (see README "Trustworthiness"): every field that the LLM
fills in must be representable as *absent* rather than guessed. We never use
empty string "" to mean "unknown" - we use `None` / the literal strings
"Not mentioned" / "Unclear", and every non-trivial fact carries a Confidence
and, where possible, a SourceReference back to the extracted document.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


# --------------------------------------------------------------------------
# Document ingestion / layout
# --------------------------------------------------------------------------

class DocumentKind(str, Enum):
    PDF_NATIVE = "pdf_native"
    PDF_SCANNED = "pdf_scanned"
    PDF_MIXED = "pdf_mixed"
    DOCX = "docx"
    IMAGE = "image"
    UNKNOWN = "unknown"


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BULLET = "bullet"
    NUMBERED_ITEM = "numbered_item"
    TABLE = "table"
    CHECKBOX = "checkbox"
    ACTION_ITEM = "action_item"
    DECISION = "decision"
    DATE = "date"
    TIME = "time"
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    ANNOTATION = "annotation"
    HANDWRITTEN_NOTE = "handwritten_note"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float


class TableData(BaseModel):
    rows: List[List[str]] = Field(default_factory=list)


class LayoutBlock(BaseModel):
    """One unit of content, tagged with a coarse type and provenance.

    `bbox` is best-effort: for native PDF/DOCX text it can be reasonably
    precise; for vision-model-derived blocks (handwriting, scans) it is a
    model estimate and should be treated as approximate, not pixel-exact.
    """
    page: int = 1
    block_type: BlockType = BlockType.UNKNOWN
    text: str = ""
    table: Optional[TableData] = None
    bbox: Optional[BoundingBox] = None
    order: int = 0
    source: str = Field(
        default="unknown",
        description="Where this block came from: native_pdf, docx, vision_model, ocr",
    )


class PageResult(BaseModel):
    page: int
    blocks: List[LayoutBlock] = Field(default_factory=list)
    raw_text: str = ""


class ExtractionResult(BaseModel):
    """Output of the ingestion + layout stage. This is deterministic /
    reproducible: no LLM creativity happens here, only parsing + OCR."""
    document_kind: DocumentKind
    pages: List[PageResult] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    def full_text(self) -> str:
        return "\n".join(p.raw_text for p in self.pages if p.raw_text)

    def is_empty(self) -> bool:
        return not any(p.raw_text.strip() for p in self.pages)


# --------------------------------------------------------------------------
# Structured meeting data (post-LLM-extraction, pre-generation)
# --------------------------------------------------------------------------

class Confidence(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    needs_review: bool = False
    reason: Optional[str] = None

    @model_validator(mode="after")
    def _flag_low_confidence(self) -> "Confidence":
        if self.score < 0.55 and not self.needs_review:
            self.needs_review = True
        return self


class SourceReference(BaseModel):
    page: Optional[int] = None
    text: Optional[str] = None


class ActionItem(BaseModel):
    task: str
    owner: Optional[str] = None
    deadline: Optional[str] = None
    source: Optional[SourceReference] = None
    confidence: Optional[Confidence] = None


class MeetingMinutes(BaseModel):
    """The strict schema described in the spec (section 11), used as the
    contract between extraction and generation. Nothing downstream is
    allowed to add facts that aren't represented here."""

    meeting_title: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    organizer: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    agenda: List[str] = Field(default_factory=list)
    discussion_points: List[str] = Field(default_factory=list)
    decisions: List[str] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    next_meeting: Optional[str] = None
    summary: str = ""

    # bookkeeping, not part of the LLM-facing schema
    field_confidence: dict = Field(default_factory=dict)


# --------------------------------------------------------------------------
# Validation / hallucination-check results
# --------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    severity: str  # "info" | "warning" | "error"
    field: str
    message: str


class ValidationReport(BaseModel):
    passed: bool
    issues: List[ValidationIssue] = Field(default_factory=list)
    unsupported_claims: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Document processing state (API-facing)
# --------------------------------------------------------------------------

class ProcessingStage(str, Enum):
    UPLOADED = "uploaded"
    CLASSIFIED = "classified"
    EXTRACTED = "extracted"
    STRUCTURED = "structured"
    VALIDATED = "validated"
    GENERATED = "generated"
    FAILED = "failed"


class DocumentRecord(BaseModel):
    id: str
    filename: str
    content_type: str
    stage: ProcessingStage = ProcessingStage.UPLOADED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    error: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
