from datetime import datetime, timezone
from uuid import uuid4

from capabilities_solutions_api.domain.models import (
    ModelCapability,
    SensorAssignment,
    Solution,
    SolutionStep,
)
from capabilities_solutions_api.domain.resolver import resolve_solution_config


def _now():
    return datetime.now(timezone.utc)


def test_resolve_solution_config_merges_capability_step_and_assignment() -> None:
    capability_id = uuid4()
    solution_id = uuid4()
    capability = ModelCapability(
        id=capability_id,
        capability_type="object_detection",
        algorithm="rf-detr",
        kind="model",
        user_params={"frame_stride": 4},
        internal_config={
            "serve_endpoint": "http://model/process",
            "poll_interval_seconds": 30,
            "poll_timeout_seconds": 3600,
            "io_contract": {"payload_template": {"video_uri": "{request.model_input_meta.video_uri}"}},
        },
        sha="cap-sha",
        created_at=_now(),
        updated_at=_now(),
        model_name="od-rf-detr-plate-counting",
        model_version="0.1.0",
        confidence_threshold=0.3,
    )
    solution = Solution(
        id=solution_id,
        name="plate_counting_divino_fogao_v2",
        description="test",
        user_params={"zones": [{"id": "a"}]},
        internal_config={"pipeline_capability": "pipeline", "subscribers": []},
        version=2,
        sha="sol-sha",
        created_at=_now(),
        updated_at=_now(),
    )
    step = SolutionStep(
        id=uuid4(),
        solution_id=solution_id,
        step_id="detect_video",
        step_type="async_inference",
        capability_id=capability_id,
        position=0,
        depends_on=[],
        user_params={"confidence_threshold": 0.55, "fps": 2.5},
        internal_config={},
        created_at=_now(),
        updated_at=_now(),
    )
    assignment = SensorAssignment(
        id=uuid4(),
        sensor_id="checkout-dvf0002",
        solution_id=solution_id,
        is_active=True,
        config_overrides={"zones": [{"id": "camera-zone"}]},
        solution_sha="sol-sha",
        created_at=_now(),
        updated_at=_now(),
    )

    resolved = resolve_solution_config(
        solution,
        [step],
        {capability_id: capability},
        assignment=assignment,
    )

    assert resolved["solution_id"] == "plate_counting_divino_fogao_v2"
    assert resolved["capability"] == "pipeline"
    assert resolved["user_params"]["zones"] == [{"id": "camera-zone"}]
    assert resolved["steps"][0]["confidence_threshold"] == 0.55
    assert resolved["steps"][0]["params"] == {"frame_stride": 4, "confidence_threshold": 0.55, "fps": 2.5}
    assert resolved["steps"][0]["serve_endpoint"] == "http://model/process"
