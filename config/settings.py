"""Application configuration module providing typed settings."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv


_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env", override=False)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_list(name: str, default: Tuple[str, ...]) -> Tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    items = [item.strip() for item in value.split(",") if item.strip()]
    return tuple(items) if items else default


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value else default


@dataclass(slots=True)
class Settings:
    """Application-wide configuration values."""

    project_root: Path = field(default_factory=lambda: _PROJECT_ROOT)
    data_dir: Path = field(init=False)
    temp_dir: Path = field(init=False)
    uploads_dir: Path = field(init=False)
    exports_dir: Path = field(init=False)

    supported_formats: Tuple[str, ...] = field(
        default_factory=lambda: _env_list("SUPPORTED_FORMATS", (".pdf",))
    )
    export_formats: Tuple[str, ...] = ("csv", "xlsx")
    csv_encoding: str = "utf-8"

    max_file_size_mb: int = field(default_factory=lambda: _env_int("MAX_FILE_SIZE_MB", 50))
    max_files_upload: int = field(default_factory=lambda: _env_int("MAX_FILES_UPLOAD", 10))

    docling_use_tables: bool = True
    docling_use_ocr: bool = True
    docling_pipeline: str = field(default_factory=lambda: _env_str("DOCLING_PIPELINE", "standard"))

    gemini_api_key: str | None = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    gemini_model: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    # Ephemeral upload settings: when enabled uploads are stored in temporary
    # directories that are cleaned up on `cleanup()` instead of persisted in
    # the project `temp/uploads` folder.
    ephemeral_uploads: bool = field(default_factory=lambda: os.getenv("EPHEMERAL_UPLOADS", "true").lower() in ("1", "true", "yes"))
    ephemeral_threshold_mb: int = field(default_factory=lambda: _env_int("EPHEMERAL_THRESHOLD_MB", 20))

    def __post_init__(self) -> None:
        self.data_dir = self.project_root / "data"
        self.temp_dir = self.project_root / "temp"
        self.uploads_dir = self.temp_dir / "uploads"
        self.exports_dir = self.temp_dir / "exports"
        self.ensure_directories()

    def ensure_directories(self) -> None:
        for directory in (self.data_dir, self.temp_dir, self.uploads_dir, self.exports_dir):
            directory.mkdir(parents=True, exist_ok=True)

