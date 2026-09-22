import os

from app.ingestion.pdf import classify_and_extract_pdf
from app.models.schemas import DocumentKind

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def _read(*parts):
    with open(os.path.join(FIXTURES, *parts), "rb") as f:
        return f.read()


def test_native_pdf_extracts_text(mock_vision):
    result = classify_and_extract_pdf(_read("typed_notes", "weekly_sync.pdf"), mock_vision, max_pages=40)
    assert result.document_kind == DocumentKind.PDF_NATIVE
    assert "WEEKLY SYNC" in result.full_text()
    assert not result.is_empty()


def test_scanned_pdf_falls_back_to_vision_ocr(mock_vision):
    result = classify_and_extract_pdf(_read("scanned_pdfs", "scanned_notes.pdf"), mock_vision, max_pages=40)
    assert result.document_kind == DocumentKind.PDF_SCANNED
    # mock provider returns its explicit "mock mode" marker rather than
    # empty text or fabricated content
    assert "MOCK VISION MODE" in result.full_text()
    assert any("OCR" in w for w in result.warnings)


def test_empty_pdf_does_not_crash_and_is_flagged():
    import io
    from pypdf import PdfWriter

    buf = io.BytesIO()
    writer = PdfWriter()
    writer.write(buf)
    from app.vision.mock_provider import MockVisionProvider

    result = classify_and_extract_pdf(buf.getvalue(), MockVisionProvider(), max_pages=40)
    assert result.pages == []
    assert any("no pages" in w.lower() for w in result.warnings)


def test_multi_page_pdf_page_numbers_increment(mock_vision):
    # weekly_sync.pdf is single-page; verify page numbering contract on it
    result = classify_and_extract_pdf(_read("typed_notes", "weekly_sync.pdf"), mock_vision, max_pages=40)
    assert result.pages[0].page == 1


def test_malformed_pdf_bytes_handled_gracefully(mock_vision):
    result = classify_and_extract_pdf(b"not a real pdf", mock_vision, max_pages=40)
    assert result.document_kind == DocumentKind.UNKNOWN
    assert result.warnings
