"""Local file system implementation of the file repository port."""

from __future__ import annotations

import shutil
from pathlib import Path
import tempfile
import os

from application.ports.file_repository import FileRepository
from config.settings import Settings
from domain.models import StoredDocument, UploadFailure, UploadedFilePayload


class LocalFileRepository(FileRepository):
    """Persists uploaded files to the local file system."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Track ephemeral temp directories created for uploads so they can be
        # cleaned up later by `cleanup()`.
        self._ephemeral_dirs: list[str] = []

    def save_uploads(
        self, files: list[UploadedFilePayload]
    ) -> tuple[list[StoredDocument], list[UploadFailure]]:
        # Choose storage mode depending on settings.ephemeral_uploads.
        if self._settings.ephemeral_uploads:
            # Create a temporary directory for this batch of uploads.
            base_dir = tempfile.mkdtemp(prefix="docpilot_upload_")
            uploads_dir = Path(base_dir)
            # remember for later cleanup
            self._ephemeral_dirs.append(base_dir)
        else:
            uploads_dir = self._settings.uploads_dir
            uploads_dir.mkdir(parents=True, exist_ok=True)

        stored: list[StoredDocument] = []
        failures: list[UploadFailure] = []

        for file in files:
            extension = Path(file.filename).suffix.lower()
            if extension not in self._settings.supported_formats:
                failures.append(
                    UploadFailure(
                        filename=file.filename,
                        reason=f"Unsupported file type: {extension}",
                    )
                )
                continue

            size_mb = len(file.data) / (1024 * 1024)
            if size_mb > self._settings.max_file_size_mb:
                failures.append(
                    UploadFailure(
                        filename=file.filename,
                        reason=(
                            f"File too large: {size_mb:.2f} MB "
                            f"(max {self._settings.max_file_size_mb} MB)"
                        ),
                    )
                )
                continue

            # If ephemeral uploads are used we still write to disk, but inside
            # a temporary directory that will be removed on cleanup(). This
            # keeps compatibility with parsers that require a filesystem path.
            destination = uploads_dir / file.filename
            try:
                with open(destination, "wb") as handle:
                    handle.write(file.data)
                stored.append(StoredDocument(filename=file.filename, path=str(destination)))
            except Exception as exc:  # pragma: no cover - rare IO failure
                failures.append(
                    UploadFailure(
                        filename=file.filename,
                        reason=str(exc),
                    )
                )

        return stored, failures

    def list_uploads(self) -> list[StoredDocument]:
        uploads: list[StoredDocument] = []
        if self._settings.ephemeral_uploads:
            # Aggregate files from ephemeral dirs
            for base in list(self._ephemeral_dirs):
                p = Path(base)
                if not p.exists():
                    continue
                for path in p.glob("*.*"):
                    if path.is_file():
                        uploads.append(StoredDocument(filename=path.name, path=str(path)))
        else:
            uploads_dir = self._settings.uploads_dir
            uploads_dir.mkdir(parents=True, exist_ok=True)
            for path in uploads_dir.glob("*.*"):
                if path.is_file():
                    uploads.append(StoredDocument(filename=path.name, path=str(path)))
        return uploads

    def cleanup(self) -> None:
        # Remove ephemeral directories if any were created.
        if self._settings.ephemeral_uploads:
            for base in list(self._ephemeral_dirs):
                try:
                    if os.path.exists(base):
                        shutil.rmtree(base)
                except Exception:
                    # best effort cleanup
                    pass
            self._ephemeral_dirs = []
        else:
            uploads_dir = self._settings.uploads_dir
            if uploads_dir.exists():
                shutil.rmtree(uploads_dir)
            uploads_dir.mkdir(parents=True, exist_ok=True)
