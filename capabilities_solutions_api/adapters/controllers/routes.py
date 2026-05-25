from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response, status

from capabilities_solutions_api.adapters.controllers.schemas import (
    SensorAssignmentCreateRequest,
    SensorAssignmentResponse,
    SensorAssignmentUpdateRequest,
    CapabilityCreateRequest,
    CapabilityInternalConfigResponse,
    CapabilityResponse,
    CapabilitySchemaResponse,
    CapabilityUpdateRequest,
    HealthResponse,
    SolutionCreateRequest,
    SolutionResponse,
    SolutionUpdateRequest,
)
from capabilities_solutions_api.app.use_cases.catalog_service import CatalogService
from capabilities_solutions_api.domain.models import (
    ClassicAlgorithmCapabilityDraft,
    ModelCapabilityDraft,
    SensorAssignmentDraft,
    SolutionDraft,
    SolutionStepDraft,
)

router = APIRouter()


def _service(request: Request) -> CatalogService:
    return request.app.state.catalog_service


def _solution_step_drafts(steps) -> list[SolutionStepDraft]:
    return [
        SolutionStepDraft(
            step_id=step.step_id,
            step_type=step.step_type,
            capability_id=step.capability_id,
            position=index,
            depends_on=list(step.depends_on),
            user_params=dict(step.user_params),
        )
        for index, step in enumerate(steps)
    ]


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/capabilities", response_model=list[CapabilityResponse])
async def list_capabilities(
    request: Request,
    capability_type: str | None = None,
    algorithm: str | None = None,
) -> list[CapabilityResponse]:
    service = _service(request)
    capabilities = await service.list_capabilities(capability_type, algorithm)
    return [CapabilityResponse.from_entity(item) for item in capabilities]


@router.get("/capabilities/{capability_id}", response_model=CapabilityResponse)
async def get_capability(request: Request, capability_id: UUID) -> CapabilityResponse:
    service = _service(request)
    capability = await service.get_capability(capability_id)
    return CapabilityResponse.from_entity(capability)


@router.post("/capabilities", response_model=CapabilityResponse, status_code=status.HTTP_201_CREATED)
async def create_capability(
    request: Request,
    payload: CapabilityCreateRequest,
) -> CapabilityResponse:
    service = _service(request)
    if payload.kind == "model":
        draft = ModelCapabilityDraft(
            capability_type=payload.capability_type,
            algorithm=payload.algorithm,
            model_name=payload.model_name,
            model_version=payload.model_version,
            confidence_threshold=payload.confidence_threshold,
            user_params=payload.user_params,
            internal_config=payload.internal_config,
        )
    else:
        draft = ClassicAlgorithmCapabilityDraft(
            capability_type=payload.capability_type,
            algorithm=payload.algorithm,
            user_params=payload.user_params,
            internal_config=payload.internal_config,
        )
    capability = await service.create_capability(draft)
    return CapabilityResponse.from_entity(capability)


@router.patch("/capabilities/{capability_id}", response_model=CapabilityResponse)
async def update_capability(
    request: Request,
    capability_id: UUID,
    payload: CapabilityUpdateRequest,
) -> CapabilityResponse:
    service = _service(request)
    capability = await service.update_capability(
        capability_id,
        payload.confidence_threshold,
        payload.user_params,
    )
    return CapabilityResponse.from_entity(capability)


@router.get("/capabilities/{capability_id}/schema", response_model=CapabilitySchemaResponse)
async def get_capability_schema(
    request: Request,
    capability_id: UUID,
) -> CapabilitySchemaResponse:
    service = _service(request)
    schema = await service.get_capability_schema(capability_id)
    return CapabilitySchemaResponse(capability_id=capability_id, json_schema=schema)


@router.get(
    "/capabilities/{capability_id}/internal-config",
    response_model=CapabilityInternalConfigResponse,
)
async def get_capability_internal_config(
    request: Request,
    capability_id: UUID,
) -> CapabilityInternalConfigResponse:
    service = _service(request)
    capability = await service.get_capability(capability_id)
    return CapabilityInternalConfigResponse(
        capability_id=capability_id,
        internal_config=capability.internal_config,
    )


@router.get("/solutions", response_model=list[SolutionResponse])
async def list_solutions(
    request: Request,
    name: str | None = None,
) -> list[SolutionResponse]:
    service = _service(request)
    solutions = await service.list_solutions(name)
    response: list[SolutionResponse] = []
    for solution in solutions:
        _, steps, capabilities = await service.get_solution(solution.id)
        response.append(SolutionResponse.from_entities(solution, steps, capabilities))
    return response


