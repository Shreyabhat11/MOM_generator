"""Spec section 29: don't persist uploaded documents longer than needed."""
import os


def test_source_file_deleted_immediately_after_ingestion(client):
    fixtures = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")
    with open(os.path.join(fixtures, "typed_notes", "weekly_sync.docx"), "rb") as f:
        file_bytes = f.read()

    resp = client.post(
        "/documents",
        files={"file": ("weekly_sync.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    doc_id = resp.json()["id"]

    from app.storage import get_store

    state = get_store().get(doc_id)
    assert not os.path.exists(state.file_path), "raw uploaded file should be deleted right after extraction"

    # The rest of the pipeline must still work from the derived
    # ExtractionResult - it must never need to re-read the original file.
    process = client.post(f"/documents/{doc_id}/process")
    assert process.status_code == 200
