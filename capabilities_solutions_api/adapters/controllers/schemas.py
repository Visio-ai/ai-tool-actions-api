from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from capabilities_solutions_api.domain.models import (
    ActionStep,
    ActionStepDraft,
    SensorAssignment,
    SensorAssignmentDraft,
    ToolAction,
    ToolActionDraft,
    ToolActionSLA,
)


# ─── SLA ──────────────────────────────────────────────────────────────────────

class ToolActionSLASchema(BaseModel):
    delivery_mode: str
    sla_seconds: int
    notes: str = ""

    def to_domain(self) -> ToolActionSLA:
        return ToolActionSLA(
            delivery_mode=self.delivery_mode,
            sla_seconds=self.sla_seconds,
            notes=self.notes,
        )

    @classmethod
    def from_domain(cls, sla: ToolActionSLA) -> "ToolActionSLASchema":
        return cls(
            delivery_mode=sla.delivery_mode,
            sla_seconds=sla.sla_seconds,
            notes=sla.notes,
        )


# ─── Step ─────────────────────────────────────────────────────────────────────

class ActionStepCreateSchema(BaseModel):
    step_id: str
    step_type: str
    capability_id: UUID | None = None
    capability_sha: str = ""
    position: int = 0
    depends_on: list[str] = Field(default_factory=list)
    user_params: dict[str, Any] = Field(default_factory=dict)
    internal_config: dict[str, Any] = Field(default_factory=dict)

    def to_draft(self) -> ActionStepDraft:
        return ActionStepDraft(
            step_id=self.step_id,
            step_type=self.step_type,
            capability_id=self.capability_id,
            capability_sha=self.capability_sha,
            position=self.position,
            depends_on=list(self.depends_on),
            user_params=dict(self.user_params),
            internal_config=dict(self.internal_config),
        )


class ActionStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tool_action_id: UUID
    step_id: str
    step_type: str
    capability_id: UUID | None
    capability_sha: str
    position: int
    depends_on: list[str]
    user_params: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_domain(cls, step: ActionStep) -> "ActionStepResponse":
        return cls(
            id=step.id,
            tool_action_id=step.tool_action_id,
            step_id=step.step_id,
            step_type=step.step_type,
            capability_id=step.capability_id,
            capability_sha=step.capability_sha,
            position=step.position,
            depends_on=list(step.depends_on),
            user_params=dict(step.user_params),
            created_at=step.created_at,
        )


# ─── ToolAction create / update ───────────────────────────────────────────────

class ToolActionCreateRequest(BaseModel):
    name: str
    display_name: str = ""
    category: str = ""
    status: str = "draft"
    sensor_type: str = "camera"
    supported_modes: list[str] = Field(default_factory=list)
    setup: dict[str, Any] = Field(default_factory=dict)
    output_schema_ref: str = ""
    use_cases: str = ""
    technical_overview: str = ""
    limitations: str = ""
    user_params: dict[str, Any] = Field(default_factory=dict)
    internal_config: dict[str, Any] = Field(default_factory=dict)
    slas: list[ToolActionSLASchema] = Field(default_factory=list)
    steps: list[ActionStepCreateSchema] = Field(default_factory=list)

    def to_draft(self) -> ToolActionDraft:
        return ToolActionDraft(
            name=self.name,
            display_name=self.display_name,
            category=self.category,
            status=self.status,
            sensor_type=self.sensor_type,
            supported_modes=list(self.supported_modes),
            setup=dict(self.setup),
            output_schema_ref=self.output_schema_ref,
            use_cases=self.use_cases,
            technical_overview=self.technical_overview,
            limitations=self.limitations,
            user_params=dict(self.user_params),
            internal_config=dict(self.internal_config),
            slas=[s.to_domain() for s in self.slas],
            steps=[s.to_draft() for s in self.steps],
        )


class ToolActionUpdateRequest(BaseModel):
    display_name: str | None = None
    category: str | None = None
    status: str | None = None
    sensor_type: str | None = None
    supported_modes: list[str] | None = None
    setup: dict[str, Any] | None = None
    output_schema_ref: str | None = None
    use_cases: str | None = None
    technical_overview: str | None = None
    limitations: str | None = None
    user_params: dict[str, Any] | None = None
    internal_config: dict[str, Any] | None = None
    slas: list[ToolActionSLASchema] | None = None
    steps: list[ActionStepCreateSchema] | None = None


# ─── ToolAction response ──────────────────────────────────────────────────────

class ToolActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    category: str
    status: str
    sensor_type: str
    supported_modes: list[str]
    setup: dict[str, Any]
    output_schema_ref: str
    use_cases: str
    technical_overview: str
    limitations: str
    version: int
    sha: str
    user_params: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    slas: list[ToolActionSLASchema]
    steps: list[ActionStepResponse]

    @classmethod
    def from_entity(cls, ta: ToolAction) -> "ToolActionResponse":
        return cls(
            id=ta.id,
            name=ta.name,
            display_name=ta.display_name,
            category=ta.category,
            status=ta.status,
            sensor_type=ta.sensor_type,
            supported_modes=list(ta.supported_modes),
            setup=dict(ta.setup),
            output_schema_ref=ta.output_schema_ref,
            use_cases=ta.use_cases,
            technical_overview=ta.technical_overview,
            limitations=ta.limitations,
            version=ta.version,
            sha=ta.sha,
            user_params=dict(ta.user_params),
            created_at=ta.created_at,
            updated_at=ta.updated_at,
            slas=[ToolActionSLASchema.from_domain(s) for s in ta.slas],
            steps=[ActionStepResponse.from_domain(s) for s in ta.steps],
        )


# ─── SensorAssignment ─────────────────────────────────────────────────────────

class SensorAssignmentCreateRequest(BaseModel):
    tool_action_id: UUID
    is_active: bool = True
    config_overrides: dict[str, Any] = Field(default_factory=dict)

    def to_draft(self, sensor_id: str) -> SensorAssignmentDraft:
        return SensorAssignmentDraft(
            sensor_id=sensor_id,
            tool_action_id=self.tool_action_id,
            is_active=self.is_active,
            config_overrides=dict(self.config_overrides),
        )


class SensorAssignmentUpdateRequest(BaseModel):
    is_active: bool | None = None
    config_overrides: dict[str, Any] | None = None


class SensorAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sensor_id: str
    tool_action_id: UUID
    is_active: bool
    config_overrides: dict[str, Any]
    tool_action_sha: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, sa: SensorAssignment) -> "SensorAssignmentResponse":
        return cls(
            id=sa.id,
            sensor_id=sa.sensor_id,
            tool_action_id=sa.tool_action_id,
            is_active=sa.is_active,
            config_overrides=dict(sa.config_overrides),
            tool_action_sha=sa.tool_action_sha,
            created_at=sa.created_at,
            updated_at=sa.updated_at,
        )


# ─── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
