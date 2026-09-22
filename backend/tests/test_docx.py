import os

from app.ingestion.docx import extract_docx
from app.models.schemas import BlockType

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def _read(*parts):
    with open(os.path.join(FIXTURES, *parts), "rb") as f:
        return f.read()


def test_docx_preserves_heading_bullets_and_table():
    result = extract_docx(_read("typed_notes", "weekly_sync.docx"))
    types = [b.block_type for p in result.pages for b in p.blocks]
    assert BlockType.HEADING in types
    assert BlockType.BULLET in types
    assert BlockType.TABLE in types


def test_docx_table_rows_are_structured():
    result = extract_docx(_read("typed_notes", "weekly_sync.docx"))
    table_blocks = [b for p in result.pages for b in p.blocks if b.block_type == BlockType.TABLE]
    assert len(table_blocks) == 1
    rows = table_blocks[0].table.rows
    assert rows[0] == ["Action", "Owner", "Deadline"]
    assert rows[1] == ["Prepare report", "Raj", "Friday"]


def test_docx_does_not_flatten_structure_into_single_blob():
    result = extract_docx(_read("typed_notes", "weekly_sync.docx"))
    # Old prototype behavior would have been a single joined string; verify
    # we get multiple distinct ordered blocks instead.
    assert len(result.pages[0].blocks) > 3


def test_malformed_docx_bytes_handled_gracefully():
    result = extract_docx(b"not a real docx")
    assert result.warnings
    assert result.pages == []
