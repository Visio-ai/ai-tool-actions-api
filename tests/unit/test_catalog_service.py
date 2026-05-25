from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from capabilities_solutions_api.app.ports.repository import CatalogRepository
from capabilities_solutions_api.app.use_cases.catalog_service import CatalogService
from capabilities_solutions_api.domain.errors import ValidationError
from capabilities_solutions_api.domain.models import (
    AnyCapabilityDraft,
    Capability,
    ClassicAlgorithmCapability,
    ModelCapability,
    ModelCapabilityDraft,
    SensorAssignment,
    SensorAssignmentDraft,
    Solution,
    SolutionDraft,
    SolutionStep,
    SolutionStepDraft,
)

from datetime import datetime, timezone

_NOW = datetime.now(tz=timezone.utc)


def _model_capability(capability_id: UUID | None = None) -> ModelCapability:
    return ModelCapability(
        id=capability_id or uuid4(),
        capability_type="object_detection",
        algorithm="rfdetr",
        kind="model",
        user_params={},
        internal_config={},
        sha="abc",
        created_at=_NOW,
        updated_at=_NOW,
        model_name="od-rf-detr",
        model_version="1.0.0",
        confidence_threshold=0.5,
    )


def _classic_capability(capability_id: UUID | None = None) -> ClassicAlgorithmCapability:
    return ClassicAlgorithmCapability(
        id=capability_id or uuid4(),
        capability_type="zone_analytics",
        algorithm="zone_eval",
        kind="classic_algorithm",
        user_params={},
        internal_config={},
        sha="def",
        created_at=_NOW,
        updated_at=_NOW,
    )


class InMemoryCatalogRepository(CatalogRepository):
    def __init__(self, capabilities: dict[UUID, Capability] | None = None) -> None:
        self._capabilities: dict[UUID, Capability] = capabilities or {}

    async def list_capabilities(
        self,
        capability_type: str | None = None,
        algorithm: str | None = None,
    ) -> list[Capability]:
        return list(self._capabilities.values())

    async def get_capability(self, capability_id: UUID) -> Capability | None:
        return self._capabilities.get(capability_id)

    async def get_capability_by_sha(self, sha: str) -> Capability | None:
        return next((c for c in self._capabilities.values() if c.sha == sha), None)

    async def create_capability(self, draft: AnyCapabilityDraft) -> Capability:
        raise NotImplementedError

    async def update_capability(self, capability_id: UUID, draft: AnyCapabilityDraft) -> Capability:
        raise NotImplementedError

    async def get_capabilities(self, capability_ids: list[UUID]) -> dict[UUID, Capability]:
        return {cid: self._capabilities[cid] for cid in capability_ids if cid in self._capabilities}

    async def list_solution_ids_for_capability(self, capability_id: UUID) -> list[UUID]:
        return []

    async def list_solutions(self, name: str | None = None) -> list[Solution]:
        return []

    async def get_solution(self, solution_id: UUID) -> Solution | None:
        return None

    async def get_solution_by_name_or_alias(self, name: str) -> Solution | None:
        return None

    async def create_solution(self, draft: SolutionDraft, steps: list[SolutionStepDraft]) -> Solution:
        raise NotImplementedError

    async def update_solution(self, solution_id: UUID, draft: SolutionDraft, steps: list[SolutionStepDraft]) -> Solution:
        raise NotImplementedError

    async def update_solution_sha(self, solution_id: UUID, sha: str) -> Solution:
        raise NotImplementedError

    async def delete_solution(self, solution_id: UUID) -> None:
        raise NotImplementedError

    async def get_solution_steps(self, solution_id: UUID) -> list[SolutionStep]:
        return []

    async def has_active_assignments(self, solution_id: UUID) -> bool:
        return False

    async def list_sensor_assignments(self, sensor_id: str) -> list[SensorAssignment]:
        return []

    async def get_sensor_assignment(self, sensor_id: str, assignment_id: UUID) -> SensorAssignment | None:
        return None

    async def create_sensor_assignment(self, draft: SensorAssignmentDraft) -> SensorAssignment:
        raise NotImplementedError

    async def update_sensor_assignment(self, sensor_id: str, assignment_id: UUID, draft: SensorAssignmentDraft) -> SensorAssignment:
        raise NotImplementedError

    async def delete_sensor_assignment(self, sensor_id: str, assignment_id: UUID) -> None:
        raise NotImplementedError


