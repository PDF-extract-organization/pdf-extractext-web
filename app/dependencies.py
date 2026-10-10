"""Cableado de dependencias. Routers y main lo importan; él no importa a ninguno."""

from functools import lru_cache

from app.application.services.orchestrator import Orchestrator
from app.core import Settings
from app.infrastructure.http_clients import (
    HttpExporterClient,
    HttpExtractorClient,
    HttpSummariesClient,
    HttpSummarizerClient,
)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_orchestrator() -> Orchestrator:
    settings = get_settings()
    timeout = settings.service_timeout_seconds
    return Orchestrator(
        extractor=HttpExtractorClient(settings.extractor_url, timeout),
        summarizer=HttpSummarizerClient(
            settings.summarizer_url, settings.summarizer_timeout_seconds
        ),
        summaries=HttpSummariesClient(settings.summaries_url, timeout),
        exporter=HttpExporterClient(settings.exporter_url, timeout),
    )
