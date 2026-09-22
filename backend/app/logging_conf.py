"""Structured (JSON) logging. Deliberately never logs document contents -
only stage names, IDs, durations and status (see spec section 30)."""
from __future__ import annotations

import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Optional

from app.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for key in ("document_id", "stage", "duration_ms", "status"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload)


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger("mom_generator")
    root.setLevel(settings.log_level)
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)


logger = logging.getLogger("mom_generator")


@contextmanager
def log_stage(stage: str, document_id: Optional[str] = None, **extra: Any):
    """Emits `<stage>_started` / `<stage>_completed` (or `_failed`) events
    with duration, without ever logging document text."""
    start = time.time()
    logger.info(f"{stage}_started", extra={"document_id": document_id, "stage": stage, "status": "started", **extra})
    try:
        yield
    except Exception:
        duration_ms = int((time.time() - start) * 1000)
        logger.exception(
            f"{stage}_failed",
            extra={"document_id": document_id, "stage": stage, "duration_ms": duration_ms, "status": "failed"},
        )
        raise
    else:
        duration_ms = int((time.time() - start) * 1000)
        logger.info(
            f"{stage}_completed",
            extra={"document_id": document_id, "stage": stage, "duration_ms": duration_ms, "status": "completed"},
        )
