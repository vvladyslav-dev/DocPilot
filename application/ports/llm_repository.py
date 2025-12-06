"""Port for LLM-based table extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import ExtractionResult, ParsedDocument


class LLMRepository(ABC):
    """Interface for invoking an LLM to extract structured data."""

    @abstractmethod
    def extract_table(
        self,
        documents: list[ParsedDocument],
        *,
        instruction: str,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> ExtractionResult:
        """Extract tabular data for provided documents."""

