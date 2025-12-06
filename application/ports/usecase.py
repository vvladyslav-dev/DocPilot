"""Base interface for all use cases."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

RequestT = TypeVar("RequestT")
ResponseT = TypeVar("ResponseT")


class UseCase(ABC, Generic[RequestT, ResponseT]):
    """Abstract use case contract."""

    @abstractmethod
    async def handle(self, request: RequestT) -> ResponseT:
        """Execute the use case."""

