from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

JSONDict = dict[str, Any]


@dataclass(slots=True)
class InferenceCost:
    hardware: str = ""
    rate_per_hour_usd: float = 0.0
    inference_time_ms_per_frame: float = 0.0
    cost_per_frame_usd: float = 0.0
    cost_per_camera_day_usd_at_15fps: float = 0.0


@dataclass(slots=True)
class ToolActionSLA:
    delivery_mode: str
    sla_seconds: int
    notes: str = ""


@dataclass(slots=True)
class ActionStepDraft:
    step_id: str
    step_type: str  # model | classic_algorithm | service
    capability_id: UUID | None = None
    capability_sha: str = ""
    position: int = 0
    depends_on: list[str] = field(default_factory=list)
    user_params: JSONDict = field(default_factory=dict)
    internal_config: JSONDict = field(default_factory=dict)


@dataclass(slots=True)
class ActionStep:
    id: UUID
    tool_action_id: UUID
    step_id: str
    step_type: str
    capability_id: UUID | None
    capability_sha: str
    position: int
    depends_on: list[str]
    user_params: JSONDict
    internal_config: JSONDict
    created_at: datetime


@dataclass(slots=True)
class ToolActionDraft:
    name: str
    category: str = ""
    display_name: str = ""
    status: str = "draft"
    sensor_type: str = "camera"
    supported_modes: list[str] = field(default_factory=list)
    setup: JSONDict = field(default_factory=dict)
    output_schema_ref: str = ""
    use_cases: str = ""
    technical_overview: str = ""
    limitations: str = ""
    user_params: JSONDict = field(default_factory=dict)
    internal_config: JSONDict = field(default_factory=dict)
    sha: str = ""
    slas: list[ToolActionSLA] = field(default_factory=list)
    steps: list[ActionStepDraft] = field(default_factory=list)


@dataclass(slots=True)
class ToolAction:
    id: UUID
    name: str
    display_name: str
    category: str
    status: str
    sensor_type: str
    supported_modes: list[str]
    setup: JSONDict
    output_schema_ref: str
    use_cases: str
    technical_overview: str
    limitations: str
    version: int
    sha: str
    user_params: JSONDict
    internal_config: JSONDict
    created_at: datetime
    updated_at: datetime
    slas: list[ToolActionSLA] = field(default_factory=list)
    steps: list[ActionStep] = field(default_factory=list)


@dataclass(slots=True)
class ToolActionPricing:
    tool_action_id: UUID
    totals: InferenceCost


@dataclass(slots=True)
class SensorAssignmentDraft:
    sensor_id: str
    tool_action_id: UUID
    is_active: bool = True
    config_overrides: JSONDict = field(default_factory=dict)


@dataclass(slots=True)
class SensorAssignment:
    id: UUID
    sensor_id: str
    tool_action_id: UUID
    is_active: bool
    config_overrides: JSONDict
    tool_action_sha: str
    created_at: datetime
    updated_at: datetime
