"""Tests de los clientes HTTP de los cuatro servicios, con un transporte simulado."""

import io
import json

import httpx
import pytest

from app.application.errors import (
    DownstreamError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from app.infrastructure.http_clients import (
    HttpExporterClient,
    HttpExtractorClient,
    HttpSummariesClient,
    HttpSummarizerClient,
)


def transport(handler, requests=None):
    def capturing(request):
        if requests is not None:
            requests.append(request)
        return handler(request)

    return httpx.MockTransport(capturing)


def respond(status, body=None, headers=None):
    return lambda request: httpx.Response(status, json=body, headers=headers)


def make(cls, handler, requests=None):
    return cls("http://servicio.test", timeout_seconds=5, transport=transport(handler, requests))


SUMMARY = {
    "id": "6f1c0e3a-0000-0000-0000-000000000001",
    "original_filename": "doc.pdf",
    "summary_text": "Un resumen",
    "created_at": "2026-10-10T12:00:00Z",
}


# --- traducción de errores, común a todos los clientes ---


async def test_un_4xx_con_detalle_se_propaga_con_su_codigo_y_mensaje():
    client = make(HttpExtractorClient, respond(422, {"detail": "Sin texto"}))

    with pytest.raises(DownstreamError) as info:
        await client.extract(io.BytesIO(b"%PDF"), "doc.pdf")

    assert (info.value.service, info.value.status_code, info.value.detail) == (
        "extractor",
        422,
        "Sin texto",
    )


async def test_un_5xx_con_detalle_tambien_se_propaga():
    client = make(HttpSummarizerClient, respond(503, {"detail": "Falta la API key"}))

    with pytest.raises(DownstreamError) as info:
        await client.summarize("texto")

    assert info.value.status_code == 503
    assert info.value.detail == "Falta la API key"


async def test_un_429_conserva_el_retry_after():
    client = make(
        HttpSummarizerClient, respond(429, {"detail": "Límite"}, {"Retry-After": "30"})
    )

    with pytest.raises(DownstreamError) as info:
        await client.summarize("texto")

    assert info.value.retry_after == "30"


async def test_un_500_sin_detalle_es_servicio_no_disponible():
    def handler(request):
        return httpx.Response(500, text="Internal Server Error")

    with pytest.raises(ServiceUnavailableError) as info:
        await make(HttpSummariesClient, handler).list(limit=10)

    assert info.value.service == "summaries"


async def test_si_no_se_puede_conectar_es_servicio_no_disponible():
    def handler(request):
        raise httpx.ConnectError("sin red", request=request)

    with pytest.raises(ServiceUnavailableError):
        await make(HttpExporterClient, handler).to_docx("t", "m", "f")


async def test_un_timeout_es_service_timeout_error():
    def handler(request):
        raise httpx.ReadTimeout("lento", request=request)

    with pytest.raises(ServiceTimeoutError) as info:
        await make(HttpSummarizerClient, handler).summarize("texto")

    assert info.value.service == "summarizer"


# --- extractor ---


async def test_extractor_envia_el_pdf_en_multipart_y_lee_el_texto():
    requests = []
    client = make(
        HttpExtractorClient,
        respond(200, {"filename": "doc.pdf", "text": "Hola", "page_count": 1, "character_count": 4}),
        requests,
    )

    result = await client.extract(io.BytesIO(b"%PDF-contenido"), "doc.pdf")

    assert result.text == "Hola"
    assert str(requests[0].url) == "http://servicio.test/extract"
    body = requests[0].read()
    assert b'filename="doc.pdf"' in body
    assert b"%PDF-contenido" in body


# --- summarizer ---


async def test_summarizer_envia_el_texto_y_devuelve_el_resumen():
    requests = []
    client = make(
        HttpSummarizerClient,
        respond(200, {"summary": "Resumen", "model": "m", "tokens_used": 1}),
        requests,
    )

    assert await client.summarize("el texto") == "Resumen"
    assert str(requests[0].url) == "http://servicio.test/summarize"
    assert json.loads(requests[0].read()) == {"text": "el texto"}


# --- summaries ---


async def test_summaries_create_envia_nombre_y_texto():
    requests = []
    client = make(HttpSummariesClient, respond(201, SUMMARY), requests)

    stored = await client.create("doc.pdf", "Un resumen")

    assert stored.id == SUMMARY["id"]
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://servicio.test/"
    assert json.loads(requests[0].read()) == {
        "original_filename": "doc.pdf",
        "summary_text": "Un resumen",
    }


async def test_summaries_list_pasa_el_limite():
    requests = []
    client = make(HttpSummariesClient, respond(200, {"summaries": [SUMMARY], "total": 1}), requests)

    result = await client.list(limit=5)

    assert [s.id for s in result] == [SUMMARY["id"]]
    assert str(requests[0].url) == "http://servicio.test/?limit=5"


async def test_summaries_get_y_delete_usan_el_id_en_la_ruta():
    requests = []

    def handler(request):
        return httpx.Response(204) if request.method == "DELETE" else httpx.Response(200, json=SUMMARY)

    client = make(HttpSummariesClient, handler, requests)

    assert (await client.get(SUMMARY["id"])).original_filename == "doc.pdf"
    await client.delete(SUMMARY["id"])

    assert [(r.method, str(r.url)) for r in requests] == [
        ("GET", f"http://servicio.test/{SUMMARY['id']}"),
        ("DELETE", f"http://servicio.test/{SUMMARY['id']}"),
    ]


# --- exporter ---


async def test_exporter_devuelve_el_contenido_y_el_nombre_que_decide_el_exportador():
    requests = []

    def handler(request):
        return httpx.Response(
            200,
            content=b"PK-docx",
            headers={"Content-Disposition": 'attachment; filename="resumen_doc.docx"'},
        )

    document = await make(HttpExporterClient, handler, requests).to_docx(
        "Resumen: doc.pdf", "# Hola", "resumen_doc"
    )

    assert document.content == b"PK-docx"
    assert document.filename == "resumen_doc.docx"
    assert json.loads(requests[0].read()) == {
        "title": "Resumen: doc.pdf",
        "markdown": "# Hola",
        "filename": "resumen_doc",
    }


# --- is_healthy ---


@pytest.mark.parametrize(
    "status, body, expected",
    [
        (200, {"status": "healthy"}, True),
        (200, {"status": "degraded"}, False),
        (503, {"status": "unhealthy"}, False),
    ],
)
async def test_is_healthy_segun_la_respuesta_de_health(status, body, expected):
    requests = []
    client = make(HttpSummarizerClient, respond(status, body), requests)

    assert await client.is_healthy() is expected
    assert str(requests[0].url) == "http://servicio.test/health"


async def test_is_healthy_es_false_si_no_se_puede_conectar():
    def handler(request):
        raise httpx.ConnectError("sin red", request=request)

    assert await make(HttpExtractorClient, handler).is_healthy() is False
