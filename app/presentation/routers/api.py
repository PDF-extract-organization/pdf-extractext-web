"""API pública que usa la interfaz. Mismo contrato que el monolito, más DELETE."""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from app.application.services.orchestrator import Orchestrator
from app.dependencies import get_orchestrator
from app.presentation.schemas import (
    ApiHealthResponse,
    SummaryListResponse,
    SummaryResponse,
)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix="/api")


@router.post("/summarize", response_model=SummaryResponse)
async def summarize(
    file: UploadFile = File(...),
    orchestrator: Orchestrator = Depends(get_orchestrator),
):
    return await orchestrator.summarize_pdf(file.file, file.filename)


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
