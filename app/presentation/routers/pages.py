"""Páginas de la interfaz y health propio del contenedor."""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.presentation.schemas import HealthResponse

TEMPLATES = Path(__file__).parent.parent / "templates"

router = APIRouter()


def _page(name: str) -> str:
    # Codificación explícita: no depende del sistema operativo (en Windows no es UTF-8)
    return (TEMPLATES / name).read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
async def index():
    return _page("index.html")


@router.get("/ajustes", response_class=HTMLResponse)
async def ajustes():
    return _page("ajustes.html")


@router.get("/health", response_model=HealthResponse)
async def health():
    """Solo indica que el proceso está vivo. El estado de los demás está en /api/health."""
    return HealthResponse(status="healthy", service="web")
