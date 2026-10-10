"""Errores de los servicios de los que depende el orquestador."""


class DownstreamError(Exception):
    """Un servicio rechazó la petición con un motivo que el usuario debe ver."""

    def __init__(
        self, service: str, status_code: int, detail: str, retry_after: str | None = None
    ):
        super().__init__(f"{service} respondió {status_code}: {detail}")
        self.service = service
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


class ServiceUnavailableError(Exception):
    """Un servicio no responde o falló sin explicar el motivo."""

    def __init__(self, service: str):
        super().__init__(f"El servicio {service} no responde.")
        self.service = service


class ServiceTimeoutError(Exception):
    """Un servicio tardó más de lo permitido."""

    def __init__(self, service: str):
        super().__init__(f"El servicio {service} tardó demasiado en responder.")
        self.service = service
