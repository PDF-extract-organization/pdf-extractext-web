"""Puertos de los cuatro servicios. El orquestador no sabe que hablan HTTP."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class SummaryOptions:
    """Ajustes del usuario (página Ajustes). Lo que falte lo pone summarizer: Consul o .env."""

    model: str | None = None
    # repr=False: que la clave no salga si el objeto acaba en un log
    api_key: str | None = field(default=None, repr=False)
    max_tokens: int | None = None


@dataclass(frozen=True)
class GeneratedSummary:
    text: str
    # El modelo paró por max_tokens: el resumen está incompleto
    truncated: bool


@dataclass(frozen=True)
class ServerDefaults:
    """Lo que usa summarizer cuando el usuario no elige nada."""

    model: str
    max_tokens: int
    # Máximo que acepta max_tokens en una petición
    max_tokens_limit: int


class HealthCheckable(ABC):
    @abstractmethod
    async def is_healthy(self) -> bool: ...


class ExtractorClient(HealthCheckable):
    @abstractmethod
    async def extract(self, file: BinaryIO, filename: str) -> ExtractedText: ...


class SummarizerClient(HealthCheckable):
    @abstractmethod
    async def summarize(
        self, text: str, options: SummaryOptions = SummaryOptions()
    ) -> GeneratedSummary:
        """El resumen en Markdown. Solo se envían los ajustes que tengan valor."""

    @abstractmethod
    async def defaults(self) -> ServerDefaults: ...


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
