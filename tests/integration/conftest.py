from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from testcontainers.postgres import PostgresContainer

from capabilities_solutions_api.adapters.capabilities_client import CapabilitySnapshot
from capabilities_solutions_api.adapters.repositories.postgres import PostgresToolActionRepository
from capabilities_solutions_api.app.use_cases.catalog_service import ToolActionCatalogService
from capabilities_solutions_api.main.app import create_app
from capabilities_solutions_api.main.settings import Settings


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17") as pg:
        yield pg


@pytest.fixture
def mock_capabilities_client():
    client = AsyncMock()
    client.get = AsyncMock(
        return_value=CapabilitySnapshot(
            id=uuid4(),
            kind="model",
            sha="mock_sha_resolve",
            cost={"cost_type": "per_frame", "unit_cost_usd": 0.000002},
        )
    )
    client.get_by_sha = AsyncMock(return_value=None)
    return client


@pytest.fixture
async def app(postgres_container, mock_capabilities_client):
    settings = Settings(
        database_dsn=postgres_container.get_connection_url().replace("postgresql+psycopg2", "postgresql"),
        capabilities_api_url="http://mock-capabilities-api",
        auto_apply_schema=True,
        json_logs=False,
    )
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        application.state.catalog_service = ToolActionCatalogService(
            repository=PostgresToolActionRepository(application.state.db_pool),
            capabilities_client=mock_capabilities_client,
        )
        yield application


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
