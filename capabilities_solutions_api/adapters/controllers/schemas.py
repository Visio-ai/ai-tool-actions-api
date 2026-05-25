from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from capabilities_solutions_api.domain.models import (
    Capability,
    ClassicAlgorithmCapability,
    ModelCapability,
    SensorAssignment,
    Solution,
    SolutionStep,
)


class ModelCapabilityCreateRequest(BaseModel):
    kind: Literal["model"] = "model"
    capability_type: str
    algorithm: str
    model_name: str
    model_version: str
    confidence_threshold: float = 0.0
    user_params: dict[str, Any] = Field(default_factory=dict)
    internal_config: dict[str, Any] = Field(default_factory=dict)


class ClassicAlgorithmCapabilityCreateRequest(BaseModel):
    kind: Literal["classic_algorithm"]
    capability_type: str
    algorithm: str
    user_params: dict[str, Any] = Field(default_factory=dict)
    internal_config: dict[str, Any] = Field(default_factory=dict)


CapabilityCreateRequest = ModelCapabilityCreateRequest | ClassicAlgorithmCapabilityCreateRequest


class CapabilityUpdateRequest(BaseModel):
    confidence_threshold: float | None = None
    user_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_confidence_threshold(self) -> "CapabilityUpdateRequest":
        if self.confidence_threshold is not None and not (0.0 <= self.confidence_threshold <= 1.0):
            raise ValueError("confidence_threshold must be between 0.0 and 1.0")
        return self


class CapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    capability_type: str
    algorithm: str
    user_params: dict[str, Any]
    sha: str
    created_at: datetime
    updated_at: datetime
    model_name: str | None = None
    model_version: str | None = None
    confidence_threshold: float | None = None

    @classmethod
    def from_entity(cls, entity: Capability) -> "CapabilityResponse":
        if isinstance(entity, ModelCapability):
            return cls(
                id=entity.id,
                kind=entity.kind,
                capability_type=entity.capability_type,
                algorithm=entity.algorithm,
                user_params=entity.user_params,
                sha=entity.sha,
                created_at=entity.created_at,
                updated_at=entity.updated_at,
                model_name=entity.model_name,
                model_version=entity.model_version,
                confidence_threshold=entity.confidence_threshold,
            )
        return cls(
            id=entity.id,
            kind=entity.kind,
            capability_type=entity.capability_type,
            algorithm=entity.algorithm,
            user_params=entity.user_params,
            sha=entity.sha,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


class CapabilitySchemaResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    capability_id: UUID
    json_schema: dict[str, Any] = Field(serialization_alias="schema")


class CapabilityInternalConfigResponse(BaseModel):
    capability_id: UUID
    internal_config: dict[str, Any]


class SolutionStepRequest(BaseModel):
    step_id: str
    step_type: str
    capability_id: UUID | None = None
    depends_on: list[str] = Field(default_factory=list)
    user_params: dict[str, Any] = Field(default_factory=dict)


class SolutionCreateRequest(BaseModel):
    name: str
    description: str = ""
    user_params: dict[str, Any] = Field(default_factory=dict)
    steps: list[SolutionStepRequest]


class SolutionUpdateRequest(BaseModel):
    description: str | None = None
    user_params: dict[str, Any] | None = None
    steps: list[SolutionStepRequest] | None = None


class CapabilitySummaryResponse(BaseModel):
    id: UUID
    kind: str
    capability_type: str
    algorithm: str
    sha: str
    model_name: str | None = None
    model_version: str | None = None
    confidence_threshold: float | None = None

    @classmethod
    def from_entity(cls, entity: Capability) -> "CapabilitySummaryResponse":
        if isinstance(entity, ModelCapability):
            return cls(
                id=entity.id,
                kind=entity.kind,
                capability_type=entity.capability_type,
                algorithm=entity.algorithm,
                sha=entity.sha,
                model_name=entity.model_name,
                model_version=entity.model_version,
                confidence_threshold=entity.confidence_threshold,
            )
        return cls(
            id=entity.id,
            kind=entity.kind,
            capability_type=entity.capability_type,
            algorithm=entity.algorithm,
            sha=entity.sha,
        )


class SolutionStepResponse(BaseModel):
    id: UUID
    step_id: str
    step_type: str
    capability_id: UUID | None
    position: int
    depends_on: list[str]
    user_params: dict[str, Any]
    capability: CapabilitySummaryResponse | None = None

    @classmethod
    def from_entity(
        cls,
        entity: SolutionStep,
        capability: Capability | None = None,
    ) -> "SolutionStepResponse":
        return cls(
            id=entity.id,
            step_id=entity.step_id,
            step_type=entity.step_type,
            capability_id=entity.capability_id,
            position=entity.position,
            depends_on=list(entity.depends_on),
            user_params=dict(entity.user_params),
            capability=CapabilitySummaryResponse.from_entity(capability) if capability else None,
        )


class SolutionResponse(BaseModel):
    id: UUID
    name: str
    description: str
    user_params: dict[str, Any]
    version: int
    sha: str
    created_at: datetime
    updated_at: datetime
    steps: list[SolutionStepResponse]

    @classmethod
    def from_entities(
        cls,
        solution: Solution,
        steps: list[SolutionStep],
        capabilities_by_id: dict[UUID, Capability],
    ) -> "SolutionResponse":
        return cls(
            id=solution.id,
            name=solution.name,
            description=solution.description,
            user_params=dict(solution.user_params),
            version=solution.version,
            sha=solution.sha,
            created_at=solution.created_at,
            updated_at=solution.updated_at,
            steps=[
                SolutionStepResponse.from_entity(step, capabilities_by_id.get(step.capability_id))
                for step in sorted(steps, key=lambda item: item.position)
            ],
        )


class SensorAssignmentCreateRequest(BaseModel):
    solution_id: UUID
    is_active: bool = True
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class SensorAssignmentUpdateRequest(BaseModel):
    is_active: bool | None = None
    config_overrides: dict[str, Any] | None = None


class SensorAssignmentResponse(BaseModel):
    id: UUID
    sensor_id: str
    solution_id: UUID
    solution_name: str
    is_active: bool
    config_overrides: dict[str, Any]
    solution_sha: str
    current_solution_sha: str
    drifted: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entities(
        cls,
        assignment: SensorAssignment,
        solution: Solution,
        *,
        drifted: bool,
    ) -> "SensorAssignmentResponse":
        return cls(
            id=assignment.id,
            sensor_id=assignment.sensor_id,
            solution_id=assignment.solution_id,
            solution_name=solution.name,
            is_active=assignment.is_active,
            config_overrides=dict(assignment.config_overrides),
            solution_sha=assignment.solution_sha,
            current_solution_sha=solution.sha,
            drifted=drifted,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
        )


class HealthResponse(BaseModel):
    status: str
