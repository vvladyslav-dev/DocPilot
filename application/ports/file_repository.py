"""Port for working with uploaded files storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import StoredDocument, UploadFailure, UploadedFilePayload


class FileRepository(ABC):
    """Interface for persisting uploaded files."""

    @abstractmethod
    def save_uploads(
        self, files: list[UploadedFilePayload]
    ) -> tuple[list[StoredDocument], list[UploadFailure]]:
        """Persist uploaded files and return successes and failures."""

    @abstractmethod
    def list_uploads(self) -> list[StoredDocument]:
        """Return all stored uploads."""

    @abstractmethod
    def cleanup(self) -> None:
        """Remove uploaded files and re-create the storage directory."""

