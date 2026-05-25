from __future__ import annotations

from uuid import UUID

from capabilities_solutions_api.app.ports.repository import CatalogRepository
from capabilities_solutions_api.domain.errors import ConflictError, NotFoundError, ValidationError
from capabilities_solutions_api.domain.models import (
    AnyCapabilityDraft,
    Capability,
    ClassicAlgorithmCapabilityDraft,
    ModelCapability,
    ModelCapabilityDraft,
    SensorAssignment,
    SensorAssignmentDraft,
    Solution,
    SolutionDraft,
    SolutionStep,
    SolutionStepDraft,
)
from capabilities_solutions_api.domain.resolver import build_user_schema, resolve_solution_config
from capabilities_solutions_api.domain.sha import compute_sha

VALID_SOLUTION_STEP_TYPES = {"inference", "async_inference", "postprocess", "local_capability"}
_INFERENCE_STEP_TYPES = {"inference", "async_inference"}


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self.repository = repository

    async def list_capabilities(
        self,
        capability_type: str | None = None,
        algorithm: str | None = None,
    ) -> list[Capability]:
        return await self.repository.list_capabilities(capability_type, algorithm)

    async def get_capability(self, capability_id: UUID) -> Capability:
        capability = await self.repository.get_capability(capability_id)
        if capability is None:
            raise NotFoundError(f"Capability {capability_id} not found")
        return capability

    async def ensure_capability(self, draft: AnyCapabilityDraft) -> Capability:
        draft.sha = self._compute_capability_sha(draft)
        existing = await self.repository.get_capability_by_sha(draft.sha)
        if existing is not None:
            return existing
        return await self.repository.create_capability(draft)

    async def create_capability(self, draft: AnyCapabilityDraft) -> Capability:
        draft.sha = self._compute_capability_sha(draft)
        existing = await self.repository.get_capability_by_sha(draft.sha)
        if existing is not None:
            raise ConflictError(f"Capability SHA {draft.sha} already exists")
        return await self.repository.create_capability(draft)

    async def update_capability(
        self,
        capability_id: UUID,
        confidence_threshold: float | None,
        user_params: dict,
    ) -> Capability:
        current = await self.get_capability(capability_id)
        if isinstance(current, ModelCapability):
            new_confidence = confidence_threshold if confidence_threshold is not None else current.confidence_threshold
            draft: AnyCapabilityDraft = ModelCapabilityDraft(
                capability_type=current.capability_type,
                algorithm=current.algorithm,
                model_name=current.model_name,
                model_version=current.model_version,
                confidence_threshold=new_confidence,
                user_params=user_params,
                internal_config=current.internal_config,
            )
        else:
            draft = ClassicAlgorithmCapabilityDraft(
                capability_type=current.capability_type,
                algorithm=current.algorithm,
                user_params=user_params,
                internal_config=current.internal_config,
            )
        draft.sha = self._compute_capability_sha(draft)
        updated = await self.repository.update_capability(capability_id, draft)
        await self._refresh_solution_shas_for_capability(updated)
        return updated

    async def get_capability_schema(self, capability_id: UUID) -> dict:
        capability = await self.get_capability(capability_id)
        return build_user_schema(capability)

    async def list_solutions(self, name: str | None = None) -> list[Solution]:
        return await self.repository.list_solutions(name)

    async def get_solution(self, solution_id: UUID) -> tuple[Solution, list[SolutionStep], dict[UUID, Capability]]:
        solution = await self.repository.get_solution(solution_id)
        if solution is None:
            raise NotFoundError(f"Solution {solution_id} not found")
        steps = await self.repository.get_solution_steps(solution_id)
        capability_ids = [step.capability_id for step in steps if step.capability_id is not None]
        capabilities = await self.repository.get_capabilities(capability_ids)
        return solution, steps, capabilities

    async def get_solution_by_name_or_alias(
        self,
        name: str,
    ) -> tuple[Solution, list[SolutionStep], dict[UUID, Capability]]:
        solution = await self.repository.get_solution_by_name_or_alias(name)
        if solution is None:
            raise NotFoundError(f"Solution {name!r} not found")
        steps = await self.repository.get_solution_steps(solution.id)
        capability_ids = [step.capability_id for step in steps if step.capability_id is not None]
        capabilities = await self.repository.get_capabilities(capability_ids)
        return solution, steps, capabilities

    async def create_solution(
        self,
        draft: SolutionDraft,
        steps: list[SolutionStepDraft],
    ) -> Solution:
        capabilities = await self.repository.get_capabilities(
            [step.capability_id for step in steps if step.capability_id is not None]
        )
        await self._validate_steps(steps, capabilities)
        draft.version = 1
        draft.sha = self._compute_solution_sha(draft, steps, capabilities)
        return await self.repository.create_solution(draft, steps)

    async def update_solution(
        self,
        solution_id: UUID,
        description: str | None = None,
        user_params: dict | None = None,
        steps: list[SolutionStepDraft] | None = None,
    ) -> Solution:
        current, current_steps, capabilities = await self.get_solution(solution_id)
        next_steps = steps if steps is not None else [
            SolutionStepDraft(
                step_id=step.step_id,
                step_type=step.step_type,
                capability_id=step.capability_id,
                position=step.position,
                depends_on=list(step.depends_on),
                user_params=dict(step.user_params),
                internal_config=dict(step.internal_config),
            )
            for step in current_steps
        ]
        if steps is not None:
            capabilities = await self.repository.get_capabilities(
                [step.capability_id for step in next_steps if step.capability_id is not None]
            )
        await self._validate_steps(next_steps, capabilities)

        draft = SolutionDraft(
            name=current.name,
            description=current.description if description is None else description,
            user_params=current.user_params if user_params is None else user_params,
            internal_config=current.internal_config,
            version=current.version + 1,
        )
        draft.sha = self._compute_solution_sha(draft, next_steps, capabilities)
        return await self.repository.update_solution(solution_id, draft, next_steps)

    async def delete_solution(self, solution_id: UUID) -> None:
        solution = await self.repository.get_solution(solution_id)
        if solution is None:
            raise NotFoundError(f"Solution {solution_id} not found")
        if await self.repository.has_active_assignments(solution_id):
            raise ConflictError(
                f"Solution {solution.name} has active sensor assignments and cannot be deleted"
            )
        await self.repository.delete_solution(solution_id)

    async def get_solution_config(self, solution_id: UUID) -> dict:
        solution, steps, capabilities = await self.get_solution(solution_id)
        return resolve_solution_config(solution, steps, capabilities)

    async def get_solution_config_by_name_or_alias(self, name: str) -> dict:
        solution, steps, capabilities = await self.get_solution_by_name_or_alias(name)
        return resolve_solution_config(solution, steps, capabilities)

    async def list_sensor_assignments(self, sensor_id: str) -> list[dict]:
        assignments = await self.repository.list_sensor_assignments(sensor_id)
        result: list[dict] = []
        for assignment in assignments:
            solution = await self.repository.get_solution(assignment.solution_id)
            if solution is None:
                continue
            result.append(
                {
                    "assignment": assignment,
                    "solution": solution,
                    "drifted": assignment.solution_sha != solution.sha,
                }
            )
        return result

    async def create_sensor_assignment(
        self,
        sensor_id: str,
        solution_id: UUID,
        config_overrides: dict,
        is_active: bool = True,
    ) -> SensorAssignment:
        solution = await self.repository.get_solution(solution_id)
        if solution is None:
            raise NotFoundError(f"Solution {solution_id} not found")
        draft = SensorAssignmentDraft(
            sensor_id=sensor_id,
            solution_id=solution_id,
            is_active=is_active,
            config_overrides=config_overrides,
            solution_sha=solution.sha,
        )
        return await self.repository.create_sensor_assignment(draft)

    async def update_sensor_assignment(
        self,
        sensor_id: str,
        assignment_id: UUID,
        is_active: bool | None,
        config_overrides: dict | None,
    ) -> SensorAssignment:
        assignment = await self.repository.get_sensor_assignment(sensor_id, assignment_id)
        if assignment is None:
            raise NotFoundError(f"Camera assignment {assignment_id} not found")
        solution = await self.repository.get_solution(assignment.solution_id)
        if solution is None:
            raise NotFoundError(f"Solution {assignment.solution_id} not found")
        draft = SensorAssignmentDraft(
            sensor_id=sensor_id,
            solution_id=assignment.solution_id,
            is_active=assignment.is_active if is_active is None else is_active,
            config_overrides=assignment.config_overrides if config_overrides is None else config_overrides,
            solution_sha=solution.sha,
        )
        return await self.repository.update_sensor_assignment(sensor_id, assignment_id, draft)

    async def delete_sensor_assignment(self, sensor_id: str, assignment_id: UUID) -> None:
        assignment = await self.repository.get_sensor_assignment(sensor_id, assignment_id)
        if assignment is None:
            raise NotFoundError(f"Camera assignment {assignment_id} not found")
        await self.repository.delete_sensor_assignment(sensor_id, assignment_id)

    async def get_sensor_assignment_config(self, sensor_id: str, assignment_id: UUID) -> dict:
        assignment = await self.repository.get_sensor_assignment(sensor_id, assignment_id)
        if assignment is None:
            raise NotFoundError(f"Camera assignment {assignment_id} not found")
        solution, steps, capabilities = await self.get_solution(assignment.solution_id)
        return resolve_solution_config(solution, steps, capabilities, assignment=assignment)

    async def _refresh_solution_shas_for_capability(self, capability: Capability) -> None:
        solution_ids = await self.repository.list_solution_ids_for_capability(capability.id)
        for solution_id in solution_ids:
            solution = await self.repository.get_solution(solution_id)
            if solution is None:
                continue
            steps = await self.repository.get_solution_steps(solution_id)
            capability_ids = [step.capability_id for step in steps if step.capability_id is not None]
            capabilities = await self.repository.get_capabilities(capability_ids)
            capabilities[capability.id] = capability
            draft_steps = [
                SolutionStepDraft(
                    step_id=step.step_id,
                    step_type=step.step_type,
                    capability_id=step.capability_id,
                    position=step.position,
                    depends_on=list(step.depends_on),
                    user_params=dict(step.user_params),
                    internal_config=dict(step.internal_config),
                )
                for step in steps
            ]
            next_sha = self._compute_solution_sha(
                SolutionDraft(
                    name=solution.name,
                    description=solution.description,
                    user_params=solution.user_params,
                    internal_config=solution.internal_config,
                    version=solution.version,
                ),
                draft_steps,
                capabilities,
            )
            if next_sha != solution.sha:
                await self.repository.update_solution_sha(solution.id, next_sha)

    def _compute_capability_sha(self, draft: AnyCapabilityDraft) -> str:
        if isinstance(draft, ModelCapabilityDraft):
            return compute_sha({
                "kind": "model",
                "capability_type": draft.capability_type,
                "algorithm": draft.algorithm,
                "model_name": draft.model_name,
                "model_version": draft.model_version,
                "confidence_threshold": draft.confidence_threshold,
                "user_params": draft.user_params,
            })
        return compute_sha({
            "kind": "classic_algorithm",
            "capability_type": draft.capability_type,
            "algorithm": draft.algorithm,
            "user_params": draft.user_params,
        })

    def _compute_solution_sha(
        self,
        draft: SolutionDraft,
        steps: list[SolutionStepDraft],
        capabilities: dict[UUID, Capability],
    ) -> str:
        serialized_steps = []
        for step in sorted(steps, key=lambda item: item.position):
            capability_sha = None
            if step.capability_id is not None:
                capability = capabilities.get(step.capability_id)
                if capability is None:
                    raise ValidationError(
                        f"Capability {step.capability_id} not found for step {step.step_id}"
                    )
                capability_sha = capability.sha
            serialized_steps.append({
                "step_id": step.step_id,
                "step_type": step.step_type,
                "position": step.position,
                "depends_on": step.depends_on,
                "capability_sha": capability_sha,
                "user_params": step.user_params,
            })
        return compute_sha({
            "name": draft.name,
            "steps": serialized_steps,
            "user_params": draft.user_params,
        })

    async def _validate_steps(
        self,
        steps: list[SolutionStepDraft],
        capabilities: dict[UUID, Capability],
    ) -> None:
        seen_ids: set[str] = set()
        seen_positions: set[int] = set()
        for index, step in enumerate(steps):
            self._validate_step_capability_contract(step, capabilities)
            if step.step_id in seen_ids:
                raise ValidationError(f"Duplicate step_id {step.step_id!r}")
            seen_ids.add(step.step_id)
            if step.position in seen_positions:
                raise ValidationError(f"Duplicate position {step.position}")
            seen_positions.add(step.position)
            if step.position != index:
                raise ValidationError(
                    "Steps must use contiguous zero-based positions matching request order"
                )
            unknown_dependencies = [dep for dep in step.depends_on if dep not in seen_ids]
            if unknown_dependencies:
                raise ValidationError(
                    f"Step {step.step_id!r} depends on unknown prior steps: {unknown_dependencies}"
                )

    def _validate_step_capability_contract(
        self,
        step: SolutionStepDraft,
        capabilities: dict[UUID, Capability],
    ) -> None:
        if step.step_type not in VALID_SOLUTION_STEP_TYPES:
            raise ValidationError(
                f"Step {step.step_id!r} has unsupported step_type={step.step_type!r}"
            )
        if step.step_type in _INFERENCE_STEP_TYPES and step.capability_id is None:
            raise ValidationError(
                f"Step {step.step_id!r} with step_type={step.step_type!r} requires a capability_id"
            )
        if step.capability_id is None:
            return
        capability = capabilities.get(step.capability_id)
        if capability is None:
            raise ValidationError(
                f"Step {step.step_id!r} references unknown capability {step.capability_id}"
            )
        if step.step_type in _INFERENCE_STEP_TYPES and not isinstance(capability, ModelCapability):
            raise ValidationError(
                f"Step {step.step_id!r} with step_type={step.step_type!r} requires a 'model' capability, got '{capability.kind}'"
            )
        if step.step_type not in _INFERENCE_STEP_TYPES and isinstance(capability, ModelCapability):
            raise ValidationError(
                f"Step {step.step_id!r} with step_type={step.step_type!r} must reference a 'classic_algorithm' capability, got 'model'"
            )
