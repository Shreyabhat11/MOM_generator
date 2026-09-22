"""In-memory + temp-file document store.

Spec section 29 (security/privacy): uploaded documents are never persisted
beyond what's needed to complete processing. This store keeps the raw file
on disk under STORAGE_DIR only for the lifetime of the process (or until
`purge`/TTL cleanup runs) and keeps structured records in memory - nothing
is written to a database. For a real multi-instance deployment this would
be swapped for object storage + a DB, but for this project's scale an
in-process store is the right amount of complexity (spec section 37).
"""
from __future__ import annotations

import os
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional

from app.config import get_settings
from app.models.schemas import DocumentRecord, ExtractionResult, MeetingMinutes, ProcessingStage, ValidationReport


@dataclass
class _DocumentState:
    record: DocumentRecord
    file_path: str
    extraction: Optional[ExtractionResult] = None
    minutes: Optional[MeetingMinutes] = None
    validation: Optional[ValidationReport] = None
    docx_bytes: Optional[bytes] = None
    pdf_bytes: Optional[bytes] = None


class DocumentStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._docs: dict[str, _DocumentState] = {}
        os.makedirs(get_settings().storage_dir, exist_ok=True)

    def create(self, filename: str, content_type: str, file_bytes: bytes) -> DocumentRecord:
        doc_id = str(uuid.uuid4())
        settings = get_settings()
        path = os.path.join(settings.storage_dir, doc_id)
        with open(path, "wb") as f:
            f.write(file_bytes)
        record = DocumentRecord(id=doc_id, filename=filename, content_type=content_type)
        with self._lock:
            self._docs[doc_id] = _DocumentState(record=record, file_path=path)
        return record

    def get(self, doc_id: str) -> Optional[_DocumentState]:
        with self._lock:
            return self._docs.get(doc_id)

    def read_bytes(self, doc_id: str) -> Optional[bytes]:
        state = self.get(doc_id)
        if state is None or not os.path.exists(state.file_path):
            return None
        with open(state.file_path, "rb") as f:
            return f.read()

    def update_stage(self, doc_id: str, stage: ProcessingStage, error: Optional[str] = None) -> None:
        with self._lock:
            state = self._docs.get(doc_id)
            if state:
                state.record.stage = stage
                state.record.error = error

    def delete_source_file(self, doc_id: str) -> None:
        """Called once processing is fully complete: we don't need the raw
        upload anymore, only the derived structured/rendered artifacts."""
        state = self.get(doc_id)
        if state and os.path.exists(state.file_path):
            os.remove(state.file_path)


_store: DocumentStore | None = None


def get_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore()
    return _store
