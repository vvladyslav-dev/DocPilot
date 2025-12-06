"""Use case for storing uploaded files."""

from __future__ import annotations

from dataclasses import dataclass

from dependency_injector.wiring import Provide, inject
from mediatr import Mediator, GenericQuery
from pydantic import BaseModel

from application.ports.file_repository import FileRepository
from application.ports.usecase import UseCase
from config.container import Container
from domain.models import StoredDocument, UploadFailure, UploadedFilePayload


@dataclass
class SaveUploadedFilesRequest(GenericQuery["SaveUploadedFilesResponse"]):
    files: list[UploadedFilePayload]


class SaveUploadedFilesResponse(BaseModel):
    stored_documents: list[StoredDocument]
    failures: list[UploadFailure]


@Mediator.handler
class SaveUploadedFilesUseCase(
    UseCase[SaveUploadedFilesRequest, SaveUploadedFilesResponse]
):
    @inject
    def __init__(
        self,
        file_repository: FileRepository = Provide[Container.file_repository],
    ) -> None:
        self._file_repository = file_repository

    async def handle(self, request: SaveUploadedFilesRequest) -> SaveUploadedFilesResponse:
        stored, failures = self._file_repository.save_uploads(request.files)
        return SaveUploadedFilesResponse(stored_documents=stored, failures=failures)
