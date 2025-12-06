"""Dependency injection container configuration."""

from __future__ import annotations

from dependency_injector import containers, providers

from config.settings import Settings
from infrastructure.files.local_file_repository import LocalFileRepository
from infrastructure.llm.gemini_llm_repository import GeminiLLMRepository
from infrastructure.parsers.docling_parser import DoclingDocumentParser


class Container(containers.DeclarativeContainer):
    """Application service container."""

    wiring_config = containers.WiringConfiguration(packages=["application.usecases"])

    settings = providers.Singleton(Settings)
    file_repository = providers.Singleton(LocalFileRepository, settings=settings)
    document_parser = providers.Singleton(DoclingDocumentParser, settings=settings)
    llm_repository = providers.Singleton(GeminiLLMRepository, settings=settings)
