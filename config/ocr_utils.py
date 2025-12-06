"""Utilities to detect OCR backend availability across platforms.

This helper provides a lightweight runtime check used by the Docling
integration to decide whether OCR can actually be performed on the
current host (for example, verifying presence of the `tesseract` binary
on Linux). The goal is to make behavior consistent across macOS and
Linux by automatically detecting capabilities and falling back safely.
"""
from __future__ import annotations

import shutil
import sys
import logging

logger = logging.getLogger(__name__)


def is_ocr_available() -> bool:
    """Return True if a supported OCR backend appears to be available.

    - On macOS we assume native OCR (OCRMac/MLX) is available when
      the environment supports it (docling/MLX is typically installed
      into the virtual env). We conservatively return True for macOS
      to avoid disabling OCR unnecessarily.
    - On other platforms (Linux) we check for a local OCR binary such
      as `tesseract` on PATH.
    """
    if sys.platform == "darwin":
        # macOS: assume native OCR backend (OCRMac/MLX) is available if
        # Docling/MLX are installed. We avoid doing heavy runtime checks
        # here and instead let Docling surface errors if MLX isn't present.
        logger.debug("Platform is macOS (darwin) — assuming OCR backend may be available")
        return True

    # For non-macOS platforms, require a well-known OCR binary (tesseract)
    # to be present on PATH so that Docling can rely on it.
    tesseract_path = shutil.which("tesseract")
    if tesseract_path:
        logger.debug("Found tesseract OCR binary at %s", tesseract_path)
        return True

    logger.debug("No supported OCR backend found (tesseract not on PATH)")
    return False


def is_macos() -> bool:
    """Return True when running on macOS (darwin).

    Small helper used across the codebase to keep platform checks
    centralized and easy to audit / change.
    """
    return sys.platform == "darwin"
