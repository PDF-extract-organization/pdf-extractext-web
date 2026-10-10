"""Adaptadores HTTP de los puertos de los cuatro servicios.

La traducción de errores es común a todos y vive en _ServiceClient:
- respuesta con {"detail": ...} → DownstreamError con el mismo código y mensaje
- sin detalle (caída, 500 sin JSON) o sin conexión → ServiceUnavailableError
- timeout → ServiceTimeoutError
"""

import re
from typing import BinaryIO

import httpx

from app.application.errors import (
    DownstreamError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from app.application.interfaces.services import (
    ExportedDocument,
    ExporterClient,
    ExtractedText,
    ExtractorClient,
    StoredSummary,
    SummariesClient,
    SummarizerClient,
)

HEALTH_TIMEOUT_SECONDS = 2.0
FILENAME_IN_DISPOSITION = re.compile(r'filename="([^"]+)"')


class _ServiceClient:
    name: str

    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def is_healthy(self) -> bool:
        try:
            response = await self._send("GET", "/health", timeout=HEALTH_TIMEOUT_SECONDS)
            return response.status_code == 200 and response.json().get("status") == "healthy"
        except (httpx.HTTPError, ValueError):
            return False

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._send(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise ServiceTimeoutError(self.name) from error
        except httpx.RequestError as error:
            raise ServiceUnavailableError(self.name) from error

        if response.is_success:
            return response

        detail = _detail(response)
        if detail is None:
            raise ServiceUnavailableError(self.name)
        raise DownstreamError(
            self.name, response.status_code, detail, response.headers.get("Retry-After")
        )

    async def _send(self, method: str, path: str, timeout: float | None = None, **kwargs):
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout or self._timeout_seconds,
            transport=self._transport,
        ) as client:
            return await client.request(method, path, **kwargs)


def _detail(response: httpx.Response) -> str | None:
    """El mensaje de error del servicio, si respondió con el formato de FastAPI."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return None
    if detail is None:
        return None
    # Los errores de validación de FastAPI traen una lista, no un texto
    return detail if isinstance(detail, str) else "El servicio rechazó la petición."


class HttpExtractorClient(_ServiceClient, ExtractorClient):
    name = "extractor"

    async def extract(self, file: BinaryIO, filename: str) -> ExtractedText:
        response = await self._request(
            "POST", "/extract", files={"file": (filename, file, "application/pdf")}
        )
        data = response.json()
        return ExtractedText(filename=data["filename"], text=data["text"])


class HttpSummarizerClient(_ServiceClient, SummarizerClient):
    name = "summarizer"

    async def summarize(self, text: str) -> str:
        response = await self._request("POST", "/summarize", json={"text": text})
        return response.json()["summary"]


class HttpSummariesClient(_ServiceClient, SummariesClient):
    name = "summaries"

    async def create(self, original_filename: str, summary_text: str) -> StoredSummary:
        response = await self._request(
            "POST",
            "/",
            json={"original_filename": original_filename, "summary_text": summary_text},
        )
        return _to_stored(response.json())

    async def list(self, limit: int) -> list[StoredSummary]:
        response = await self._request("GET", "/", params={"limit": limit})
        return [_to_stored(item) for item in response.json()["summaries"]]

    async def get(self, summary_id: str) -> StoredSummary:
        response = await self._request("GET", f"/{summary_id}")
        return _to_stored(response.json())

    async def delete(self, summary_id: str) -> None:
        await self._request("DELETE", f"/{summary_id}")


def _to_stored(data: dict) -> StoredSummary:
    return StoredSummary(
        id=data["id"],
        original_filename=data["original_filename"],
        summary_text=data["summary_text"],
        created_at=data["created_at"],
    )


class HttpExporterClient(_ServiceClient, ExporterClient):
    name = "exporter"

    async def to_docx(self, title: str, markdown: str, filename: str) -> ExportedDocument:
        response = await self._request(
            "POST", "/docx", json={"title": title, "markdown": markdown, "filename": filename}
        )
        # El nombre final lo decide (y lo sanea) el exportador
        match = FILENAME_IN_DISPOSITION.search(response.headers.get("Content-Disposition", ""))
        return ExportedDocument(
            filename=match.group(1) if match else "resumen.docx",
            content=response.content,
        )
