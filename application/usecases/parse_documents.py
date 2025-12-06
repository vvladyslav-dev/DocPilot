"""Use case for parsing stored documents."""

from __future__ import annotations

from dataclasses import dataclass

from dependency_injector.wiring import Provide, inject
from mediatr import Mediator, GenericQuery
from pydantic import BaseModel

from application.ports.document_parser import DocumentParser
from application.ports.usecase import UseCase
from config.container import Container
from domain.models import ParsedDocument, StoredDocument


@dataclass
class ParseDocumentsRequest(GenericQuery["ParseDocumentsResponse"]):
    documents: list[StoredDocument]
    use_tables: bool = True
    use_ocr: bool = True
    pipeline: str | None = None


class ParseDocumentsResponse(BaseModel):
    documents: list[ParsedDocument]


@Mediator.handler
class ParseDocumentsUseCase(
    UseCase[ParseDocumentsRequest, ParseDocumentsResponse]
):
    @inject
    def __init__(
        self,
        document_parser: DocumentParser = Provide[Container.document_parser],
    ) -> None:
        self._document_parser = document_parser

    async def handle(self, request: ParseDocumentsRequest) -> ParseDocumentsResponse:
        file_paths = [doc.path for doc in request.documents]
        parsed_documents = self._document_parser.parse_many(
            file_paths,
            use_tables=request.use_tables,
            use_ocr=request.use_ocr,
            pipeline=request.pipeline,
        )
        return ParseDocumentsResponse(documents=parsed_documents)