@router.get("/solutions/{solution_id}", response_model=SolutionResponse)
async def get_solution(request: Request, solution_id: UUID) -> SolutionResponse:
    service = _service(request)
    solution, steps, capabilities = await service.get_solution(solution_id)
    return SolutionResponse.from_entities(solution, steps, capabilities)


@router.post("/solutions", response_model=SolutionResponse, status_code=status.HTTP_201_CREATED)
async def create_solution(
    request: Request,
    payload: SolutionCreateRequest,
) -> SolutionResponse:
    service = _service(request)
    solution = await service.create_solution(
        SolutionDraft(
            name=payload.name,
            description=payload.description,
            user_params=payload.user_params,
        ),
        _solution_step_drafts(payload.steps),
    )
    solution, steps, capabilities = await service.get_solution(solution.id)
    return SolutionResponse.from_entities(solution, steps, capabilities)


@router.patch("/solutions/{solution_id}", response_model=SolutionResponse)
async def update_solution(
    request: Request,
    solution_id: UUID,
    payload: SolutionUpdateRequest,
) -> SolutionResponse:
    service = _service(request)
    updated = await service.update_solution(
        solution_id,
        description=payload.description,
        user_params=payload.user_params,
        steps=None if payload.steps is None else _solution_step_drafts(payload.steps),
    )
    solution, steps, capabilities = await service.get_solution(updated.id)
    return SolutionResponse.from_entities(solution, steps, capabilities)


@router.delete("/solutions/{solution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_solution(request: Request, solution_id: UUID) -> Response:
    service = _service(request)
    await service.delete_solution(solution_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/solutions/{solution_id}/config")
async def get_solution_config(request: Request, solution_id: UUID) -> dict:
    service = _service(request)
    return await service.get_solution_config(solution_id)


@router.get("/internal/solutions/by-name/{name}")
async def get_solution_by_name(request: Request, name: str) -> dict:
    service = _service(request)
    solution, _, _ = await service.get_solution_by_name_or_alias(name)
    return {
        "id": str(solution.id),
        "name": solution.name,
        "sha": solution.sha,
        "version": solution.version,
        "capability": solution.internal_config.get("pipeline_capability", ""),
        "legacy_aliases": solution.internal_config.get("legacy_aliases", []),
    }


@router.get("/internal/solutions/by-name/{name}/config")
async def get_solution_config_by_name(request: Request, name: str) -> dict:
    service = _service(request)
    return await service.get_solution_config_by_name_or_alias(name)


@router.get(
    "/sensors/{sensor_id}/solutions",
    response_model=list[SensorAssignmentResponse],
)
async def list_sensor_assignments(
    request: Request,
    sensor_id: str,
) -> list[SensorAssignmentResponse]:
    service = _service(request)
    assignments = await service.list_sensor_assignments(sensor_id)
    return [
        SensorAssignmentResponse.from_entities(
            item["assignment"],
            item["solution"],
            drifted=item["drifted"],
        )
        for item in assignments
    ]


@router.post(
    "/sensors/{sensor_id}/solutions",
    response_model=SensorAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_sensor_assignment(
    request: Request,
    sensor_id: str,
    payload: SensorAssignmentCreateRequest,
) -> SensorAssignmentResponse:
    service = _service(request)
    assignment = await service.create_sensor_assignment(
        sensor_id,
        payload.solution_id,
        payload.config_overrides,
        is_active=payload.is_active,
    )
    solution, _, _ = await service.get_solution(assignment.solution_id)
    return SensorAssignmentResponse.from_entities(assignment, solution, drifted=False)


@router.patch(
    "/sensors/{sensor_id}/solutions/{assignment_id}",
    response_model=SensorAssignmentResponse,
)
async def update_sensor_assignment(
    request: Request,
    sensor_id: str,
    assignment_id: UUID,
    payload: SensorAssignmentUpdateRequest,
) -> SensorAssignmentResponse:
    service = _service(request)
    assignment = await service.update_sensor_assignment(
        sensor_id,
        assignment_id,
        is_active=payload.is_active,
        config_overrides=payload.config_overrides,
    )
    solution, _, _ = await service.get_solution(assignment.solution_id)
    return SensorAssignmentResponse.from_entities(
        assignment,
        solution,
        drifted=assignment.solution_sha != solution.sha,
    )


@router.delete(
    "/sensors/{sensor_id}/solutions/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sensor_assignment(
    request: Request,
    sensor_id: str,
    assignment_id: UUID,
) -> Response:
    service = _service(request)
    await service.delete_sensor_assignment(sensor_id, assignment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sensors/{sensor_id}/solutions/{assignment_id}/config")
async def get_sensor_assignment_config(
    request: Request,
    sensor_id: str,
    assignment_id: UUID,
) -> dict:
    service = _service(request)
    return await service.get_sensor_assignment_config(sensor_id, assignment_id)
