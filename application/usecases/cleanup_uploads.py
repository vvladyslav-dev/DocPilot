"""Use case for clearing uploaded files."""

from __future__ import annotations

from dataclasses import dataclass

from dependency_injector.wiring import Provide, inject
from mediatr import Mediator, GenericQuery
from pydantic import BaseModel

from application.ports.file_repository import FileRepository
from application.ports.usecase import UseCase
from config.container import Container


@dataclass
class CleanupUploadsRequest(GenericQuery["CleanupUploadsResponse"]):
    pass


class CleanupUploadsResponse(BaseModel):
    success: bool


@Mediator.handler
class CleanupUploadsUseCase(
    UseCase[CleanupUploadsRequest, CleanupUploadsResponse]
):
    @inject
    def __init__(
        self,
        file_repository: FileRepository = Provide[Container.file_repository],
    ) -> None:
        self._file_repository = file_repository

    async def handle(self, request: CleanupUploadsRequest) -> CleanupUploadsResponse:
        self._file_repository.cleanup()
        return CleanupUploadsResponse(success=True)
