import io
import os

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def _read(*parts):
    with open(os.path.join(FIXTURES, *parts), "rb") as f:
        return f.read()


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_full_pipeline_happy_path(client):
    file_bytes = _read("typed_notes", "weekly_sync.docx")
    resp = client.post(
        "/documents",
        files={"file": ("weekly_sync.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert resp.status_code == 200
    doc_id = resp.json()["id"]

    status = client.get(f"/documents/{doc_id}/status")
    assert status.status_code == 200

    extraction = client.get(f"/documents/{doc_id}/extraction")
    assert extraction.status_code == 200

    process = client.post(f"/documents/{doc_id}/process")
    assert process.status_code == 200
    assert process.json()["stage"] == "structured"

    generate = client.post(f"/documents/{doc_id}/generate")
    assert generate.status_code == 200
    assert generate.json()["stage"] == "generated"

    mom = client.get(f"/documents/{doc_id}/mom")
    assert mom.status_code == 200

    docx_resp = client.get(f"/documents/{doc_id}/download/docx")
    assert docx_resp.status_code == 200
    assert docx_resp.headers["content-type"].startswith("application/vnd.openxmlformats")

    pdf_resp = client.get(f"/documents/{doc_id}/download/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"


def test_unsupported_file_type_returns_415(client):
    resp = client.post("/documents", files={"file": ("notes.exe", b"MZ\x90\x00fake binary", "application/octet-stream")})
    assert resp.status_code == 415


def test_empty_file_returns_400(client):
    resp = client.post("/documents", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert resp.status_code == 400


def test_process_before_upload_returns_404(client):
    resp = client.post("/documents/does-not-exist/process")
    assert resp.status_code == 404


def test_download_before_generate_returns_404(client):
    file_bytes = _read("typed_notes", "weekly_sync.docx")
    resp = client.post(
        "/documents",
        files={"file": ("weekly_sync.docx", file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    doc_id = resp.json()["id"]
    download = client.get(f"/documents/{doc_id}/download/docx")
    assert download.status_code == 404


def test_no_stack_trace_leaked_on_internal_error(client, monkeypatch):
    import app.api.documents as documents_module

    def boom(*args, **kwargs):
        raise RuntimeError("boom - simulated internal failure with sensitive detail")

    monkeypatch.setattr(documents_module, "extract", boom)
    resp = client.post("/documents", files={"file": ("weekly_sync.pdf", _read("typed_notes", "weekly_sync.pdf"), "application/pdf")})
    assert resp.status_code == 500
    assert "boom" not in resp.text
    assert "RuntimeError" not in resp.text
