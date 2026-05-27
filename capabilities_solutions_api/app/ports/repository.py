from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from capabilities_solutions_api.domain.models import (
    ActionStep,
    ActionStepDraft,
    SensorAssignment,
    SensorAssignmentDraft,
    ToolAction,
    ToolActionDraft,
    ToolActionSLA,
)


class ToolActionRepository(ABC):
    @abstractmethod
    async def list_tool_actions(
        self,
        status: str | None = None,
        sensor_type: str | None = None,
        category: str | None = None,
    ) -> list[ToolAction]:
        raise NotImplementedError

    @abstractmethod
    async def get_tool_action(self, tool_action_id: UUID) -> ToolAction | None:
        raise NotImplementedError

    @abstractmethod
    async def get_tool_action_by_name(self, name: str) -> ToolAction | None:
        raise NotImplementedError

    @abstractmethod
    async def get_tool_action_by_sha(self, sha: str) -> ToolAction | None:
        raise NotImplementedError

    @abstractmethod
    async def create_tool_action(self, draft: ToolActionDraft) -> ToolAction:
        raise NotImplementedError

    @abstractmethod
    async def update_tool_action(
        self,
        tool_action_id: UUID,
        draft: ToolActionDraft,
    ) -> ToolAction:
        raise NotImplementedError

    @abstractmethod
    async def delete_tool_action(self, tool_action_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_steps(self, tool_action_id: UUID) -> list[ActionStep]:
        raise NotImplementedError

    @abstractmethod
    async def list_sensor_assignments(self, sensor_id: str) -> list[SensorAssignment]:
        raise NotImplementedError

    @abstractmethod
    async def get_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
    ) -> SensorAssignment | None:
        raise NotImplementedError

    @abstractmethod
    async def create_sensor_assignment(
        self,
        draft: SensorAssignmentDraft,
        tool_action_sha: str,
    ) -> SensorAssignment:
        raise NotImplementedError

    @abstractmethod
    async def update_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
        is_active: bool,
        config_overrides: dict,
    ) -> SensorAssignment:
        raise NotImplementedError

    @abstractmethod
    async def delete_sensor_assignment(
        self,
        sensor_id: str,
        tool_action_id: UUID,
    ) -> None:
        raise NotImplementedError
