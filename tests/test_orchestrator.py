"""Tests del caso de uso que orquesta los cuatro servicios, con dobles."""

import io

import pytest

from app.application.errors import DownstreamError, ServiceUnavailableError
from app.application.services.orchestrator import Orchestrator
from tests.conftest import FakeExporter, FakeExtractor, FakeSummaries, FakeSummarizer


@pytest.fixture
def orchestrator(extractor, summarizer, summaries, exporter) -> Orchestrator:
    return Orchestrator(extractor, summarizer, summaries, exporter)


# --- summarize_pdf ---


async def test_summarize_pdf_encadena_extraer_resumir_y_guardar(
    orchestrator, extractor, summarizer, summaries
):
    stored = await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")

    assert extractor.received == [(b"%PDF", "doc.pdf")]
    assert summarizer.received == ["Texto extraído del PDF"]
    assert summaries.stored == [stored]
    assert stored.original_filename == "doc.pdf"
    assert stored.summary_text == "# Resumen\n\nUn **resumen**."


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
    stored = await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "doc.pdf")

    assert await orchestrator.list_summaries(limit=10) == [stored]
    assert await orchestrator.get_summary(stored.id) == stored

    await orchestrator.delete_summary(stored.id)
    assert summaries.stored == []


# --- export ---


async def test_export_pide_el_docx_con_titulo_y_nombre_derivados_del_pdf(orchestrator, exporter):
    stored = await orchestrator.summarize_pdf(io.BytesIO(b"%PDF"), "informe.pdf")

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
