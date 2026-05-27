from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "tool-actions-api"
    database_dsn: str = "postgresql://postgres:postgres@localhost:5432/tool_actions_api"
    database_dsn_file: str | None = None
    capabilities_api_url: str = "http://localhost:8001"
    auto_apply_schema: bool = False
    log_level: str = "INFO"
    json_logs: bool = True
    otlp_endpoint: str | None = None
    otlp_insecure: bool = True
    otel_service_name: str | None = None

    model_config = {"env_prefix": "TOOL_ACTIONS_"}

    @model_validator(mode="after")
    def _resolve_dsn_from_file(self) -> Settings:
        if self.database_dsn_file:
            self.database_dsn = Path(self.database_dsn_file).read_text().strip()
        return self
