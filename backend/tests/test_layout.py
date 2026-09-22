import os

from app.ingestion.pdf import classify_and_extract_pdf
from app.models.schemas import BlockType

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def _read(*parts):
    with open(os.path.join(FIXTURES, *parts), "rb") as f:
        return f.read()


def test_native_pdf_heading_heuristic_detects_allcaps_heading(mock_vision):
    result = classify_and_extract_pdf(_read("typed_notes", "weekly_sync.pdf"), mock_vision, max_pages=40)
    blocks = result.pages[0].blocks
    assert any(b.block_type == BlockType.HEADING and "WEEKLY SYNC" in b.text for b in blocks)


def test_native_pdf_bullet_detection(mock_vision):
    result = classify_and_extract_pdf(_read("typed_notes", "weekly_sync.pdf"), mock_vision, max_pages=40)
    blocks = result.pages[0].blocks
    assert any(b.block_type == BlockType.BULLET for b in blocks)


def test_blocks_preserve_order():
    from app.ingestion.docx import extract_docx

    result = extract_docx(_read("typed_notes", "weekly_sync.docx"))
    orders = [b.order for b in result.pages[0].blocks]
    assert orders == sorted(orders)
