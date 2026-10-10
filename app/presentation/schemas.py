from pydantic import BaseModel, ConfigDict


class SummaryResponse(BaseModel):
    # Se construye directamente desde StoredSummary (un dataclass)
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    summary_text: str
    created_at: str


class SummaryListResponse(BaseModel):
    summaries: list[SummaryResponse]
    total: int


class ApiHealthResponse(BaseModel):
    status: str
    services: dict[str, bool]


class HealthResponse(BaseModel):
    status: str
    service: str
