"""Traducción a HTTP de los errores de los servicios, en un solo sitio para toda la API."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.errors import (
    DownstreamError,
    ServiceTimeoutError,
    ServiceUnavailableError,
)


async def _downstream(request: Request, error: DownstreamError) -> JSONResponse:
    # El servicio ya explicó el motivo: se devuelve tal cual al usuario
    headers = {"Retry-After": error.retry_after} if error.retry_after else None
    return JSONResponse(
        status_code=error.status_code, content={"detail": error.detail}, headers=headers
    )


async def _unavailable(request: Request, error: ServiceUnavailableError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"detail": f"El servicio {error.service} no responde. Inténtalo más tarde."},
    )


async def _timeout(request: Request, error: ServiceTimeoutError) -> JSONResponse:
    return JSONResponse(
        status_code=504,
        content={"detail": f"El servicio {error.service} tardó demasiado en responder."},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DownstreamError, _downstream)
    app.add_exception_handler(ServiceUnavailableError, _unavailable)
    app.add_exception_handler(ServiceTimeoutError, _timeout)
