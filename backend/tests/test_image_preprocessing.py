import os

from app.preprocessing.image_ops import preprocess_image

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures")


def _read(*parts):
    with open(os.path.join(FIXTURES, *parts), "rb") as f:
        return f.read()


def test_clean_image_preprocesses_without_error():
    pre = preprocess_image(_read("typed_notes", "clean_note.png"))
    assert pre.original_png
    assert pre.enhanced_png
    assert abs(pre.rotation_applied_deg) < 2


def test_skewed_image_is_deskewed():
    pre = preprocess_image(_read("handwritten_notes", "skewed_note.png"))
    # We rotated the source by 8 degrees when generating the fixture;
    # expect the estimator to detect meaningful skew.
    assert abs(pre.rotation_applied_deg) > 1


def test_low_contrast_image_flags_warning():
    pre = preprocess_image(_read("handwritten_notes", "low_contrast_note.png"))
    assert any("contrast" in w.lower() for w in pre.warnings)


def test_original_bytes_are_preserved_not_destroyed():
    pre = preprocess_image(_read("typed_notes", "clean_note.png"))
    # original_png must decode back to a valid, non-trivial image
    import cv2
    import numpy as np

    arr = np.frombuffer(pre.original_png, dtype=np.uint8)
    decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape[0] > 0 and decoded.shape[1] > 0


def test_corrupted_image_bytes_raise_value_error():
    import pytest

    with pytest.raises(ValueError):
        preprocess_image(b"not an image")


def test_oversized_image_is_downscaled():
    pre = preprocess_image(_read("typed_notes", "clean_note.png"), max_dimension_px=100)
    assert any("downscal" in w.lower() for w in pre.warnings)
