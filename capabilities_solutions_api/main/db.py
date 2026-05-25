from __future__ import annotations

from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


def schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "database" / "schema.sql"


async def create_pool(dsn: str) -> AsyncConnectionPool:
    pool = AsyncConnectionPool(
        conninfo=dsn,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await pool.open(wait=True)
    return pool


async def apply_schema(pool: AsyncConnectionPool) -> None:
    schema_sql = schema_path().read_text()
    async with pool.connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(schema_sql)
