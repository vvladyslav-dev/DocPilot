"""Port for parsing documents."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import ParsedDocument


class DocumentParser(ABC):
    """Interface for parsing persisted documents."""

    @abstractmethod
    def parse_many(
        self,
        file_paths: list[str],
        *,
        use_tables: bool = True,
        use_ocr: bool = True,
        pipeline: str | None = None,
    ) -> list[ParsedDocument]:
        """Parse provided documents and return structured results."""

