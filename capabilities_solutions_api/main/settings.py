from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "capabilities-solutions-api"
    database_dsn: str = "postgresql://postgres:postgres@localhost:5432/capabilities_solutions_api"
    auto_apply_schema: bool = False
    log_level: str = "INFO"
    json_logs: bool = True
    otlp_endpoint: str | None = None
    otlp_insecure: bool = True
    otel_service_name: str | None = None

    model_config = {"env_prefix": "CAP_SOL_"}
