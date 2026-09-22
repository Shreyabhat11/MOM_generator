import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("USE_MOCK_VISION", "true")
os.environ.setdefault("STORAGE_DIR", "/tmp/mom_generator_test")

import pytest

from app.config import get_settings
from app.vision.factory import get_vision_provider, reset_vision_provider_cache
from app.vision.mock_provider import MockVisionProvider


@pytest.fixture(autouse=True)
def _reset_caches():
    get_settings.cache_clear()
    reset_vision_provider_cache()
    yield
    get_settings.cache_clear()
    reset_vision_provider_cache()


@pytest.fixture
def mock_vision() -> MockVisionProvider:
    return MockVisionProvider()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
