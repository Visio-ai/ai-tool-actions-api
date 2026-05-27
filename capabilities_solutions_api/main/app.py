from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from visio_ml_utils.log import configure_structlog

from capabilities_solutions_api.adapters.capabilities_client import CapabilitiesClient
from capabilities_solutions_api.adapters.controllers.routes import router
from capabilities_solutions_api.adapters.repositories.postgres import PostgresToolActionRepository
from capabilities_solutions_api.app.use_cases.catalog_service import ToolActionCatalogService
from capabilities_solutions_api.domain.errors import ConflictError, DomainError, NotFoundError, ValidationError
from capabilities_solutions_api.main.db import apply_schema, create_pool
from capabilities_solutions_api.main.settings import Settings
from capabilities_solutions_api.main.telemetry import configure_telemetry


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    pool: AsyncConnectionPool = await create_pool(settings.database_dsn)
    if settings.auto_apply_schema:
        await apply_schema(pool)
    http_client = httpx.AsyncClient(timeout=10.0)
    app.state.db_pool = pool
    app.state.http_client = http_client
    app.state.catalog_service = ToolActionCatalogService(
        repository=PostgresToolActionRepository(pool),
        capabilities_client=CapabilitiesClient(
            base_url=settings.capabilities_api_url,
            http_client=http_client,
        ),
    )
    try:
        yield
    finally:
        await http_client.aclose()
        await pool.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    configure_structlog(log_level=resolved_settings.log_level, json=resolved_settings.json_logs)

    app = FastAPI(title="Tool Actions API", version="0.1.0", lifespan=_lifespan)
    app.state.settings = resolved_settings
    app.include_router(router)
    configure_telemetry(app, resolved_settings)

    @app.exception_handler(NotFoundError)
    async def _handle_not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _handle_conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def _handle_validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(DomainError)
    async def _handle_domain(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(pg_errors.UniqueViolation)
    async def _handle_unique(_: Request, exc: pg_errors.UniqueViolation) -> JSONResponse:
        detail = exc.diag.message_detail or str(exc)
        return JSONResponse(status_code=409, content={"detail": detail})

    @app.exception_handler(pg_errors.ForeignKeyViolation)
    @app.exception_handler(pg_errors.CheckViolation)
    @app.exception_handler(pg_errors.NotNullViolation)
    async def _handle_constraint(_: Request, exc: Exception) -> JSONResponse:
        diag = getattr(exc, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)
        detail = getattr(diag, "message_detail", None) or str(exc)
        if constraint_name:
            detail = f"{constraint_name}: {detail}"
        return JSONResponse(status_code=422, content={"detail": detail})

    return app


app = create_app()
