from __future__ import annotations

from typing import Any
from uuid import UUID

from capabilities_solutions_api.domain.errors import ValidationError
from capabilities_solutions_api.domain.models import (
    Capability,
    ModelCapability,
    SensorAssignment,
    Solution,
    SolutionStep,
)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, override_value in override.items():
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(override_value, dict):
            result[key] = deep_merge(base_value, override_value)
        else:
            result[key] = override_value
    return result


def build_user_schema(capability: Capability) -> dict[str, Any]:
    sample_props: dict[str, Any] = {}
    for key, value in capability.user_params.items():
        if isinstance(value, bool):
            value_type = "boolean"
        elif isinstance(value, int) and not isinstance(value, bool):
            value_type = "integer"
        elif isinstance(value, float):
            value_type = "number"
        elif isinstance(value, list):
            value_type = "array"
        elif isinstance(value, dict):
            value_type = "object"
        else:
            value_type = "string"
        sample_props[key] = {"type": value_type}

    props: dict[str, Any] = {
        "user_params": {
            "type": "object",
            "properties": sample_props,
            "additionalProperties": True,
        },
    }
    if isinstance(capability, ModelCapability):
        props["confidence_threshold"] = {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        }

    return {
        "title": f"{capability.capability_type}:{capability.algorithm}",
        "type": "object",
        "properties": props,
        "additionalProperties": False,
    }


def resolve_solution_config(
    solution: Solution,
    steps: list[SolutionStep],
    capabilities_by_id: dict[UUID, Capability],
    assignment: SensorAssignment | None = None,
) -> dict[str, Any]:
    merged_solution_user_params = dict(solution.user_params)
    if assignment:
        merged_solution_user_params = deep_merge(
            merged_solution_user_params,
            assignment.config_overrides,
        )

    resolved_steps: list[dict[str, Any]] = []
    for step in sorted(steps, key=lambda item: item.position):
        step_config: dict[str, Any] = {
            "step_id": step.step_id,
            "step_type": step.step_type,
            "depends_on": list(step.depends_on),
        }

        if step.capability_id is not None:
            capability = capabilities_by_id.get(step.capability_id)
            if capability is None:
                raise ValidationError(
                    f"Missing capability {step.capability_id} for step {step.step_id}"
                )
            merged_internal = deep_merge(capability.internal_config, step.internal_config)
            merged_params = deep_merge(capability.user_params, step.user_params)
            step_config.update(merged_internal)
            step_config.update({
                "params": merged_params,
                "capability_id": str(capability.id),
                "capability_sha": capability.sha,
                "capability_type": capability.capability_type,
                "algorithm": capability.algorithm,
            })
            if isinstance(capability, ModelCapability):
                confidence_threshold = float(
                    step.user_params.get("confidence_threshold", capability.confidence_threshold)
                )
                step_config.update({
                    "model_name": capability.model_name,
                    "model_version": capability.model_version,
                    "confidence_threshold": confidence_threshold,
                })
        else:
            merged_internal = dict(step.internal_config)
            internal_params = merged_internal.pop("params", {})
            merged_params = deep_merge(internal_params, step.user_params)
            step_config.update(merged_internal)
            step_config.update({"params": merged_params})

        resolved_steps.append(step_config)

    top_level = dict(solution.internal_config)
    top_level.setdefault("subscribers", [])
    top_level["steps"] = resolved_steps
    top_level["solution_id"] = solution.name
    top_level["solution_sha"] = solution.sha
    top_level["solution_version"] = solution.version
    top_level["capability"] = solution.internal_config.get("pipeline_capability", "")
    top_level["user_params"] = merged_solution_user_params
    if assignment:
        top_level["sensor_assignment"] = {
            "assignment_id": str(assignment.id),
            "sensor_id": assignment.sensor_id,
            "solution_sha": assignment.solution_sha,
            "is_active": assignment.is_active,
        }
    return top_level
