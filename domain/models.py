"""Domain models used across the application layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class UploadedFilePayload(BaseModel):
    """In-memory representation of an uploaded file."""

    filename: str
    data: bytes
    content_type: str | None = None


class StoredDocument(BaseModel):
    """Represents a file persisted to storage."""

    filename: str
    path: str


class UploadFailure(BaseModel):
    """Information about a file that failed validation or storage."""

    filename: str
    reason: str


class ParsedDocument(BaseModel):
    """Outcome of parsing a document into Markdown text."""

    filename: str
    status: Literal["success", "failed"]
    markdown: str | None = None
    error: str | None = None


class ExtractionInstruction(BaseModel):
    """Instruction provided by the user for LLM extraction."""

    text: str


class ExtractionResult(BaseModel):
    """Tabular data returned by an LLM extraction."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not self.rows
