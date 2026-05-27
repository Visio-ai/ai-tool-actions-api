from __future__ import annotations

from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from capabilities_solutions_api.app.ports.repository import ToolActionRepository
from capabilities_solutions_api.domain.models import (
    ActionStep,
    ActionStepDraft,
    SensorAssignment,
    SensorAssignmentDraft,
    ToolAction,
    ToolActionDraft,
    ToolActionSLA,
)


def _sla_from_row(row: dict) -> ToolActionSLA:
    return ToolActionSLA(
        delivery_mode=row["delivery_mode"],
        sla_seconds=row["sla_seconds"],
        notes=row["notes"] or "",
    )


def _step_from_row(row: dict) -> ActionStep:
    return ActionStep(
        id=row["id"],
        tool_action_id=row["tool_action_id"],
        step_id=row["step_id"],
        step_type=row["step_type"],
        capability_id=row["capability_id"],
        capability_sha=row["capability_sha"] or "",
        position=row["position"],
        depends_on=row["depends_on"] or [],
        user_params=row["user_params"] or {},
        internal_config=row["internal_config"] or {},
        created_at=row["created_at"],
    )


def _assignment_from_row(row: dict) -> SensorAssignment:
    return SensorAssignment(
        id=row["id"],
        sensor_id=row["sensor_id"],
        tool_action_id=row["tool_action_id"],
        is_active=row["is_active"],
        config_overrides=row["config_overrides"] or {},
        tool_action_sha=row["tool_action_sha"] or "",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _tool_action_from_row(
    row: dict,
    slas: list[ToolActionSLA],
    steps: list[ActionStep],
) -> ToolAction:
    return ToolAction(
        id=row["id"],
        name=row["name"],
        display_name=row["display_name"] or "",
        category=row["category"] or "",
        status=row["status"],
        sensor_type=row["sensor_type"],
        supported_modes=row["supported_modes"] or [],
        setup=row["setup"] or {},
        output_schema_ref=row["output_schema_ref"] or "",
        use_cases=row["use_cases"] or "",
        technical_overview=row["technical_overview"] or "",
        limitations=row["limitations"] or "",
        version=row["version"],
        sha=row["sha"],
        user_params=row["user_params"] or {},
        internal_config=row["internal_config"] or {},
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        slas=slas,
        steps=steps,
    )


class PostgresToolActionRepository(ToolActionRepository):
    def __init__(self, pool: AsyncConnectionPool) -> None:
        self.pool = pool

    async def list_tool_actions(
        self,
        status: str | None = None,
        sensor_type: str | None = None,
        category: str | None = None,
    ) -> list[ToolAction]:
        conditions: list[str] = []
        params: list[object] = []
        if status:
            conditions.append("status = %s")
            params.append(status)
        if sensor_type:
            conditions.append("sensor_type = %s")
            params.append(sensor_type)
        if category:
            conditions.append("category = %s")
            params.append(category)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"SELECT * FROM tool_actions {where} ORDER BY name",
                    params,
                )
                rows = await cur.fetchall()
        result: list[ToolAction] = []
        for row in rows:
            slas = await self._get_slas(row["id"])
            steps = await self._get_steps(row["id"])
            result.append(_tool_action_from_row(row, slas, steps))
        return result

    async def get_tool_action(self, tool_action_id: UUID) -> ToolAction | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM tool_actions WHERE id = %s",
                    (tool_action_id,),
                )
                row = await cur.fetchone()
        if row is None:
            return None
        slas = await self._get_slas(row["id"])
        steps = await self._get_steps(row["id"])
        return _tool_action_from_row(row, slas, steps)

    async def get_tool_action_by_name(self, name: str) -> ToolAction | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM tool_actions WHERE name = %s",
                    (name,),
                )
                row = await cur.fetchone()
        if row is None:
            return None
        slas = await self._get_slas(row["id"])
        steps = await self._get_steps(row["id"])
        return _tool_action_from_row(row, slas, steps)

    async def get_tool_action_by_sha(self, sha: str) -> ToolAction | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM tool_actions WHERE sha = %s",
                    (sha,),
                )
                row = await cur.fetchone()
        if row is None:
            return None
        slas = await self._get_slas(row["id"])
        steps = await self._get_steps(row["id"])
        return _tool_action_from_row(row, slas, steps)

    async def create_tool_action(self, draft: ToolActionDraft) -> ToolAction:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        INSERT INTO tool_actions (
                            name, display_name, category, status, sensor_type,
                            supported_modes, setup, output_schema_ref,
                            use_cases, technical_overview, limitations,
                            sha, user_params, internal_config
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING *
                        """,
                        (
                            draft.name,
                            draft.display_name,
                            draft.category,
                            draft.status,
                            draft.sensor_type,
                            draft.supported_modes,
                            Jsonb(draft.setup),
                            draft.output_schema_ref,
                            draft.use_cases,
                            draft.technical_overview,
                            draft.limitations,
                            draft.sha,
                            Jsonb(draft.user_params),
                            Jsonb(draft.internal_config),
                        ),
                    )
                    ta_row = await cur.fetchone()
                    ta_id = ta_row["id"]

                    for sla in draft.slas:
                        await cur.execute(
                            """
                            INSERT INTO tool_action_slas (tool_action_id, delivery_mode, sla_seconds, notes)
                            VALUES (%s,%s,%s,%s)
                            """,
                            (ta_id, sla.delivery_mode, sla.sla_seconds, sla.notes),
                        )

                    for step in draft.steps:
                        await cur.execute(
                            """
                            INSERT INTO action_steps (
                                tool_action_id, step_id, step_type,
                                capability_id, capability_sha,
                                position, depends_on, user_params, internal_config
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                ta_id,
                                step.step_id,
                                step.step_type,
                                step.capability_id,
                                step.capability_sha,
                                step.position,
                                step.depends_on,
                                Jsonb(step.user_params),
                                Jsonb(step.internal_config),
                            ),
                        )

        return await self.get_tool_action(ta_id)  # type: ignore[return-value]

    async def update_tool_action(
        self,
        tool_action_id: UUID,
        draft: ToolActionDraft,
    ) -> ToolAction:
        async with self.pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(
                        """
                        UPDATE tool_actions
                        SET display_name = %s, category = %s, status = %s,
                            sensor_type = %s, supported_modes = %s, setup = %s,
                            output_schema_ref = %s, use_cases = %s,
                            technical_overview = %s, limitations = %s,
                            sha = %s, user_params = %s, internal_config = %s,
                            version = version + 1, updated_at = NOW()
                        WHERE id = %s
                        """,
                        (
                            draft.display_name,
                            draft.category,
                            draft.status,
                            draft.sensor_type,
                            draft.supported_modes,
                            Jsonb(draft.setup),
                            draft.output_schema_ref,
                            draft.use_cases,
                            draft.technical_overview,
                            draft.limitations,
                            draft.sha,
                            Jsonb(draft.user_params),
                            Jsonb(draft.internal_config),
                            tool_action_id,
                        ),
                    )

                    await cur.execute(
                        "DELETE FROM tool_action_slas WHERE tool_action_id = %s",
                        (tool_action_id,),
                    )
                    for sla in draft.slas:
                        await cur.execute(
                            """
                            INSERT INTO tool_action_slas (tool_action_id, delivery_mode, sla_seconds, notes)
                            VALUES (%s,%s,%s,%s)
                            """,
                            (tool_action_id, sla.delivery_mode, sla.sla_seconds, sla.notes),
                        )

                    await cur.execute(
                        "DELETE FROM action_steps WHERE tool_action_id = %s",
                        (tool_action_id,),
                    )
                    for step in draft.steps:
                        await cur.execute(
                            """
                            INSERT INTO action_steps (
                                tool_action_id, step_id, step_type,
                                capability_id, capability_sha,
                                position, depends_on, user_params, internal_config
                            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """,
                            (
                                tool_action_id,
                                step.step_id,
                                step.step_type,
                                step.capability_id,
                                step.capability_sha,
                                step.position,
                                step.depends_on,
                                Jsonb(step.user_params),
                                Jsonb(step.internal_config),
                            ),
                        )

        return await self.get_tool_action(tool_action_id)  # type: ignore[return-value]

    async def delete_tool_action(self, tool_action_id: UUID) -> None:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM tool_actions WHERE id = %s",
                    (tool_action_id,),
                )

    async def get_steps(self, tool_action_id: UUID) -> list[ActionStep]:
        return await self._get_steps(tool_action_id)

    async def _get_slas(self, tool_action_id: UUID) -> list[ToolActionSLA]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM tool_action_slas WHERE tool_action_id = %s ORDER BY delivery_mode",
                    (tool_action_id,),
                )
                rows = await cur.fetchall()
        return [_sla_from_row(r) for r in rows]

    async def _get_steps(self, tool_action_id: UUID) -> list[ActionStep]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM action_steps WHERE tool_action_id = %s ORDER BY position",
                    (tool_action_id,),
                )
                rows = await cur.fetchall()
        return [_step_from_row(r) for r in rows]

    async def list_sensor_assignments(self, sensor_id: str) -> list[SensorAssignment]:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM sensor_assignments WHERE sensor_id = %s ORDER BY created_at",
                    (sensor_id,),
                )
                rows = await cur.fetchall()
        return [_assignment_from_row(r) for r in rows]

    async def get_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
    ) -> SensorAssignment | None:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT * FROM sensor_assignments WHERE sensor_id = %s AND tool_action_id = %s",
                    (sensor_id, tool_action_id),
                )
                row = await cur.fetchone()
        return _assignment_from_row(row) if row else None

    async def create_sensor_assignment(
        self,
        draft: SensorAssignmentDraft,
        tool_action_sha: str,
    ) -> SensorAssignment:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO sensor_assignments (
                        sensor_id, tool_action_id, is_active, config_overrides, tool_action_sha
                    ) VALUES (%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        draft.sensor_id,
                        draft.tool_action_id,
                        draft.is_active,
                        Jsonb(draft.config_overrides),
                        tool_action_sha,
                    ),
                )
                row = await cur.fetchone()
        return _assignment_from_row(row)  # type: ignore[arg-type]

    async def update_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
        is_active: bool,
        config_overrides: dict,
    ) -> SensorAssignment:
        async with self.pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE sensor_assignments
                    SET is_active = %s, config_overrides = %s, updated_at = NOW()
                    WHERE sensor_id = %s AND tool_action_id = %s
                    RETURNING *
                    """,
                    (is_active, Jsonb(config_overrides), sensor_id, tool_action_id),
                )
                row = await cur.fetchone()
        return _assignment_from_row(row)  # type: ignore[arg-type]

    async def delete_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
    ) -> None:
        async with self.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM sensor_assignments WHERE sensor_id = %s AND tool_action_id = %s",
                    (sensor_id, tool_action_id),
                )
