"""Tests del caso de uso que orquesta los cuatro servicios, con dobles."""

import io

import pytest

from app.application.errors import DownstreamError, ServiceUnavailableError
from app.application.interfaces.services import SummaryOptions
from app.application.services.orchestrator import Orchestrator
from tests.conftest import (
    DEFAULTS,
    FakeExporter,
    FakeExtractor,
    FakeSummaries,
    FakeSummarizer,
)


@pytest.fixture
def orchestrator(extractor, summarizer, summaries, exporter) -> Orchestrator:
    return Orchestrator(extractor, summarizer, summaries, exporter)


# --- summarize_pdf ---


async def test_summarize_pdf_encadena_extraer_resumir_y_guardar(
    orchestrator, extractor, summarizer, summaries
):
    result = await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")

    assert extractor.received == [(b"%PDF", "doc.pdf")]
    assert summarizer.received == ["Texto extraído del PDF"]
    assert summaries.stored == [result.summary]
    assert result.summary.original_filename == "doc.pdf"
    assert result.summary.summary_text == "# Resumen\n\nUn **resumen**."
    assert result.truncated is False


async def test_sin_ajustes_del_usuario_no_se_envia_ninguno(orchestrator, summarizer):
    await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")

    assert summarizer.options == [SummaryOptions()]


async def test_los_ajustes_del_usuario_llegan_a_summarizer(orchestrator, summarizer):
    options = SummaryOptions(model="modelo/usuario", api_key="sk-usuario", max_tokens=1500)

    await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf", options)

    assert summarizer.options == [options]


async def test_la_api_key_del_usuario_no_se_guarda_en_summaries(orchestrator, summaries):
    options = SummaryOptions(api_key="sk-usuario-secreta")

    await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf", options)

    assert "sk-usuario-secreta" not in repr(summaries.stored)


async def test_un_resumen_cortado_se_guarda_y_se_devuelve_marcado(extractor, summaries, exporter):
    orchestrator = Orchestrator(extractor, FakeSummarizer(truncated=True), summaries, exporter)

    result = await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")

    assert result.truncated is True
    assert summaries.stored == [result.summary]


async def test_la_api_key_no_aparece_al_imprimir_los_ajustes():
    assert "sk-secreta" not in repr(SummaryOptions(api_key="sk-secreta"))


async def test_server_defaults_delega_en_summarizer(orchestrator):
    assert await orchestrator.server_defaults() == DEFAULTS


async def test_si_falla_la_extraccion_no_se_llama_a_la_ia_ni_se_guarda(summarizer, summaries, exporter):
    error = DownstreamError("extractor", 422, "El PDF no contiene texto extraíble.")
    orchestrator = Orchestrator(FakeExtractor(error=error), summarizer, summaries, exporter)

    with pytest.raises(DownstreamError):
        await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "escaneado.pdf")

    assert summarizer.received == []
    assert summaries.stored == []


async def test_si_falla_la_ia_no_se_guarda_nada(extractor, summaries, exporter):
    error = DownstreamError("summarizer", 503, "Falta la OPENROUTER_API_KEY")
    orchestrator = Orchestrator(extractor, FakeSummarizer(error=error), summaries, exporter)

    with pytest.raises(DownstreamError):
        await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")

    assert summaries.stored == []


async def test_si_falla_el_guardado_se_propaga_el_error(extractor, summarizer, exporter):
    orchestrator = Orchestrator(
        extractor, summarizer, FakeSummaries(error=ServiceUnavailableError("summaries")), exporter
    )

    with pytest.raises(ServiceUnavailableError):
        await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")


# --- list, get, delete ---


async def test_list_get_y_delete_delegan_en_summaries(orchestrator, summaries):
    stored = (await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")).summary

    assert await orchestrator.list_summaries(limit=10) == [stored]
    assert await orchestrator.get_summary(stored.id) == stored

    await orchestrator.delete_summary(stored.id)
    assert summaries.stored == []


# --- export ---


async def test_export_pide_el_docx_con_titulo_y_nombre_derivados_del_pdf(orchestrator, exporter):
    stored = (await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "informe.pdf")).summary

    document = await orchestrator.export_summary(stored.id)

    assert exporter.received == [
        ("Resumen: informe.pdf", stored.summary_text, "resumen_informe")
    ]
    assert document.filename == "resumen_informe.docx"
    assert document.content == b"PK-docx"


# --- health ---


async def test_health_informa_del_estado_de_cada_servicio():
    orchestrator = Orchestrator(
        FakeExtractor(healthy=True),
        FakeSummarizer(healthy=False),
        FakeSummaries(healthy=True),
        FakeExporter(healthy=False),
    )

    assert await orchestrator.health() == {
        "extractor": True,
        "summarizer": False,
        "summaries": True,
        "exporter": False,
    }
