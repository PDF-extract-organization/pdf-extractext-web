"""Tests de la API pública y de la portada, con dobles de los cuatro servicios."""

import pytest
from fastapi.testclient import TestClient

from app.application.errors import (
    DownstreamError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)
from app.application.interfaces.services import SummaryOptions
from app.application.services.orchestrator import Orchestrator
from app.dependencies import get_orchestrator
from app.main import app
from tests.conftest import FakeExporter, FakeExtractor, FakeSummaries, FakeSummarizer

SECRET = "sk-or-v1-secreta-del-usuario"
# Clave de localStorage compartida por la portada y la página Ajustes
SETTINGS_KEY = "pdf_extractext_settings"


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


def subir(client, filename="doc.pdf", contenido=b"%PDF-1.4", **ajustes):
    return client.post(
        "/api/summarize",
        files={"file": (filename, contenido, "application/pdf")},
        data=ajustes or None,
    )


# --- POST /api/summarize ---


def test_summarize_devuelve_el_resumen_guardado():
    response = subir(client_con())

    assert response.status_code == 200
    body = response.json()
    assert body["original_filename"] == "doc.pdf"
    assert body["summary_text"] == "# Resumen\n\nUn **resumen**."
    assert body["truncated"] is False
    assert set(body) == {"id", "original_filename", "summary_text", "created_at", "truncated"}


def test_summarize_marca_un_resumen_cortado():
    response = subir(client_con(summarizer=FakeSummarizer(truncated=True)))

    assert response.json()["truncated"] is True


def test_los_ajustes_del_formulario_llegan_a_summarizer():
    summarizer = FakeSummarizer()

    subir(
        client_con(summarizer=summarizer),
        model="modelo/usuario",
        api_key=SECRET,
        max_tokens="1500",
    )

    assert summarizer.options == [
        SummaryOptions(model="modelo/usuario", api_key=SECRET, max_tokens=1500)
    ]


def test_sin_ajustes_no_se_envia_ninguno():
    summarizer = FakeSummarizer()

    subir(client_con(summarizer=summarizer))

    assert summarizer.options == [SummaryOptions()]


def test_ajustes_en_blanco_cuentan_como_no_enviados():
    """El formulario del navegador manda "" en los campos vacíos."""
    summarizer = FakeSummarizer()

    subir(client_con(summarizer=summarizer), model="  ", api_key="", max_tokens="")

    assert summarizer.options == [SummaryOptions()]


@pytest.mark.parametrize("max_tokens", ["muchos", "0", "-3", "1.5"])
def test_max_tokens_mal_formado_devuelve_422_sin_devolver_la_clave(max_tokens):
    summarizer = FakeSummarizer()

    response = subir(client_con(summarizer=summarizer), api_key=SECRET, max_tokens=max_tokens)

    assert response.status_code == 422
    assert SECRET not in response.text
    assert summarizer.received == []


def test_el_error_de_summarizer_con_la_clave_del_usuario_llega_tal_cual():
    error = DownstreamError("summarizer", 401, "La API key no es válida.")

    response = subir(client_con(summarizer=FakeSummarizer(error=error)), api_key=SECRET)

    assert response.status_code == 401
    assert response.json()["detail"] == "La API key no es válida."
    assert SECRET not in response.text


# --- GET /api/settings/defaults ---


def test_settings_defaults_devuelve_los_valores_del_servidor():
    response = client_con().get("/api/settings/defaults")

    assert response.status_code == 200
    assert response.json() == {
        "model": "modelo/servidor",
        "max_tokens": 5000,
        "max_tokens_limit": 8000,
    }


def test_settings_defaults_con_summarizer_caido_devuelve_502():
    summarizer = FakeSummarizer(error=ServiceUnavailableError("summarizer"))

    response = client_con(summarizer=summarizer).get("/api/settings/defaults")

    assert response.status_code == 502
    assert "summarizer" in response.json()["detail"]


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

    # truncated solo viaja al generarlo: no se guarda en summaries
    stored = {k: v for k, v in created.items() if k != "truncated"}
    assert client.get(f"/api/summaries/{created['id']}").json() == stored


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


def test_el_boton_del_resumen_abre_ajustes_en_vez_de_vaciar_la_vista():
    html = client_con().get("/").text

    assert 'href="/ajustes"' in html
    assert 'aria-label="Ajustes"' in html
    assert 'aria-label="Close summary"' not in html
    assert "addEventListener('click', clearResult)" not in html


def test_la_portada_avisa_de_los_resumenes_cortados():
    html = client_con().get("/").text

    assert 'id="truncated-warning"' in html
    assert ".truncated" in html


def test_la_portada_lee_los_ajustes_guardados_en_ajustes():
    assert SETTINGS_KEY in client_con().get("/").text


# --- página Ajustes ---


def test_ajustes_se_sirve_en_utf8():
    response = client_con().get("/ajustes")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Ajustes" in response.text
    assert "Restablecer" in response.text


def test_ajustes_guarda_en_la_misma_clave_que_lee_la_portada():
    assert SETTINGS_KEY in client_con().get("/ajustes").text


def test_ajustes_pide_la_api_key_como_contrasena():
    assert 'type="password"' in client_con().get("/ajustes").text


def test_ajustes_no_usa_innerhtml():
    """Los nombres de modelo los escribe el usuario: se pintan siempre con textContent."""
    assert "innerHTML" not in client_con().get("/ajustes").text
