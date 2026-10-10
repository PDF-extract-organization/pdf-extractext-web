"""Portada y health propio del contenedor."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.presentation.schemas import HealthResponse

TEMPLATE = Path(__file__).parent.parent / "templates" / "index.html"

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index():
    # Codificación explícita: no depende del sistema operativo (en Windows no es UTF-8)
    return TEMPLATE.read_text(encoding="utf-8")


@router.get("/health", response_model=HealthResponse)
async def health():
    """Solo indica que el proceso está vivo. El estado de los demás está en /api/health."""
    return HealthResponse(status="healthy", service="web")
