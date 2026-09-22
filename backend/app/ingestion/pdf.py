"""PDF ingestion. Classifies each PDF as native-text, scanned, or mixed,
and extracts accordingly (spec section 5). Uses pypdf for native text with
deterministic heading heuristics, falling back to page rasterization + the
vision provider for pages with no extractable text.
"""
from __future__ import annotations

import io
from typing import List

from pypdf import PdfReader

from app.models.schemas import BlockType, DocumentKind, ExtractionResult, LayoutBlock, PageResult
from app.vision.provider import VisionProvider

MIN_CHARS_FOR_NATIVE_PAGE = 20


def _heading_heuristic_blocks(text: str, page_num: int) -> List[LayoutBlock]:
    """Deterministic (non-LLM) layout tagging for native text: short,
    title-cased / all-caps lines are treated as headings; lines starting
    with bullet markers or digits+period as list items."""
    blocks: List[LayoutBlock] = []
    for i, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line:
            continue
        block_type = BlockType.PARAGRAPH
        if len(line) <= 60 and (line.isupper() or line.istitle()) and not line.endswith((".", ",")):
            block_type = BlockType.HEADING
        elif line[0] in "-*\u2022":
            block_type = BlockType.BULLET
        elif len(line) > 2 and line[0].isdigit() and line[1] in ".)":
            block_type = BlockType.NUMBERED_ITEM
        blocks.append(LayoutBlock(page=page_num, block_type=block_type, text=line, order=i, source="native_pdf"))
    return blocks


def classify_and_extract_pdf(file_bytes: bytes, vision: VisionProvider, max_pages: int) -> ExtractionResult:
    warnings: List[str] = []
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
    except Exception as exc:
        return ExtractionResult(
            document_kind=DocumentKind.UNKNOWN,
            pages=[],
            warnings=[f"Could not open PDF: could not parse file structure ({type(exc).__name__})."],
        )

    num_pages = len(reader.pages)
    if num_pages == 0:
        return ExtractionResult(document_kind=DocumentKind.UNKNOWN, pages=[], warnings=["PDF has no pages."])
    if num_pages > max_pages:
        warnings.append(f"PDF has {num_pages} pages; only the first {max_pages} will be processed.")
        num_pages = max_pages

    pages: List[PageResult] = []
    native_page_count = 0
    scanned_page_count = 0

    for idx in range(num_pages):
        page = reader.pages[idx]
        page_num = idx + 1
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""

        if len(text) >= MIN_CHARS_FOR_NATIVE_PAGE:
            native_page_count += 1
            blocks = _heading_heuristic_blocks(text, page_num)
            pages.append(PageResult(page=page_num, blocks=blocks, raw_text=text))
        else:
            scanned_page_count += 1
            try:
                image_bytes = _render_page_to_png(file_bytes, idx)
            except Exception as exc:
                warnings.append(f"Page {page_num}: could not rasterize page for OCR ({type(exc).__name__}).")
                pages.append(PageResult(page=page_num, blocks=[], raw_text=""))
                continue

            vision_result = vision.extract_document_blocks(image_bytes, page_num=page_num)
            pages.append(PageResult(page=page_num, blocks=vision_result.blocks, raw_text=vision_result.raw_text))
            if vision_result.low_confidence:
                warnings.append(f"Page {page_num}: scanned content required OCR; some text may need review.")

    if native_page_count and scanned_page_count:
        kind = DocumentKind.PDF_MIXED
    elif scanned_page_count:
        kind = DocumentKind.PDF_SCANNED
    else:
        kind = DocumentKind.PDF_NATIVE

    result = ExtractionResult(document_kind=kind, pages=pages, warnings=warnings)
    if result.is_empty():
        result.warnings.append("No text could be extracted from this PDF (native or OCR).")
    return result


def _render_page_to_png(file_bytes: bytes, page_index: int) -> bytes:
    """Rasterize a single PDF page to PNG bytes using PyMuPDF (fitz), which
    has no external system dependency (unlike poppler/pdf2image)."""
    import fitz  # PyMuPDF

    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        page = doc[page_index]
        pix = page.get_pixmap(dpi=200)
        return pix.tobytes("png")
    finally:
        doc.close()
