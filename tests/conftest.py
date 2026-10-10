"""Dobles de los cuatro servicios. Registran lo que reciben y pueden fallar a demanda."""

from typing import BinaryIO

import pytest

from app.application.interfaces.services import (
    ExportedDocument,
    ExporterClient,
    ExtractedText,
    ExtractorClient,
    StoredSummary,
    SummariesClient,
    SummarizerClient,
)


class FakeExtractor(ExtractorClient):
    def __init__(self, text="Texto extraído del PDF", error=None, healthy=True):
        self._text, self._error, self._healthy = text, error, healthy
        self.received: list[tuple[bytes, str]] = []

    async def extract(self, file: BinaryIO, filename: str) -> ExtractedText:
        self.received.append((file.read(), filename))
        if self._error:
            raise self._error
        return ExtractedText(filename=filename, text=self._text)

    async def is_healthy(self) -> bool:
        return self._healthy


class FakeSummarizer(SummarizerClient):
    def __init__(self, summary="# Resumen\n\nUn **resumen**.", error=None, healthy=True):
        self._summary, self._error, self._healthy = summary, error, healthy
        self.received: list[str] = []

    async def summarize(self, text: str) -> str:
        self.received.append(text)
        if self._error:
            raise self._error
        return self._summary

    async def is_healthy(self) -> bool:
        return self._healthy


class FakeSummaries(SummariesClient):
    def __init__(self, error=None, healthy=True):
        self._error, self._healthy = error, healthy
        self.stored: list[StoredSummary] = []

    async def create(self, original_filename: str, summary_text: str) -> StoredSummary:
        if self._error:
            raise self._error
        summary = StoredSummary(
            id=f"00000000-0000-0000-0000-{len(self.stored):012d}",
            original_filename=original_filename,
            summary_text=summary_text,
            created_at="2026-10-10T12:00:00Z",
        )
        self.stored.append(summary)
        return summary

    async def list(self, limit: int) -> list[StoredSummary]:
        if self._error:
            raise self._error
        return list(reversed(self.stored))[:limit]

    async def get(self, summary_id: str) -> StoredSummary:
        if self._error:
            raise self._error
        return next(s for s in self.stored if s.id == summary_id)

    async def delete(self, summary_id: str) -> None:
        if self._error:
            raise self._error
        self.stored = [s for s in self.stored if s.id != summary_id]

    async def is_healthy(self) -> bool:
        return self._healthy


class FakeExporter(ExporterClient):
    def __init__(self, error=None, healthy=True):
        self._error, self._healthy = error, healthy
        self.received: list[tuple[str, str, str]] = []

    async def to_docx(self, title: str, markdown: str, filename: str) -> ExportedDocument:
        self.received.append((title, markdown, filename))
        if self._error:
            raise self._error
        return ExportedDocument(filename=f"{filename}.docx", content=b"PK-docx")

    async def is_healthy(self) -> bool:
        return self._healthy


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def summarizer() -> FakeSummarizer:
    return FakeSummarizer()


@pytest.fixture
def summaries() -> FakeSummaries:
    return FakeSummaries()


@pytest.fixture
def exporter() -> FakeExporter:
    return FakeExporter()
