"""Tests de la API pública y de la portada, con dobles de los cuatro servicios."""

import pytest
from fastapi.testclient import TestClient

from app.application.errors import (
    DownstreamError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from app.application.services.orchestrator import Orchestrator
from app.dependencies import get_orchestrator
from app.main import app
from tests.conftest import FakeExporter, FakeExtractor, FakeSummaries, FakeSummarizer


def client_con(
    extractor=None, summarizer=None, summaries=None, exporter=None
) -> TestClient:
    orchestrator = Orchestrator(
        extractor or FakeExtractor(),
        summarizer or FakeSummarizer(),
        summaries if summaries is not None else FakeSummaries(),
        exporter or FakeExporter(),
    )
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    return TestClient(app)


@pytest.fixture(autouse=True)
def limpiar_overrides():
    yield
    app.dependency_overrides.clear()


def subir(client, filename="doc.pdf", contenido=b"%PDF-1.4"):
    return client.post(
        "/api/summarize", files={"file": (filename, contenido, "application/pdf")}
    )


# --- POST /api/summarize ---


def test_summarize_devuelve_el_resumen_guardado():
    response = subir(client_con())

    assert response.status_code == 200
    body = response.json()
    assert body["original_filename"] == "doc.pdf"
    assert body["summary_text"] == "# Resumen\n\nUn **resumen**."
    assert set(body) == {"id", "original_filename", "summary_text", "created_at"}


def test_summarize_sin_archivo_devuelve_422():
    assert client_con().post("/api/summarize").status_code == 422


def test_un_error_de_un_servicio_llega_al_cliente_con_su_codigo_y_mensaje():
    error = DownstreamError("extractor", 422, "El PDF no contiene texto extraíble.")

    response = subir(client_con(extractor=FakeExtractor(error=error)))

    assert response.status_code == 422
    assert response.json()["detail"] == "El PDF no contiene texto extraíble."


def test_un_429_conserva_retry_after():
    error = DownstreamError("summarizer", 429, "Límite", retry_after="30")

    response = subir(client_con(summarizer=FakeSummarizer(error=error)))

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"


def test_un_servicio_caido_devuelve_502_indicando_cual():
    summaries = FakeSummaries(error=ServiceUnavailableError("summaries"))

    response = subir(client_con(summaries=summaries))

    assert response.status_code == 502
    assert "summaries" in response.json()["detail"]


def test_un_timeout_de_un_servicio_devuelve_504_indicando_cual():
    summarizer = FakeSummarizer(error=ServiceTimeoutError("summarizer"))

    response = subir(client_con(summarizer=summarizer))

    assert response.status_code == 504
    assert "summarizer" in response.json()["detail"]


# --- GET /api/summaries y /api/summaries/{id} ---


def test_listar_devuelve_los_resumenes_y_el_total():
    client = client_con()
    subir(client, "a.pdf")
    subir(client, "b.pdf")

    body = client.get("/api/summaries").json()

    assert body["total"] == 2
    assert [s["original_filename"] for s in body["summaries"]] == ["b.pdf", "a.pdf"]


def test_obtener_devuelve_el_resumen():
    client = client_con()
    created = subir(client).json()

    assert client.get(f"/api/summaries/{created['id']}").json() == created


def test_obtener_un_id_que_no_es_uuid_devuelve_422():
    assert client_con().get("/api/summaries/no-es-uuid").status_code == 422


def test_un_404_de_summaries_llega_como_404():
    error = DownstreamError("summaries", 404, "No existe un resumen con ese id.")
    client = client_con(summaries=FakeSummaries(error=error))

    response = client.get("/api/summaries/00000000-0000-0000-0000-000000000009")

    assert response.status_code == 404
    assert response.json()["detail"] == "No existe un resumen con ese id."


# --- DELETE /api/summaries/{id} ---


def test_borrar_devuelve_204_y_el_resumen_desaparece():
    summaries = FakeSummaries()
    client = client_con(summaries=summaries)
    created = subir(client).json()

    response = client.delete(f"/api/summaries/{created['id']}")

    assert response.status_code == 204
    assert summaries.stored == []


def test_borrar_un_id_que_no_es_uuid_devuelve_422():
    assert client_con().delete("/api/summaries/no-es-uuid").status_code == 422


# --- GET /api/summaries/{id}/export ---


def test_exportar_devuelve_el_docx_con_el_nombre_del_exportador():
    client = client_con()
    created = subir(client, "informe.pdf").json()

    response = client.get(f"/api/summaries/{created['id']}/export")

    assert response.status_code == 200
    assert response.content == b"PK-docx"
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == (
        'attachment; filename="resumen_informe.docx"'
    )


# --- GET /api/health ---


def test_health_healthy_si_todos_los_servicios_responden():
    response = client_con().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "services": {"extractor": True, "summarizer": True, "summaries": True, "exporter": True},
    }


def test_health_degraded_indica_que_servicio_falla():
    body = client_con(exporter=FakeExporter(healthy=False)).get("/api/health").json()

    assert body["status"] == "degraded"
    assert body["services"]["exporter"] is False


def test_health_propio_para_docker_no_depende_de_los_demas():
    response = client_con(exporter=FakeExporter(healthy=False)).get("/health")

    assert response.json() == {"status": "healthy", "service": "web"}


# --- portada ---


def test_la_portada_se_sirve_en_utf8():
    response = client_con().get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "PDF Summarizer" in response.text


def test_la_portada_fija_las_versiones_de_marked_y_dompurify():
    html = client_con().get("/").text

    assert "marked@12.0.2" in html
    assert "dompurify@3.1.6" in html
    assert "DOMPurify.sanitize(marked.parse(" in html


def test_la_portada_no_mete_texto_de_usuario_con_innerhtml_sin_sanear():
    html = client_con().get("/").text

    assert "innerHTML = marked.parse(" not in html
    assert "${s.original_filename}" not in html
