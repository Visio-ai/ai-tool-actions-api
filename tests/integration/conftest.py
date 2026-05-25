from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg_pool import AsyncConnectionPool
from testcontainers.postgres import PostgresContainer

from capabilities_solutions_api.adapters.repositories.postgres import PostgresCatalogRepository
from capabilities_solutions_api.main.settings import Settings


SCHEMA_PATH = Path(__file__).resolve().parents[2] / "database" / "schema.sql"


def _reset_database(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS public CASCADE")
        conn.execute("CREATE SCHEMA public")


def _apply_schema(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


async def _create_pool(dsn: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(conninfo=dsn, open=False)
    await pool.open()
    return pool


@pytest.fixture(scope="session")
def test_settings() -> Iterator[Settings]:
    with PostgresContainer("postgres:17") as postgres:
        yield Settings(
            database_dsn=postgres.get_connection_url().replace("+psycopg2", ""),
            auto_apply_schema=True,
            json_logs=False,
        )


@pytest.fixture()
def app(test_settings: Settings) -> Iterator[FastAPI]:
    from capabilities_solutions_api.main.app import create_app

    _reset_database(test_settings.database_dsn)
    yield create_app(test_settings)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture()
async def repository(test_settings: Settings) -> Iterator[PostgresCatalogRepository]:
    _reset_database(test_settings.database_dsn)
    _apply_schema(test_settings.database_dsn)

    pool = await _create_pool(test_settings.database_dsn)
    try:
        yield PostgresCatalogRepository(pool)
    finally:
        await pool.close()
