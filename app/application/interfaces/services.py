"""Puertos de los cuatro servicios. El orquestador no sabe que hablan HTTP."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class ExtractedText:
    filename: str
    text: str


@dataclass(frozen=True)
class StoredSummary:
    id: str
    original_filename: str
    summary_text: str
    created_at: str


@dataclass(frozen=True)
class ExportedDocument:
    filename: str
    content: bytes


class HealthCheckable(ABC):
    @abstractmethod
    async def is_healthy(self) -> bool: ...


class ExtractorClient(HealthCheckable):
    @abstractmethod
    async def extract(self, file: BinaryIO, filename: str) -> ExtractedText: ...


class SummarizerClient(HealthCheckable):
    @abstractmethod
    async def summarize(self, text: str) -> str:
        """Devuelve el resumen en Markdown."""


class SummariesClient(HealthCheckable):
    @abstractmethod
    async def create(self, original_filename: str, summary_text: str) -> StoredSummary: ...

    @abstractmethod
    async def list(self, limit: int) -> list[StoredSummary]: ...

    @abstractmethod
    async def get(self, summary_id: str) -> StoredSummary: ...

    @abstractmethod
    async def delete(self, summary_id: str) -> None: ...


class ExporterClient(HealthCheckable):
    @abstractmethod
    async def to_docx(self, title: str, markdown: str, filename: str) -> ExportedDocument:
        """`filename` es una sugerencia; el exportador decide el nombre final."""
