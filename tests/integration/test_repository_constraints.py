from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg import errors as pg_errors

from capabilities_solutions_api.adapters.repositories.postgres import PostgresCatalogRepository
from capabilities_solutions_api.domain.models import (
    SensorAssignmentDraft,
    CapabilityDraft,
    SolutionDraft,
    SolutionStepDraft,
)


@pytest.mark.asyncio
async def test_repository_create_solution_rolls_back_on_missing_capability_fk(
    repository: PostgresCatalogRepository,
) -> None:
    with pytest.raises(pg_errors.ForeignKeyViolation) as exc_info:
        await repository.create_solution(
            SolutionDraft(
                name="missing-capability-solution",
                description="Should fail on step FK",
                user_params={},
                internal_config={},
                sha="solution-sha",
            ),
            [
                SolutionStepDraft(
                    step_id="detect_video",
                    step_type="async_inference",
                    capability_id=uuid4(),
                    position=0,
                    depends_on=[],
                    user_params={},
                    internal_config={},
                )
            ],
        )

    assert exc_info.value.diag.constraint_name == "solution_steps_capability_id_fkey"
    assert await repository.list_solutions() == []


@pytest.mark.asyncio
async def test_repository_create_solution_raises_check_violation_for_inference_step_without_capability_id(
    repository: PostgresCatalogRepository,
) -> None:
    with pytest.raises(pg_errors.CheckViolation):
        await repository.create_solution(
            SolutionDraft(
                name="invalid-inference-step",
                description="Should fail on step contract check",
                user_params={},
                internal_config={},
                sha="solution-sha",
            ),
            [
                SolutionStepDraft(
                    step_id="detect_video",
                    step_type="async_inference",
                    capability_id=None,
                    position=0,
                    depends_on=[],
                    user_params={},
                    internal_config={},
                )
            ],
        )

    assert await repository.list_solutions() == []


@pytest.mark.asyncio
async def test_repository_create_solution_raises_check_violation_for_postprocess_step_with_capability_id(
    repository: PostgresCatalogRepository,
) -> None:
    capability = await repository.create_capability(
        CapabilityDraft(
            capability_type="object_detection",
            algorithm="rf-detr",
            model_name="od-rf-detr-plate-counting",
            model_version="0.1.0",
            step_type="async_inference",
            confidence_threshold=0.35,
            user_params={},
            internal_config={},
            sha="capability-sha",
        )
    )

    with pytest.raises(pg_errors.CheckViolation):
        await repository.create_solution(
            SolutionDraft(
                name="invalid-postprocess-step",
                description="Should fail on step contract check",
                user_params={},
                internal_config={},
                sha="solution-sha",
            ),
            [
                SolutionStepDraft(
                    step_id="stitch_tracks",
                    step_type="postprocess",
                    capability_id=capability.id,
                    position=0,
                    depends_on=[],
                    user_params={"operations": [{"op": "stitch_tracks"}]},
                    internal_config={},
                )
            ],
        )

    assert await repository.list_solutions() == []


@pytest.mark.asyncio
async def test_repository_create_sensor_assignment_raises_foreign_key_violation_for_missing_solution(
    repository: PostgresCatalogRepository,
) -> None:
    with pytest.raises(pg_errors.ForeignKeyViolation) as exc_info:
        await repository.create_sensor_assignment(
            SensorAssignmentDraft(
                sensor_id="checkout-dvf0002",
                solution_id=uuid4(),
                is_active=True,
                config_overrides={},
                solution_sha="solution-sha",
            )
        )

    assert exc_info.value.diag.constraint_name == "sensor_assignments_solution_id_fkey"
    assert await repository.list_sensor_assignments("checkout-dvf0002") == []


@pytest.mark.asyncio
async def test_repository_create_capability_raises_not_null_violation_for_missing_model_name(
    repository: PostgresCatalogRepository,
) -> None:
    with pytest.raises(pg_errors.NotNullViolation) as exc_info:
        await repository.create_capability(
            CapabilityDraft(
                capability_type="object_detection",
                algorithm="rf-detr",
                model_name=None,  # type: ignore[arg-type]
                model_version="0.1.0",
                step_type="async_inference",
                confidence_threshold=0.35,
                user_params={},
                internal_config={},
                sha="capability-sha",
            )
        )

    assert exc_info.value.diag.column_name == "model_name"
    assert await repository.list_capabilities() == []
