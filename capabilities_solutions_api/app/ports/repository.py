from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from capabilities_solutions_api.domain.models import (
    AnyCapabilityDraft,
    Capability,
    SensorAssignment,
    SensorAssignmentDraft,
    Solution,
    SolutionDraft,
    SolutionStep,
    SolutionStepDraft,
)


class CatalogRepository(ABC):
    @abstractmethod
    async def list_capabilities(
        self,
        capability_type: str | None = None,
        algorithm: str | None = None,
    ) -> list[Capability]:
        raise NotImplementedError

    @abstractmethod
    async def get_capability(self, capability_id: UUID) -> Capability | None:
        raise NotImplementedError

    @abstractmethod
    async def get_capability_by_sha(self, sha: str) -> Capability | None:
        raise NotImplementedError

    @abstractmethod
    async def create_capability(self, draft: AnyCapabilityDraft) -> Capability:
        raise NotImplementedError

    @abstractmethod
    async def update_capability(
        self,
        capability_id: UUID,
        draft: AnyCapabilityDraft,
    ) -> Capability:
        raise NotImplementedError

    @abstractmethod
    async def get_capabilities(self, capability_ids: list[UUID]) -> dict[UUID, Capability]:
        raise NotImplementedError

    @abstractmethod
    async def list_solution_ids_for_capability(self, capability_id: UUID) -> list[UUID]:
        raise NotImplementedError

    @abstractmethod
    async def list_solutions(self, name: str | None = None) -> list[Solution]:
        raise NotImplementedError

    @abstractmethod
    async def get_solution(self, solution_id: UUID) -> Solution | None:
        raise NotImplementedError

    @abstractmethod
    async def get_solution_by_name_or_alias(self, name: str) -> Solution | None:
        raise NotImplementedError

    @abstractmethod
    async def create_solution(
        self,
        draft: SolutionDraft,
        steps: list[SolutionStepDraft],
    ) -> Solution:
        raise NotImplementedError

    @abstractmethod
    async def update_solution(
        self,
        solution_id: UUID,
        draft: SolutionDraft,
        steps: list[SolutionStepDraft],
    ) -> Solution:
        raise NotImplementedError

    @abstractmethod
    async def update_solution_sha(self, solution_id: UUID, sha: str) -> Solution:
        raise NotImplementedError

    @abstractmethod
    async def delete_solution(self, solution_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_solution_steps(self, solution_id: UUID) -> list[SolutionStep]:
        raise NotImplementedError

    @abstractmethod
    async def has_active_assignments(self, solution_id: UUID) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def list_sensor_assignments(self, sensor_id: str) -> list[SensorAssignment]:
        raise NotImplementedError

    @abstractmethod
    async def get_sensor_assignment(
        self,
        sensor_id: str,
        assignment_id: UUID,
    ) -> SensorAssignment | None:
        raise NotImplementedError

    @abstractmethod
    async def create_sensor_assignment(
        self,
        draft: SensorAssignmentDraft,
    ) -> SensorAssignment:
        raise NotImplementedError

    @abstractmethod
    async def update_sensor_assignment(
        self,
        sensor_id: str,
        assignment_id: UUID,
        draft: SensorAssignmentDraft,
    ) -> SensorAssignment:
        raise NotImplementedError

    @abstractmethod
    async def delete_sensor_assignment(self, sensor_id: str, assignment_id: UUID) -> None:
        raise NotImplementedError
