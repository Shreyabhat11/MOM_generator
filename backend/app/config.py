"""Environment-driven configuration. Nothing here is hard-coded; see
.env.example for the full list of variables. Settings are read fresh on
each `Settings()` construction (via default_factory) so tests can
monkeypatch env vars and call `get_settings.cache_clear()`."""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import BaseModel, Field


class Settings(BaseModel):
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or None)
    model_name: str = Field(default_factory=lambda: os.getenv("MODEL_NAME", "gemini-2.5-flash"))
    max_file_size_mb: int = Field(default_factory=lambda: int(os.getenv("MAX_FILE_SIZE_MB", "25")))
    max_pages: int = Field(default_factory=lambda: int(os.getenv("MAX_PAGES", "40")))
    max_image_dimension_px: int = Field(default_factory=lambda: int(os.getenv("MAX_IMAGE_DIMENSION_PX", "6000")))
    storage_dir: str = Field(default_factory=lambda: os.getenv("STORAGE_DIR", "/tmp/mom_generator"))
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    cors_origins: List[str] = Field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost:5500,http://127.0.0.1:5500"
        ).split(",")
    )

    supported_content_types: tuple = (
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/png",
        "image/jpeg",
    )

    @property
    def use_mock_vision(self) -> bool:
        forced = os.getenv("USE_MOCK_VISION", "").lower() in ("1", "true", "yes")
        return forced or not self.gemini_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
