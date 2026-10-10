from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.presentation.errors import register_error_handlers
from app.presentation.routers import api, pages

STATIC_DIR = Path(__file__).parent.parent / "static"

app = FastAPI(title="pdf-extractext-web")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.include_router(api.router)
app.include_router(pages.router)
register_error_handlers(app)
