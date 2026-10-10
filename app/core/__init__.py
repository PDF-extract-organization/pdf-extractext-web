"""Configuración leída de variables de entorno o del .env."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # URLs internas de los servicios en la red de Docker (sin pasar por Traefik)
    extractor_url: str = "http://extractor:8000"
    summarizer_url: str = "http://summarizer:8000"
    summaries_url: str = "http://summaries:8000"
    exporter_url: str = "http://exporter:8000"

    service_timeout_seconds: float = 10.0
    # El resumen espera a la IA, que puede tardar hasta su propio timeout (60 s)
    summarizer_timeout_seconds: float = 90.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
