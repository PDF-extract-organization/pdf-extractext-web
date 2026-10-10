"""Caso de uso: coordinar los servicios para resumir, consultar, borrar y exportar."""

import asyncio
from pathlib import PurePath
from typing import BinaryIO

from app.application.interfaces.services import (
    ExportedDocument,
    ExporterClient,
    ExtractorClient,
    StoredSummary,
    SummariesClient,
    SummarizerClient,
)


class Orchestrator:
    def __init__(
        self,
        extractor: ExtractorClient,
        summarizer: SummarizerClient,
        summaries: SummariesClient,
        exporter: ExporterClient,
    ):
        self._extractor = extractor
        self._summarizer = summarizer
        self._summaries = summaries
        self._exporter = exporter

    async def summarize_pdf(self, file: BinaryIO, filename: str) -> StoredSummary:
        # Si un paso falla, su error se propaga y los siguientes no se ejecutan
        extracted = await self._extractor.extract(file, filename)
        summary = await self._summarizer.summarize(extracted.text)
        return await self._summaries.create(filename, summary)

    async def list_summaries(self, limit: int) -> list[StoredSummary]:
        return await self._summaries.list(limit)

    async def get_summary(self, summary_id: str) -> StoredSummary:
        return await self._summaries.get(summary_id)

    async def delete_summary(self, summary_id: str) -> None:
        await self._summaries.delete(summary_id)

    async def export_summary(self, summary_id: str) -> ExportedDocument:
        summary = await self._summaries.get(summary_id)
        return await self._exporter.to_docx(
            title=f"Resumen: {summary.original_filename}",
            markdown=summary.summary_text,
            filename=f"resumen_{PurePath(summary.original_filename).stem}",
        )

    async def health(self) -> dict[str, bool]:
        services = {
            "extractor": self._extractor,
            "summarizer": self._summarizer,
            "summaries": self._summaries,
            "exporter": self._exporter,
        }
        results = await asyncio.gather(*(s.is_healthy() for s in services.values()))
        return dict(zip(services, results))
