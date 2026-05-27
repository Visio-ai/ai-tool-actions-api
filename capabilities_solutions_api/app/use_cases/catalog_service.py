from __future__ import annotations

from uuid import UUID

from capabilities_solutions_api.adapters.capabilities_client import CapabilitiesClient
from capabilities_solutions_api.app.ports.repository import ToolActionRepository
from capabilities_solutions_api.domain.errors import ConflictError, NotFoundError, ValidationError
from capabilities_solutions_api.domain.models import (
    InferenceCost,
    SensorAssignment,
    SensorAssignmentDraft,
    StepCostBreakdown,
    ToolAction,
    ToolActionDraft,
    ToolActionPricing,
)
from capabilities_solutions_api.domain.sha import compute_tool_action_sha

VALID_STATUSES = {"draft", "active", "deprecated"}
VALID_STEP_TYPES = {"model", "classic_algorithm", "service"}


class ToolActionCatalogService:
    def __init__(
        self,
        repository: ToolActionRepository,
        capabilities_client: CapabilitiesClient,
    ) -> None:
        self.repository = repository
        self.capabilities_client = capabilities_client

    async def list_tool_actions(
        self,
        status: str | None = None,
        sensor_type: str | None = None,
        category: str | None = None,
    ) -> list[ToolAction]:
        return await self.repository.list_tool_actions(status, sensor_type, category)

    async def get_tool_action(self, tool_action_id: UUID) -> ToolAction:
        ta = await self.repository.get_tool_action(tool_action_id)
        if ta is None:
            raise NotFoundError(f"ToolAction {tool_action_id} not found")
        return ta

    async def get_tool_action_by_name(self, name: str) -> ToolAction:
        ta = await self.repository.get_tool_action_by_name(name)
        if ta is None:
            raise NotFoundError(f"ToolAction '{name}' not found")
        return ta

    async def create_tool_action(self, draft: ToolActionDraft) -> ToolAction:
        _validate_draft(draft)
        await _resolve_capability_shas(draft, self.capabilities_client)
        draft.sha = compute_tool_action_sha(draft)
        existing = await self.repository.get_tool_action_by_sha(draft.sha)
        if existing is not None:
            raise ConflictError(f"ToolAction sha={draft.sha} already exists")
        return await self.repository.create_tool_action(draft)

    async def update_tool_action(
        self,
        tool_action_id: UUID,
        draft: ToolActionDraft,
    ) -> ToolAction:
        await self.get_tool_action(tool_action_id)
        _validate_draft(draft)
        await _resolve_capability_shas(draft, self.capabilities_client)
        draft.sha = compute_tool_action_sha(draft)
        return await self.repository.update_tool_action(tool_action_id, draft)

    async def delete_tool_action(self, tool_action_id: UUID) -> None:
        await self.get_tool_action(tool_action_id)
        await self.repository.delete_tool_action(tool_action_id)

    async def get_config(self, tool_action_id: UUID) -> dict:
        ta = await self.get_tool_action(tool_action_id)
        return {
            "tool_action_id": str(tool_action_id),
            "name": ta.name,
            "sha": ta.sha,
            "sensor_type": ta.sensor_type,
            "supported_modes": ta.supported_modes,
            "setup": ta.setup,
            "output_schema_ref": ta.output_schema_ref,
            "user_params": ta.user_params,
            "internal_config": ta.internal_config,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_type": s.step_type,
                    "capability_id": str(s.capability_id) if s.capability_id else None,
                    "capability_sha": s.capability_sha,
                    "position": s.position,
                    "depends_on": s.depends_on,
                    "user_params": s.user_params,
                    "internal_config": s.internal_config,
                }
                for s in ta.steps
            ],
        }

    async def get_pricing(self, tool_action_id: UUID) -> ToolActionPricing:
        ta = await self.get_tool_action(tool_action_id)
        breakdown: list[StepCostBreakdown] = []

        for step in ta.steps:
            if step.capability_id is None:
                continue
            try:
                snap = await self.capabilities_client.get(step.capability_id)
            except NotFoundError:
                breakdown.append(StepCostBreakdown(
                    step_id=step.step_id,
                    capability_id=step.capability_id,
                    cost=None,
                    error="capability not found",
                ))
                continue
            breakdown.append(StepCostBreakdown(
                step_id=step.step_id,
                capability_id=step.capability_id,
                cost=snap.cost,
            ))

        totals = InferenceCost()
        for entry in breakdown:
            if entry.cost:
                totals = InferenceCost(
                    hardware=totals.hardware or entry.cost.hardware,
                    rate_per_hour_usd=totals.rate_per_hour_usd + entry.cost.rate_per_hour_usd,
                    inference_time_ms_per_frame=totals.inference_time_ms_per_frame + entry.cost.inference_time_ms_per_frame,
                    cost_per_frame_usd=totals.cost_per_frame_usd + entry.cost.cost_per_frame_usd,
                    cost_per_camera_day_usd_at_15fps=totals.cost_per_camera_day_usd_at_15fps + entry.cost.cost_per_camera_day_usd_at_15fps,
                )

        return ToolActionPricing(
            tool_action_id=tool_action_id,
            breakdown=breakdown,
            totals=totals,
        )

    async def list_sensor_assignments(self, sensor_id: str) -> list[SensorAssignment]:
        return await self.repository.list_sensor_assignments(sensor_id)

    async def get_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
    ) -> SensorAssignment:
        sa = await self.repository.get_sensor_assignment(sensor_id, tool_action_id)
        if sa is None:
            raise NotFoundError(
                f"SensorAssignment sensor={sensor_id} tool_action={tool_action_id} not found"
            )
        return sa

    async def create_sensor_assignment(
        self,
        draft: SensorAssignmentDraft,
    ) -> SensorAssignment:
        ta = await self.get_tool_action(draft.tool_action_id)
        existing = await self.repository.get_sensor_assignment(
            draft.sensor_id, draft.tool_action_id
        )
        if existing is not None:
            raise ConflictError(
                f"SensorAssignment sensor={draft.sensor_id} tool_action={draft.tool_action_id} already exists"
            )
        return await self.repository.create_sensor_assignment(draft, ta.sha)

    async def update_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
        is_active: bool | None,
        config_overrides: dict | None,
    ) -> SensorAssignment:
        current = await self.get_sensor_assignment(sensor_id, tool_action_id)
        return await self.repository.update_sensor_assignment(
            sensor_id,
            tool_action_id,
            is_active if is_active is not None else current.is_active,
            config_overrides if config_overrides is not None else dict(current.config_overrides),
        )

    async def delete_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
    ) -> None:
        await self.get_sensor_assignment(sensor_id, tool_action_id)
        await self.repository.delete_sensor_assignment(sensor_id, tool_action_id)


def _validate_draft(draft: ToolActionDraft) -> None:
    if not draft.name:
        raise ValidationError("name is required")
    for step in draft.steps:
        if step.step_type not in VALID_STEP_TYPES:
            raise ValidationError(
                f"step {step.step_id!r}: invalid step_type {step.step_type!r}"
            )


async def _resolve_capability_shas(
    draft: ToolActionDraft,
    client: CapabilitiesClient,
) -> None:
    for step in draft.steps:
        if step.capability_id is not None and not step.capability_sha:
            snap = await client.get(step.capability_id)
            step.capability_sha = snap.sha
