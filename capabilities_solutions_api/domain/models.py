from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeAlias
from uuid import UUID

JSONDict = dict[str, Any]


# ─── Capability drafts ─────────────────────────────────────────────────────────

@dataclass(slots=True)
class ModelCapabilityDraft:
    capability_type: str
    algorithm: str
    model_name: str
    model_version: str
    confidence_threshold: float = 0.0
    user_params: JSONDict = field(default_factory=dict)
    internal_config: JSONDict = field(default_factory=dict)
    sha: str = ""


@dataclass(slots=True)
class ClassicAlgorithmCapabilityDraft:
    capability_type: str
    algorithm: str
    user_params: JSONDict = field(default_factory=dict)
    internal_config: JSONDict = field(default_factory=dict)
    sha: str = ""


AnyCapabilityDraft: TypeAlias = ModelCapabilityDraft | ClassicAlgorithmCapabilityDraft


# ─── Capability entities ───────────────────────────────────────────────────────

@dataclass(slots=True)
class Capability:
    id: UUID
    capability_type: str
    algorithm: str
    kind: str
    user_params: JSONDict
    internal_config: JSONDict
    sha: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class ModelCapability(Capability):
    model_name: str = ""
    model_version: str = ""
    confidence_threshold: float = 0.0


@dataclass(slots=True)
class ClassicAlgorithmCapability(Capability):
    pass


# ─── Solution ──────────────────────────────────────────────────────────────────

@dataclass(slots=True)
class SolutionStepDraft:
    step_id: str
    step_type: str
    capability_id: UUID | None
    position: int
    depends_on: list[str] = field(default_factory=list)
    user_params: JSONDict = field(default_factory=dict)
    internal_config: JSONDict = field(default_factory=dict)


@dataclass(slots=True)
class SolutionStep:
    id: UUID
    solution_id: UUID
    step_id: str
    step_type: str
    capability_id: UUID | None
    position: int
    depends_on: list[str]
    user_params: JSONDict
    internal_config: JSONDict
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class SolutionDraft:
    name: str
    description: str = ""
    user_params: JSONDict = field(default_factory=dict)
    internal_config: JSONDict = field(default_factory=dict)
    version: int = 1
    sha: str = ""


@dataclass(slots=True)
class Solution:
    id: UUID
    name: str
    description: str
    user_params: JSONDict
    internal_config: JSONDict
    version: int
    sha: str
    created_at: datetime
    updated_at: datetime


# ─── Sensor assignment ─────────────────────────────────────────────────────────

@dataclass(slots=True)
class SensorAssignmentDraft:
    sensor_id: str
    solution_id: UUID
    is_active: bool = True
    config_overrides: JSONDict = field(default_factory=dict)
    solution_sha: str = ""


@dataclass(slots=True)
class SensorAssignment:
    id: UUID
    sensor_id: str
    solution_id: UUID
    is_active: bool
    config_overrides: JSONDict
    solution_sha: str
    created_at: datetime
    updated_at: datetime
