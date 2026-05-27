from __future__ import annotations

import hashlib
import json
from datetime import datetime
from uuid import UUID

from capabilities_solutions_api.domain.models import ToolActionDraft


def _json_default(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Unsupported type for canonical JSON: {type(value)!r}")


def compute_sha(data: dict) -> str:
    canonical = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def compute_tool_action_sha(draft: ToolActionDraft) -> str:
    payload: dict = {
        "name": draft.name,
        "sensor_type": draft.sensor_type,
        "supported_modes": sorted(draft.supported_modes),
        "setup": draft.setup,
        "output_schema_ref": draft.output_schema_ref,
        "slas": {
            s.delivery_mode: s.sla_seconds
            for s in sorted(draft.slas, key=lambda s: s.delivery_mode)
        },
        "steps": [
            {
                "step_id": s.step_id,
                "step_type": s.step_type,
                "capability_sha": s.capability_sha,
                "depends_on": sorted(s.depends_on),
                "user_params": s.user_params,
            }
            for s in sorted(draft.steps, key=lambda s: s.position)
        ],
    }
    return compute_sha(payload)
