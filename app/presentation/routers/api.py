"""API pública que usa la interfaz. Mismo contrato que el monolito, más DELETE."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

from app.application.interfaces.services import SummaryOptions
from app.application.services.orchestrator import Orchestrator
from app.dependencies import get_orchestrator
from app.presentation.schemas import (
    ApiHealthResponse,
    NewSummaryResponse,
    SettingsDefaultsResponse,
    SummaryListResponse,
    SummaryResponse,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
INVALID_MAX_TOKENS_DETAIL = "max_tokens debe ser un número entero mayor que 0."

router = APIRouter(prefix="/api")


def _blank_to_none(value: str | None) -> str | None:
    # El navegador manda "" en los campos vacíos del formulario
    return value.strip() or None if value is not None else None


def summary_options(
    model: str | None = Form(None),
    api_key: str | None = Form(None),
    max_tokens: str | None = Form(None),
) -> SummaryOptions:
    """Ajustes del usuario que llegan junto al PDF. Se validan a mano para que un error
    no devuelva lo recibido: ahí iría la API key."""
    raw_tokens = _blank_to_none(max_tokens)
    if raw_tokens is not None and not (raw_tokens.isdigit() and int(raw_tokens) > 0):
        raise HTTPException(status_code=422, detail=INVALID_MAX_TOKENS_DETAIL)
    return SummaryOptions(
        model=_blank_to_none(model),
        api_key=_blank_to_none(api_key),
        max_tokens=int(raw_tokens) if raw_tokens else None,
    )


@router.post("/summarize", response_model=NewSummaryResponse)
async def summarize(
    file: UploadFile = File(...),
    options: SummaryOptions = Depends(summary_options),
    orchestrator: Orchestrator = Depends(get_orchestrator),
):
    result = await orchestrator.summarize_pdf(file.file, file.filename, options)
    return NewSummaryResponse(
        **SummaryResponse.model_validate(result.summary).model_dump(),
        truncated=result.truncated,
    )


@router.get("/settings/defaults", response_model=SettingsDefaultsResponse)
async def settings_defaults(orchestrator: Orchestrator = Depends(get_orchestrator)):
    """Solo lectura: la página Ajustes nunca cambia los valores del servidor."""
    defaults = await orchestrator.server_defaults()
    return SettingsDefaultsResponse(
        model=defaults.model,
        max_tokens=defaults.max_tokens,
        max_tokens_limit=defaults.max_tokens_limit,
    )


@router.get("/summaries", response_model=SummaryListResponse)
async def list_summaries(
    limit: int = Query(100, ge=1, le=1000),
    orchestrator: Orchestrator = Depends(get_orchestrator),
):
    summaries = await orchestrator.list_summaries(limit)
    return SummaryListResponse(summaries=summaries, total=len(summaries))


@router.get("/summaries/{summary_id}", response_model=SummaryResponse)
async def get_summary(
    summary_id: UUID, orchestrator: Orchestrator = Depends(get_orchestrator)
):
    return await orchestrator.get_summary(str(summary_id))


@router.delete("/summaries/{summary_id}", status_code=204)
async def delete_summary(
    summary_id: UUID, orchestrator: Orchestrator = Depends(get_orchestrator)
):
    await orchestrator.delete_summary(str(summary_id))
    return Response(status_code=204)


@router.get("/summaries/{summary_id}/export")
async def export_summary(
    summary_id: UUID, orchestrator: Orchestrator = Depends(get_orchestrator)
):
    document = await orchestrator.export_summary(str(summary_id))
    return Response(
        content=document.content,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )


@router.get("/health", response_model=ApiHealthResponse)
async def api_health(orchestrator: Orchestrator = Depends(get_orchestrator)):
    services = await orchestrator.health()
    status = "healthy" if all(services.values()) else "degraded"
    return ApiHealthResponse(status=status, services=services)
