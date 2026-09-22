"""Image preprocessing for handwritten/photographed notes (spec section 7).

Key principle: we never destroy the original image. We compute a
*preprocessed variant* (deskewed, denoised, contrast-enhanced) for cases
where it helps, but always keep the original bytes available too, and pass
both forward so the vision model can use whichever is more legible.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps


@dataclass
class PreprocessedImage:
    original_png: bytes
    enhanced_png: bytes
    rotation_applied_deg: float
    warnings: list[str]


def _to_cv2(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes (unsupported or corrupted image).")
    return img


def _correct_exif_orientation(image_bytes: bytes) -> bytes:
    """Respect the EXIF orientation tag from phone photos before any other
    processing, otherwise deskewing/analysis operates on a rotated frame."""
    try:
        with Image.open(__import__("io").BytesIO(image_bytes)) as im:
            im = ImageOps.exif_transpose(im)
            buf = __import__("io").BytesIO()
            im.convert("RGB").save(buf, format="PNG")
            return buf.getvalue()
    except Exception as exc:
        raise ValueError(f"Could not decode image bytes (unsupported or corrupted image): {exc}") from exc


def _estimate_skew_angle(gray: np.ndarray) -> float:
    """Estimate skew via the minimum-area bounding rectangle of dark pixels.
    Conservative: only returns non-trivial angles (a few degrees), since
    aggressive "correction" on already-straight text does more harm than
    good."""
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh > 0))
    if coords.shape[0] < 20:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
    if abs(angle) > 15:
        return 0.0  # implausible; likely a bad estimate on sparse content
    return float(angle)


def _rotate(img: np.ndarray, angle_deg: float) -> np.ndarray:
    if abs(angle_deg) < 0.3:
        return img
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_image(
    image_bytes: bytes, max_dimension_px: int = 6000
) -> PreprocessedImage:
    warnings: list[str] = []

    oriented_bytes = _correct_exif_orientation(image_bytes)
    img = _to_cv2(oriented_bytes)

    h, w = img.shape[:2]
    if max(h, w) > max_dimension_px:
        warnings.append(f"Image exceeds {max_dimension_px}px on its longest side; downscaling.")
        scale = max_dimension_px / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    original_png = cv2.imencode(".png", img)[1].tobytes()

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    angle = _estimate_skew_angle(gray)
    rotated = _rotate(img, angle)
    rotated_gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)

    # CLAHE (adaptive local contrast) handles uneven lighting from phone
    # photos far better than a single global threshold.
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(rotated_gray)

    denoised = cv2.fastNlMeansDenoising(contrast_enhanced, h=10)

    # Adaptive threshold as an *additional* variant, not a destructive
    # in-place replacement - many handwriting samples read better as
    # grayscale than binarized.
    adaptive = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
    )
    # Blend: prefer the denoised grayscale (keeps stroke gradients visible
    # for handwriting) over hard binarization, which is only used to flag
    # very low-contrast originals in `warnings`.
    if np.std(rotated_gray) < 20:
        warnings.append("Very low contrast detected in source image; OCR/handwriting quality may be reduced.")

    enhanced_bgr = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
    enhanced_png = cv2.imencode(".png", enhanced_bgr)[1].tobytes()

    return PreprocessedImage(
        original_png=original_png,
        enhanced_png=enhanced_png,
        rotation_applied_deg=angle,
        warnings=warnings,
    )
