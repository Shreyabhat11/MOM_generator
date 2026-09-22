"""Inspects the uploaded file (never trusts the filename/extension alone)
and dispatches to the right extractor (spec section 5: "inspect the
uploaded file rather than blindly assuming what type of document it is")."""
from __future__ import annotations

import filetype

from app.config import Settings
from app.ingestion.docx import extract_docx
from app.ingestion.image import extract_image
from app.ingestion.pdf import classify_and_extract_pdf
from app.models.schemas import DocumentKind, ExtractionResult
from app.vision.provider import VisionProvider

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class UnsupportedFileError(Exception):
    pass


class EmptyFileError(Exception):
    pass


def sniff_content_type(file_bytes: bytes, declared_content_type: str, filename: str) -> str:
    """Determine the real file type from magic bytes, falling back to the
    declared content-type/extension only if sniffing is inconclusive
    (true for some minimal/edge-case DOCX and text-only PDFs)."""
    if not file_bytes:
        raise EmptyFileError("Uploaded file is empty.")

    kind = filetype.guess(file_bytes)
    if kind is not None:
        if kind.mime == "application/zip" and filename.lower().endswith(".docx"):
            return _DOCX_MIME
        return kind.mime

    if declared_content_type in ("application/pdf",) or filename.lower().endswith(".pdf"):
        return "application/pdf"
    if filename.lower().endswith(".docx"):
        return _DOCX_MIME
    if filename.lower().endswith((".png",)):
        return "image/png"
    if filename.lower().endswith((".jpg", ".jpeg")):
        return "image/jpeg"

    raise UnsupportedFileError(f"Could not determine file type for '{filename}'.")


def extract(
    file_bytes: bytes,
    filename: str,
    declared_content_type: str,
    settings: Settings,
    vision: VisionProvider,
) -> tuple[str, ExtractionResult]:
    """Returns (sniffed_content_type, ExtractionResult)."""
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        raise UnsupportedFileError(
            f"File is {size_mb:.1f}MB, which exceeds the {settings.max_file_size_mb}MB limit."
        )

    content_type = sniff_content_type(file_bytes, declared_content_type, filename)
    if content_type not in settings.supported_content_types:
        raise UnsupportedFileError(
            f"Unsupported file type '{content_type}'. Supported types: PDF, DOCX, PNG, JPEG."
        )

    if content_type == "application/pdf":
        result = classify_and_extract_pdf(file_bytes, vision, max_pages=settings.max_pages)
    elif content_type == _DOCX_MIME:
        result = extract_docx(file_bytes)
    elif content_type in ("image/png", "image/jpeg"):
        result = extract_image(file_bytes, vision, max_dimension_px=settings.max_image_dimension_px)
    else:  # pragma: no cover - guarded above
        raise UnsupportedFileError(f"Unsupported file type '{content_type}'.")

    return content_type, result
