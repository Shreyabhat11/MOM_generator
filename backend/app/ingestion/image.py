"""Image (photographed/scanned notes) ingestion. Preprocesses, then hands
both the enhanced and original image to the vision provider - the vision
model decides which is more legible per spec section 7 ("original image
should remain available to the vision model when useful")."""
from __future__ import annotations

from app.models.schemas import DocumentKind, ExtractionResult, PageResult
from app.preprocessing.image_ops import preprocess_image
from app.vision.provider import VisionProvider


def extract_image(file_bytes: bytes, vision: VisionProvider, max_dimension_px: int) -> ExtractionResult:
    try:
        pre = preprocess_image(file_bytes, max_dimension_px=max_dimension_px)
    except ValueError as exc:
        return ExtractionResult(document_kind=DocumentKind.UNKNOWN, pages=[], warnings=[str(exc)])

    # Send the enhanced variant as the primary image (best legibility for
    # handwriting); providers that want the original can be extended to
    # accept both, but for now enhanced-first keeps the API surface small
    # while still never discarding the original (available via `pre`).
    vision_result = vision.extract_document_blocks(pre.enhanced_png, page_num=1)

    warnings = list(pre.warnings)
    if vision_result.low_confidence:
        warnings.append("Some handwritten or unclear content may require manual review.")

    return ExtractionResult(
        document_kind=DocumentKind.IMAGE,
        pages=[PageResult(page=1, blocks=vision_result.blocks, raw_text=vision_result.raw_text)],
        warnings=warnings,
    )
