from __future__ import annotations

from datetime import datetime
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from capabilities_solutions_api.app.ports.repository import CatalogRepository
from capabilities_solutions_api.domain.models import (
    AnyCapabilityDraft,
    Capability,
    ClassicAlgorithmCapability,
    ClassicAlgorithmCapabilityDraft,
    ModelCapability,
    ModelCapabilityDraft,
    SensorAssignment,
    SensorAssignmentDraft,
    Solution,
    SolutionDraft,
    SolutionStep,
    SolutionStepDraft,
)

_CAPABILITY_JOIN = """
    SELECT
        c.id, c.capability_type, c.algorithm, c.kind,
        c.user_params, c.internal_config, c.sha,
        c.created_at, c.updated_at,
        mc.model_name, mc.model_version, mc.confidence_threshold
    FROM capabilities c
    LEFT JOIN model_capabilities mc ON mc.capability_id = c.id
"""


def _capability_from_row(row: dict) -> Capability:
    base = dict(
        id=row["id"],
        capability_type=row["capability_type"],
        algorithm=row["algorithm"],
        kind=row["kind"],
        user_params=row["user_params"] or {},
        internal_config=row["internal_config"] or {},
        sha=row["sha"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
    if row["kind"] == "model":
        return ModelCapability(
            **base,
            model_name=row["model_name"],
            model_version=row["model_version"],
            confidence_threshold=row["confidence_threshold"],
        )
    return ClassicAlgorithmCapability(**base)


def _solution_from_row(row: dict) -> Solution:
    return Solution(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        user_params=row["user_params"] or {},
        internal_config=row["internal_config"] or {},
        version=row["version"],
        sha=row["sha"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _solution_step_from_row(row: dict) -> SolutionStep:
    return SolutionStep(
        id=row["id"],
        solution_id=row["solution_id"],
        step_id=row["step_id"],
        step_type=row["step_type"],
        capability_id=row["capability_id"],
        position=row["position"],
        depends_on=row["depends_on"] or [],
        user_params=row["user_params"] or {},
        internal_config=row["internal_config"] or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _sensor_assignment_from_row(row: dict) -> SensorAssignment:
    return SensorAssignment(
        id=row["id"],
        sensor_id=row["sensor_id"],
        solution_id=row["solution_id"],
        is_active=row["is_active"],
        config_overrides=row["config_overrides"] or {},
        solution_sha=row["solution_sha"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresCatalogRepository(CatalogRepository):
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def list_capabilities(
        self,
        capability_type: str | None = None,
        algorithm: str | None = None,
    ) -> list[Capability]:
        conditions: list[str] = []
        params: list[object] = []
        if capability_type:
            conditions.append("c.capability_type = %s")
            params.append(capability_type)
        if algorithm:
            conditions.append("c.algorithm = %s")
            params.append(algorithm)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"{_CAPABILITY_JOIN} {where} ORDER BY c.capability_type, c.algorithm"
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
        return [_capability_from_row(row) for row in rows]

    async def get_capability(self, capability_id: UUID) -> Capability | None:
        query = f"{_CAPABILITY_JOIN} WHERE c.id = %s"
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (capability_id,))
                row = await cur.fetchone()
        return _capability_from_row(row) if row else None

    async def get_capability_by_sha(self, sha: str) -> Capability | None:
        query = f"{_CAPABILITY_JOIN} WHERE c.sha = %s"
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (sha,))
                row = await cur.fetchone()
        return _capability_from_row(row) if row else None

    async def create_capability(self, draft: AnyCapabilityDraft) -> Capability:
        kind = "model" if isinstance(draft, ModelCapabilityDraft) else "classic_algorithm"
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO capabilities (
                            capability_type, algorithm, kind, user_params, internal_config, sha
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            draft.capability_type,
                            draft.algorithm,
                            kind,
                            Jsonb(draft.user_params),
                            Jsonb(draft.internal_config),
                            draft.sha,
                        ),
                    )
                    base_row = await cur.fetchone()
                    if isinstance(draft, ModelCapabilityDraft):
                        await cur.execute(
                            """
                            INSERT INTO model_capabilities (
                                capability_id, model_name, model_version, confidence_threshold
                            )
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                base_row["id"],
                                draft.model_name,
                                draft.model_version,
                                draft.confidence_threshold,
                            ),
                        )
                        row = {**base_row, "model_name": draft.model_name, "model_version": draft.model_version, "confidence_threshold": draft.confidence_threshold}
                    else:
                        await cur.execute(
                            "INSERT INTO classic_algorithm_capabilities (capability_id) VALUES (%s)",
                            (base_row["id"],),
                        )
                        row = {**base_row, "model_name": None, "model_version": None, "confidence_threshold": None}
        return _capability_from_row(row)

    async def update_capability(
        self,
        capability_id: UUID,
        draft: AnyCapabilityDraft,
    ) -> Capability:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE capabilities
                        SET user_params = %s,
                            sha = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (
                            Jsonb(draft.user_params),
                            draft.sha,
                            capability_id,
                        ),
                    )
                    base_row = await cur.fetchone()
                    if isinstance(draft, ModelCapabilityDraft):
                        await cur.execute(
                            """
                            UPDATE model_capabilities
                            SET confidence_threshold = %s
                            WHERE capability_id = %s
                            """,
                            (draft.confidence_threshold, capability_id),
                        )
                        row = {**base_row, "model_name": draft.model_name, "model_version": draft.model_version, "confidence_threshold": draft.confidence_threshold}
                    else:
                        row = {**base_row, "model_name": None, "model_version": None, "confidence_threshold": None}
        return _capability_from_row(row)

    async def get_capabilities(self, capability_ids: list[UUID]) -> dict[UUID, Capability]:
        if not capability_ids:
            return {}
        query = f"{_CAPABILITY_JOIN} WHERE c.id = ANY(%s)"
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (capability_ids,))
                rows = await cur.fetchall()
        capabilities = [_capability_from_row(row) for row in rows]
        return {cap.id: cap for cap in capabilities}

    async def list_solution_ids_for_capability(self, capability_id: UUID) -> list[UUID]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT DISTINCT solution_id
                    FROM solution_steps
                    WHERE capability_id = %s
                    ORDER BY solution_id
                    """,
                    (capability_id,),
                )
                rows = await cur.fetchall()
        return [row["solution_id"] for row in rows]

    async def list_solutions(self, name: str | None = None) -> list[Solution]:
        params: tuple[object, ...] = ()
        query = "SELECT * FROM solutions"
        if name:
            query += " WHERE name = %s"
            params = (name,)
        query += " ORDER BY name"
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                rows = await cur.fetchall()
        return [_solution_from_row(row) for row in rows]

    async def get_solution(self, solution_id: UUID) -> Solution | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute("SELECT * FROM solutions WHERE id = %s", (solution_id,))
                row = await cur.fetchone()
        return _solution_from_row(row) if row else None

    async def get_solution_by_name_or_alias(self, name: str) -> Solution | None:
        query = """
            SELECT *
            FROM solutions
            WHERE name = %s
               OR (internal_config -> 'legacy_aliases') ? %s
            LIMIT 1
        """
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, (name, name))
                row = await cur.fetchone()
        return _solution_from_row(row) if row else None

    async def create_solution(
        self,
        draft: SolutionDraft,
        steps: list[SolutionStepDraft],
    ) -> Solution:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO solutions (name, description, user_params, internal_config, version, sha)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING *
                        """,
                        (
                            draft.name,
                            draft.description,
                            Jsonb(draft.user_params),
                            Jsonb(draft.internal_config),
                            draft.version,
                            draft.sha,
                        ),
                    )
                    row = await cur.fetchone()
                    solution = _solution_from_row(row)
                    await self._insert_steps(cur, solution.id, steps)
        return solution

    async def update_solution(
        self,
        solution_id: UUID,
        draft: SolutionDraft,
        steps: list[SolutionStepDraft],
    ) -> Solution:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE solutions
                        SET description = %s,
                            user_params = %s,
                            internal_config = %s,
                            version = %s,
                            sha = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (
                            draft.description,
                            Jsonb(draft.user_params),
                            Jsonb(draft.internal_config),
                            draft.version,
                            draft.sha,
                            solution_id,
                        ),
                    )
                    row = await cur.fetchone()
                    await cur.execute("DELETE FROM solution_steps WHERE solution_id = %s", (solution_id,))
                    await self._insert_steps(cur, solution_id, steps)
        return _solution_from_row(row)

    async def update_solution_sha(self, solution_id: UUID, sha: str) -> Solution:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE solutions
                        SET sha = %s,
                            updated_at = NOW()
                        WHERE id = %s
                        RETURNING *
                        """,
                        (sha, solution_id),
                    )
                    row = await cur.fetchone()
        return _solution_from_row(row)

    async def delete_solution(self, solution_id: UUID) -> None:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        DELETE FROM sensor_assignments
                        WHERE solution_id = %s AND is_active = FALSE
                        """,
                        (solution_id,),
                    )
                    await cur.execute("DELETE FROM solutions WHERE id = %s", (solution_id,))

    async def get_solution_steps(self, solution_id: UUID) -> list[SolutionStep]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM solution_steps WHERE solution_id = %s ORDER BY position",
                    (solution_id,),
                )
                rows = await cur.fetchall()
        return [_solution_step_from_row(row) for row in rows]

    async def has_active_assignments(self, solution_id: UUID) -> bool:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM sensor_assignments
                        WHERE solution_id = %s AND is_active = TRUE
                    ) AS has_active
                    """,
                    (solution_id,),
                )
                row = await cur.fetchone()
        return bool(row["has_active"])

    async def list_sensor_assignments(self, sensor_id: str) -> list[SensorAssignment]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT * FROM sensor_assignments
                    WHERE sensor_id = %s
                    ORDER BY created_at
                    """,
                    (sensor_id,),
                )
                rows = await cur.fetchall()
        return [_sensor_assignment_from_row(row) for row in rows]

    async def get_sensor_assignment(
        self,
        sensor_id: str,
        assignment_id: UUID,
    ) -> SensorAssignment | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT * FROM sensor_assignments
                    WHERE sensor_id = %s AND id = %s
                    """,
                    (sensor_id, assignment_id),
                )
                row = await cur.fetchone()
        return _sensor_assignment_from_row(row) if row else None

    async def create_sensor_assignment(
        self,
        draft: SensorAssignmentDraft,
    ) -> SensorAssignment:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO sensor_assignments (
                            sensor_id, solution_id, is_active, config_overrides, solution_sha
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (sensor_id, solution_id)
                        DO UPDATE SET
                            is_active = EXCLUDED.is_active,
                            config_overrides = EXCLUDED.config_overrides,
                            solution_sha = EXCLUDED.solution_sha,
                            updated_at = NOW()
                        RETURNING *
                        """,
                        (
                            draft.sensor_id,
                            draft.solution_id,
                            draft.is_active,
                            Jsonb(draft.config_overrides),
                            draft.solution_sha,
                        ),
                    )
                    row = await cur.fetchone()
        return _sensor_assignment_from_row(row)

    async def update_sensor_assignment(
        self,
        sensor_id: str,
        assignment_id: UUID,
        draft: SensorAssignmentDraft,
    ) -> SensorAssignment:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE sensor_assignments
                        SET is_active = %s,
                            config_overrides = %s,
                            solution_sha = %s,
                            updated_at = NOW()
                        WHERE sensor_id = %s AND id = %s
                        RETURNING *
                        """,
                        (
                            draft.is_active,
                            Jsonb(draft.config_overrides),
                            draft.solution_sha,
                            sensor_id,
                            assignment_id,
                        ),
                    )
                    row = await cur.fetchone()
        return _sensor_assignment_from_row(row)

    async def delete_sensor_assignment(self, sensor_id: str, assignment_id: UUID) -> None:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        "DELETE FROM sensor_assignments WHERE sensor_id = %s AND id = %s",
                        (sensor_id, assignment_id),
                    )

    async def _insert_steps(
        self,
        cursor,
        solution_id: UUID,
        steps: list[SolutionStepDraft],
    ) -> None:
        for step in steps:
            await cursor.execute(
                """
                INSERT INTO solution_steps (
                    solution_id,
                    step_id,
                    step_type,
                    capability_id,
                    position,
                    depends_on,
                    user_params,
                    internal_config
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    solution_id,
                    step.step_id,
                    step.step_type,
                    step.capability_id,
                    step.position,
                    step.depends_on,
                    Jsonb(step.user_params),
                    Jsonb(step.internal_config),
                ),
            )
