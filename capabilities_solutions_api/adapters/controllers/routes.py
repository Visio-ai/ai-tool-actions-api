from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from capabilities_solutions_api.adapters.controllers.schemas import (
    HealthResponse,
    SensorAssignmentCreateRequest,
    SensorAssignmentResponse,
    SensorAssignmentUpdateRequest,
    ToolActionCreateRequest,
    ToolActionResponse,
    ToolActionUpdateRequest,
)
from capabilities_solutions_api.app.use_cases.catalog_service import ToolActionCatalogService
from capabilities_solutions_api.domain.models import ToolActionDraft

router = APIRouter()


def _service(request: Request) -> ToolActionCatalogService:
    return request.app.state.catalog_service


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


# ─── ToolActions ──────────────────────────────────────────────────────────────

@router.get("/tool-actions", response_model=list[ToolActionResponse])
async def list_tool_actions(
    request: Request,
    status: str | None = None,
    sensor_type: str | None = None,
    category: str | None = None,
) -> list[ToolActionResponse]:
    tas = await _service(request).list_tool_actions(status, sensor_type, category)
    return [ToolActionResponse.from_entity(ta) for ta in tas]


@router.get("/tool-actions/{tool_action_id}", response_model=ToolActionResponse)
async def get_tool_action(
    request: Request,
    tool_action_id: UUID,
) -> ToolActionResponse:
    ta = await _service(request).get_tool_action(tool_action_id)
    return ToolActionResponse.from_entity(ta)


@router.post(
    "/tool-actions",
    response_model=ToolActionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_tool_action(
    request: Request,
    payload: ToolActionCreateRequest,
) -> ToolActionResponse:
    draft = payload.to_draft()
    ta = await _service(request).create_tool_action(draft)
    return ToolActionResponse.from_entity(ta)


@router.patch("/tool-actions/{tool_action_id}", response_model=ToolActionResponse)
async def update_tool_action(
    request: Request,
    tool_action_id: UUID,
    payload: ToolActionUpdateRequest,
) -> ToolActionResponse:
    svc = _service(request)
    current = await svc.get_tool_action(tool_action_id)

    draft = ToolActionDraft(
        name=current.name,
        display_name=payload.display_name if payload.display_name is not None else current.display_name,
        category=payload.category if payload.category is not None else current.category,
        status=payload.status if payload.status is not None else current.status,
        sensor_type=payload.sensor_type if payload.sensor_type is not None else current.sensor_type,
        supported_modes=list(payload.supported_modes) if payload.supported_modes is not None else list(current.supported_modes),
        setup=dict(payload.setup) if payload.setup is not None else dict(current.setup),
        output_schema_ref=payload.output_schema_ref if payload.output_schema_ref is not None else current.output_schema_ref,
        use_cases=payload.use_cases if payload.use_cases is not None else current.use_cases,
        technical_overview=payload.technical_overview if payload.technical_overview is not None else current.technical_overview,
        limitations=payload.limitations if payload.limitations is not None else current.limitations,
        user_params=dict(payload.user_params) if payload.user_params is not None else dict(current.user_params),
        internal_config=dict(payload.internal_config) if payload.internal_config is not None else dict(current.internal_config),
        slas=[s.to_domain() for s in payload.slas] if payload.slas is not None else list(current.slas),
        steps=(
            [s.to_draft() for s in payload.steps]
            if payload.steps is not None
            else [
                _step_to_draft(s)
                for s in current.steps
            ]
        ),
    )
    updated = await svc.update_tool_action(tool_action_id, draft)
    return ToolActionResponse.from_entity(updated)


@router.delete("/tool-actions/{tool_action_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_action(
    request: Request,
    tool_action_id: UUID,
) -> None:
    await _service(request).delete_tool_action(tool_action_id)


@router.get("/tool-actions/{tool_action_id}/config")
async def get_tool_action_config(
    request: Request,
    tool_action_id: UUID,
) -> dict:
    return await _service(request).get_config(tool_action_id)


@router.get("/tool-actions/{tool_action_id}/pricing")
async def get_tool_action_pricing(
    request: Request,
    tool_action_id: UUID,
) -> dict:
    import dataclasses
    pricing = await _service(request).get_pricing(tool_action_id)
    return dataclasses.asdict(pricing)


@router.get("/internal/tool-actions/by-name/{name}", response_model=ToolActionResponse)
async def get_tool_action_by_name(
    request: Request,
    name: str,
) -> ToolActionResponse:
    ta = await _service(request).get_tool_action_by_name(name)
    return ToolActionResponse.from_entity(ta)


# ─── SensorAssignments ────────────────────────────────────────────────────────

@router.get(
    "/sensors/{sensor_id}/tool-actions",
    response_model=list[SensorAssignmentResponse],
)
async def list_sensor_assignments(
    request: Request,
    sensor_id: str,
) -> list[SensorAssignmentResponse]:
    assignments = await _service(request).list_sensor_assignments(sensor_id)
    return [SensorAssignmentResponse.from_entity(a) for a in assignments]


@router.post(
    "/sensors/{sensor_id}/tool-actions",
    response_model=SensorAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensor_assignment(
    request: Request,
    sensor_id: str,
    payload: SensorAssignmentCreateRequest,
) -> SensorAssignmentResponse:
    draft = payload.to_draft(sensor_id)
    assignment = await _service(request).create_sensor_assignment(draft)
    return SensorAssignmentResponse.from_entity(assignment)


@router.get(
    "/sensors/{sensor_id}/tool-actions/{tool_action_id}",
    response_model=SensorAssignmentResponse,
)
async def get_sensor_assignment(
    request: Request,
    sensor_id: str,
    tool_action_id: UUID,
) -> SensorAssignmentResponse:
    assignment = await _service(request).get_sensor_assignment(sensor_id, tool_action_id)
    return SensorAssignmentResponse.from_entity(assignment)


@router.patch(
    "/sensors/{sensor_id}/tool-actions/{tool_action_id}",
    response_model=SensorAssignmentResponse,
)
async def update_sensor_assignment(
    request: Request,
    sensor_id: str,
    tool_action_id: UUID,
    payload: SensorAssignmentUpdateRequest,
) -> SensorAssignmentResponse:
    assignment = await _service(request).update_sensor_assignment(
        sensor_id,
        tool_action_id,
        payload.is_active,
        payload.config_overrides,
    )
    return SensorAssignmentResponse.from_entity(assignment)


@router.delete(
    "/sensors/{sensor_id}/tool-actions/{tool_action_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sensor_assignment(
    request: Request,
    sensor_id: str,
    tool_action_id: UUID,
) -> None:
    await _service(request).delete_sensor_assignment(sensor_id, tool_action_id)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _step_to_draft(step):
    from capabilities_solutions_api.domain.models import ActionStepDraft
    return ActionStepDraft(
        step_id=step.step_id,
        step_type=step.step_type,
        capability_id=step.capability_id,
        capability_sha=step.capability_sha,
        position=step.position,
        depends_on=list(step.depends_on),
        user_params=dict(step.user_params),
        internal_config=dict(step.internal_config),
    )
