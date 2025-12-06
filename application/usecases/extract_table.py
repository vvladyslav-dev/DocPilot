"""Use case for extracting structured data via LLM."""

from __future__ import annotations

from dataclasses import dataclass

from dependency_injector.wiring import Provide, inject
from mediatr import Mediator, GenericQuery
from pydantic import BaseModel

from application.ports.llm_repository import LLMRepository
from application.ports.usecase import UseCase
from config.container import Container
from domain.models import ExtractionResult, ParsedDocument


@dataclass
class ExtractTableRequest(GenericQuery["ExtractTableResponse"]):
    documents: list[ParsedDocument]
    instruction: str
    api_key: str | None = None
    model_name: str | None = None


class ExtractTableResponse(BaseModel):
    result: ExtractionResult


@Mediator.handler
class ExtractTableUseCase(
    UseCase[ExtractTableRequest, ExtractTableResponse]
):
    @inject
    def __init__(
        self,
        llm_repository: LLMRepository = Provide[Container.llm_repository],
    ) -> None:
        self._llm_repository = llm_repository

    async def handle(self, request: ExtractTableRequest) -> ExtractTableResponse:
        instruction = (request.instruction or "").strip()
        if not instruction:
            raise ValueError("Instruction must be provided for LLM extraction.")

        result = self._llm_repository.extract_table(
            request.documents,
            instruction=instruction,
            api_key=request.api_key,
            model_name=request.model_name,
        )
        return ExtractTableResponse(result=result)
