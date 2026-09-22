"""HTTP API surface (spec section 3). Kept thin - all real logic lives in
the ingestion/extraction/validation/generation/rendering modules; this file
only does request/response plumbing, status-stage bookkeeping, and
translating internal exceptions into clean HTTP errors (spec section 23:
never expose raw stack traces to end users)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.config import get_settings
from app.extraction.meeting import ExtractionFailedError, extract_meeting_minutes
from app.extraction.normalization import normalize_meeting_minutes
from app.generation.mom import generate_mom
from app.ingestion.router import EmptyFileError, UnsupportedFileError, extract
from app.logging_conf import log_stage
from app.models.schemas import ProcessingStage
from app.rendering.docx_render import render_docx
from app.rendering.pdf_render import render_pdf
from app.storage import get_store
from app.validation.grounding import check_grounding
from app.validation.schema_validate import validate_structure
from app.vision.factory import get_vision_provider

logger = logging.getLogger("mom_generator")
router = APIRouter(prefix="/documents")


@router.post("")
async def create_document(file: UploadFile = File(...)):
    file_bytes = await file.read()
    settings = get_settings()
    try:
        content_type, extraction = extract(
            file_bytes, file.filename or "upload", file.content_type or "", settings, get_vision_provider()
        )
    except EmptyFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except Exception:
        logger.exception("document_ingestion_failed")
        raise HTTPException(status_code=500, detail="Could not process this file. Please try again or use a different file.")

    store = get_store()
    record = store.create(file.filename or "upload", content_type, file_bytes)
    state = store.get(record.id)
    state.extraction = extraction
    state.record.warnings = extraction.warnings
    store.update_stage(record.id, ProcessingStage.CLASSIFIED)

    # Spec section 29 (privacy): the raw upload is only needed to run
    # extraction, which has already happened by this point. Delete it
    # immediately rather than keeping it for the lifetime of the session -
    # everything downstream (process/generate/render/download) works from
    # the derived ExtractionResult/MeetingMinutes, never the original bytes.
    store.delete_source_file(record.id)

    return {
        "id": record.id,
        "filename": record.filename,
        "content_type": content_type,
        "document_kind": extraction.document_kind,
        "stage": state.record.stage,
        "warnings": extraction.warnings,
    }


@router.get("/{doc_id}/status")
def get_status(doc_id: str):
    state = get_store().get(doc_id)
    if not state:
        raise HTTPException(status_code=404, detail="Document not found.")
    return {"id": doc_id, "stage": state.record.stage, "error": state.record.error, "warnings": state.record.warnings}


@router.get("/{doc_id}/extraction")
def get_extraction(doc_id: str):
    state = get_store().get(doc_id)
    if not state or not state.extraction:
        raise HTTPException(status_code=404, detail="No extraction available for this document yet.")
    return state.extraction


@router.post("/{doc_id}/process")
def process_document(doc_id: str):
    """Runs structured extraction (text/layout -> MeetingMinutes) and
    deterministic + grounding validation. Generation (prose) is a separate
    step (`/generate`) so a caller can inspect/edit structured facts first."""
    store = get_store()
    state = store.get(doc_id)
    if not state or not state.extraction:
        raise HTTPException(status_code=404, detail="Document not found or not yet ingested.")

    try:
        with log_stage("extraction", document_id=doc_id):
            minutes = extract_meeting_minutes(state.extraction, get_vision_provider())
            minutes = normalize_meeting_minutes(minutes)
    except ExtractionFailedError as exc:
        store.update_stage(doc_id, ProcessingStage.FAILED, error=str(exc))
        raise HTTPException(status_code=502, detail="The extraction model returned an invalid response. Please try again.")
    except Exception:
        logger.exception("extraction_failed", extra={"document_id": doc_id})
        store.update_stage(doc_id, ProcessingStage.FAILED, error="internal_error")
        raise HTTPException(status_code=500, detail="Extraction failed unexpectedly.")

    structural_issues = validate_structure(minutes)
    grounding_report = check_grounding(minutes, state.extraction.full_text())
    grounding_report.issues = structural_issues + grounding_report.issues

    state.minutes = minutes
    state.validation = grounding_report
    store.update_stage(doc_id, ProcessingStage.STRUCTURED)

    return {
        "id": doc_id,
        "stage": state.record.stage,
        "meeting_minutes": minutes,
        "validation": grounding_report,
    }


@router.post("/{doc_id}/generate")
def generate(doc_id: str):
    store = get_store()
    state = store.get(doc_id)
    if not state or not state.minutes:
        raise HTTPException(status_code=404, detail="Document has not been processed yet. Call /process first.")

    try:
        with log_stage("generation", document_id=doc_id):
            minutes, gen_report = generate_mom(state.minutes, state.extraction.full_text(), get_vision_provider())
    except Exception:
        logger.exception("generation_failed", extra={"document_id": doc_id})
        store.update_stage(doc_id, ProcessingStage.FAILED, error="internal_error")
        raise HTTPException(status_code=500, detail="Generation failed unexpectedly.")

    state.minutes = minutes
    combined_issues = (state.validation.issues if state.validation else []) + gen_report.issues
    combined_unsupported = (state.validation.unsupported_claims if state.validation else []) + gen_report.unsupported_claims
    state.validation = gen_report.model_copy(update={"issues": combined_issues, "unsupported_claims": combined_unsupported})
    store.update_stage(doc_id, ProcessingStage.GENERATED)

    return {"id": doc_id, "stage": state.record.stage, "meeting_minutes": minutes, "validation": state.validation}


@router.get("/{doc_id}/mom")
def get_mom(doc_id: str):
    state = get_store().get(doc_id)
    if not state or not state.minutes:
        raise HTTPException(status_code=404, detail="MoM not generated yet.")
    return {"id": doc_id, "meeting_minutes": state.minutes, "validation": state.validation}


@router.put("/{doc_id}/mom")
def update_mom(doc_id: str, meeting_minutes: dict):
    """Human-review edits (spec section 17). The edited version becomes the
    new source of truth for export - re-validated structurally, but we do
    not re-run grounding against the original document, since the human
    reviewer is the authority once they've edited a field."""
    from app.models.schemas import MeetingMinutes

    store = get_store()
    state = store.get(doc_id)
    if not state:
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        state.minutes = MeetingMinutes(**meeting_minutes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Minutes of Meeting payload: {exc}")
    return {"id": doc_id, "meeting_minutes": state.minutes}


@router.get("/{doc_id}/download/docx")
def download_docx(doc_id: str):
    state = get_store().get(doc_id)
    if not state or not state.minutes:
        raise HTTPException(status_code=404, detail="MoM not generated yet.")
    content = render_docx(state.minutes)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="minutes_of_meeting.docx"'},
    )


@router.get("/{doc_id}/download/pdf")
def download_pdf(doc_id: str):
    state = get_store().get(doc_id)
    if not state or not state.minutes:
        raise HTTPException(status_code=404, detail="MoM not generated yet.")
    content = render_pdf(state.minutes)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="minutes_of_meeting.pdf"'},
    )
