from pydantic import BaseModel, ConfigDict


class SummaryResponse(BaseModel):
    # Se construye directamente desde StoredSummary (un dataclass)
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    summary_text: str
    created_at: str


class NewSummaryResponse(SummaryResponse):
    # El modelo paró por max_tokens: la interfaz avisa de que el resumen está incompleto
    truncated: bool


class SettingsDefaultsResponse(BaseModel):
    """Valores del servidor que la página Ajustes muestra como 'por defecto'."""

    model: str
    max_tokens: int
    max_tokens_limit: int


class SummaryListResponse(BaseModel):
    summaries: list[SummaryResponse]
    total: int


class ApiHealthResponse(BaseModel):
    status: str
    services: dict[str, bool]


class HealthResponse(BaseModel):
    status: str
    service: str
