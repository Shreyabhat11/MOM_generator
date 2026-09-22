"""Selects the vision provider based on configuration. This is the single
place that decides mock vs real - nothing else in the codebase should
branch on `use_mock_vision`."""
from __future__ import annotations

from app.config import get_settings
from app.vision.mock_provider import MockVisionProvider
from app.vision.provider import VisionProvider

_cached: VisionProvider | None = None


def get_vision_provider() -> VisionProvider:
    global _cached
    if _cached is not None:
        return _cached
    settings = get_settings()
    if settings.use_mock_vision:
        _cached = MockVisionProvider()
    else:
        from app.vision.gemini_provider import GeminiVisionProvider  # lazy import: avoid requiring google-genai in mock-only environments
        _cached = GeminiVisionProvider()
    return _cached


def reset_vision_provider_cache() -> None:
    global _cached
    _cached = None
