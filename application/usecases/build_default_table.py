"""Use case for building a default table when no LLM instruction is provided."""

from __future__ import annotations

from dataclasses import dataclass

from mediatr import Mediator, GenericQuery
from pydantic import BaseModel

from application.ports.usecase import UseCase
from domain.models import ExtractionResult, ParsedDocument


@dataclass
class BuildDefaultTableRequest(GenericQuery["BuildDefaultTableResponse"]):
    documents: list[ParsedDocument]
    snippet_length: int = 200


class BuildDefaultTableResponse(BaseModel):
    result: ExtractionResult


@Mediator.handler
class BuildDefaultTableUseCase(
    UseCase[BuildDefaultTableRequest, BuildDefaultTableResponse]
):
    async def handle(self, request: BuildDefaultTableRequest) -> BuildDefaultTableResponse:
        snippet_length = max(0, request.snippet_length)
        rows = []
        for document in request.documents:
            if document.status != "success" or not document.markdown:
                continue
            snippet = document.markdown[:snippet_length]
            if len(document.markdown) > snippet_length:
                snippet += "..."
            rows.append([document.filename, snippet, document.status])

        result = ExtractionResult(
            columns=["file", "snippet", "status"],
            rows=rows,
        )
        return BuildDefaultTableResponse(result=result)