# ─── Validation: inference steps ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inference_step_without_capability_id_rejected() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    with pytest.raises(ValidationError, match="requires a capability_id"):
        await service.create_solution(
            SolutionDraft(name="s"),
            [SolutionStepDraft(step_id="run", step_type="async_inference", capability_id=None, position=0)],
        )


@pytest.mark.asyncio
async def test_inference_step_with_classic_algorithm_capability_rejected() -> None:
    cap = _classic_capability()
    service = CatalogService(InMemoryCatalogRepository({cap.id: cap}))
    with pytest.raises(ValidationError, match="requires a 'model' capability"):
        await service.create_solution(
            SolutionDraft(name="s"),
            [SolutionStepDraft(step_id="run", step_type="inference", capability_id=cap.id, position=0)],
        )


@pytest.mark.asyncio
async def test_inference_step_with_model_capability_accepted() -> None:
    cap = _model_capability()
    repo = InMemoryCatalogRepository({cap.id: cap})

    created: list[Solution] = []

    async def create_solution(draft, steps):
        sol = Solution(
            id=uuid4(), name=draft.name, description="", user_params={},
            internal_config={}, version=1, sha="x", created_at=_NOW, updated_at=_NOW,
        )
        created.append(sol)
        return sol

    repo.create_solution = create_solution
    service = CatalogService(repo)
    await service.create_solution(
        SolutionDraft(name="s"),
        [SolutionStepDraft(step_id="run", step_type="inference", capability_id=cap.id, position=0)],
    )
    assert len(created) == 1


# ─── Validation: postprocess / local_capability steps ─────────────────────────

@pytest.mark.asyncio
async def test_postprocess_step_without_capability_accepted() -> None:
    repo = InMemoryCatalogRepository()
    created: list[Solution] = []

    async def create_solution(draft, steps):
        sol = Solution(
            id=uuid4(), name=draft.name, description="", user_params={},
            internal_config={}, version=1, sha="x", created_at=_NOW, updated_at=_NOW,
        )
        created.append(sol)
        return sol

    repo.create_solution = create_solution
    service = CatalogService(repo)
    await service.create_solution(
        SolutionDraft(name="s"),
        [SolutionStepDraft(step_id="pp", step_type="postprocess", capability_id=None, position=0)],
    )
    assert len(created) == 1


@pytest.mark.asyncio
async def test_local_capability_step_with_classic_algorithm_capability_accepted() -> None:
    cap = _classic_capability()
    repo = InMemoryCatalogRepository({cap.id: cap})
    created: list[Solution] = []

    async def create_solution(draft, steps):
        sol = Solution(
            id=uuid4(), name=draft.name, description="", user_params={},
            internal_config={}, version=1, sha="x", created_at=_NOW, updated_at=_NOW,
        )
        created.append(sol)
        return sol

    repo.create_solution = create_solution
    service = CatalogService(repo)
    await service.create_solution(
        SolutionDraft(name="s"),
        [SolutionStepDraft(step_id="zone", step_type="local_capability", capability_id=cap.id, position=0)],
    )
    assert len(created) == 1


@pytest.mark.asyncio
async def test_local_capability_step_with_model_capability_rejected() -> None:
    cap = _model_capability()
    service = CatalogService(InMemoryCatalogRepository({cap.id: cap}))
    with pytest.raises(ValidationError, match="must reference a 'classic_algorithm' capability"):
        await service.create_solution(
            SolutionDraft(name="s"),
            [SolutionStepDraft(step_id="zone", step_type="local_capability", capability_id=cap.id, position=0)],
        )


# ─── Validation: misc ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unsupported_step_type_rejected() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    with pytest.raises(ValidationError, match="unsupported step_type"):
        await service.create_solution(
            SolutionDraft(name="s"),
            [SolutionStepDraft(step_id="x", step_type="unsupported", capability_id=uuid4(), position=0)],
        )


# ─── SHA: model vs classic_algorithm are distinct ─────────────────────────────

def test_model_and_classic_sha_differ() -> None:
    service = CatalogService(InMemoryCatalogRepository())
    model_sha = service._compute_capability_sha(
        ModelCapabilityDraft(
            capability_type="object_detection",
            algorithm="rfdetr",
            model_name="od-rf-detr",
            model_version="1.0.0",
        )
    )
    from capabilities_solutions_api.domain.models import ClassicAlgorithmCapabilityDraft
    classic_sha = service._compute_capability_sha(
        ClassicAlgorithmCapabilityDraft(
            capability_type="object_detection",
            algorithm="rfdetr",
        )
    )
    assert model_sha != classic_sha
