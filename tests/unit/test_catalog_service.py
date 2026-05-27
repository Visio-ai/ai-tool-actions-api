from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4, UUID

import pytest

from capabilities_solutions_api.adapters.capabilities_client import CapabilitySnapshot
from capabilities_solutions_api.app.use_cases.catalog_service import ToolActionCatalogService
from capabilities_solutions_api.domain.errors import ConflictError, NotFoundError, ValidationError
from capabilities_solutions_api.domain.models import (
    ActionStep,
    ActionStepDraft,
    SensorAssignment,
    ToolAction,
    ToolActionDraft,
    ToolActionSLA,
)

from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_step(step_id: str = "od", position: int = 0, cap_sha: str = "abc") -> ActionStep:
    return ActionStep(
        id=uuid4(),
        tool_action_id=uuid4(),
        step_id=step_id,
        step_type="model",
        capability_id=None,
        capability_sha=cap_sha,
        position=position,
        depends_on=[],
        user_params={},
        internal_config={},
        created_at=_now(),
    )


def _make_tool_action(**overrides) -> ToolAction:
    defaults = dict(
        id=uuid4(),
        name="person-heatmap",
        display_name="",
        category="spatial-analytics",
        status="active",
        sensor_type="camera",
        supported_modes=["video"],
        setup={},
        output_schema_ref="schemas/ph/v1",
        use_cases="",
        technical_overview="",
        limitations="",
        version=1,
        sha="abc123sha16cha",
        user_params={},
        internal_config={},
        created_at=_now(),
        updated_at=_now(),
        slas=[ToolActionSLA(delivery_mode="video", sla_seconds=60)],
        steps=[_make_step()],
    )
    defaults.update(overrides)
    return ToolAction(**defaults)


def _make_service(repo=None, caps_client=None):
    if repo is None:
        repo = AsyncMock()
    if caps_client is None:
        caps_client = AsyncMock()
    return ToolActionCatalogService(repository=repo, capabilities_client=caps_client)


@pytest.mark.asyncio
async def test_get_tool_action_not_found():
    repo = AsyncMock()
    repo.get_tool_action.return_value = None
    svc = _make_service(repo=repo)
    with pytest.raises(NotFoundError):
        await svc.get_tool_action(uuid4())


@pytest.mark.asyncio
async def test_create_tool_action_conflict():
    repo = AsyncMock()
    existing = _make_tool_action()
    repo.get_tool_action_by_sha.return_value = existing
    svc = _make_service(repo=repo)
    draft = ToolActionDraft(
        name="person-heatmap",
        supported_modes=["video"],
        slas=[ToolActionSLA(delivery_mode="video", sla_seconds=60)],
    )
    with pytest.raises(ConflictError):
        await svc.create_tool_action(draft)


@pytest.mark.asyncio
async def test_create_resolves_capability_sha():
    cap_id = uuid4()
    snap = CapabilitySnapshot(id=cap_id, kind="model", sha="resolved_sha_xx", cost=None)
    caps_client = AsyncMock()
    caps_client.get.return_value = snap

    repo = AsyncMock()
    repo.get_tool_action_by_sha.return_value = None
    repo.create_tool_action.side_effect = lambda draft: _make_tool_action(name=draft.name)
    svc = _make_service(repo=repo, caps_client=caps_client)

    draft = ToolActionDraft(
        name="test-action",
        steps=[
            ActionStepDraft(step_id="od", step_type="model", capability_id=cap_id, position=0)
        ],
    )
    await svc.create_tool_action(draft)
    assert draft.steps[0].capability_sha == "resolved_sha_xx"
    caps_client.get.assert_called_once_with(cap_id)


@pytest.mark.asyncio
async def test_create_skips_resolution_if_sha_already_set():
    caps_client = AsyncMock()
    repo = AsyncMock()
    repo.get_tool_action_by_sha.return_value = None
    repo.create_tool_action.side_effect = lambda draft: _make_tool_action(name=draft.name)
    svc = _make_service(repo=repo, caps_client=caps_client)

    draft = ToolActionDraft(
        name="test-action",
        steps=[
            ActionStepDraft(
                step_id="od",
                step_type="model",
                capability_id=uuid4(),
                capability_sha="already_set_sha",
                position=0,
            )
        ],
    )
    await svc.create_tool_action(draft)
    caps_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_validation_rejects_invalid_step_type():
    svc = _make_service()
    draft = ToolActionDraft(
        name="bad-action",
        steps=[ActionStepDraft(step_id="x", step_type="invalid_type", position=0)],
    )
    with pytest.raises(ValidationError, match="invalid_type"):
        await svc.create_tool_action(draft)


@pytest.mark.asyncio
async def test_get_pricing_aggregates_by_type():
    cap_id = uuid4()
    ta = _make_tool_action(
        steps=[
            ActionStep(
                id=uuid4(),
                tool_action_id=uuid4(),
                step_id="od",
                step_type="model",
                capability_id=cap_id,
                capability_sha="sha1",
                position=0,
                depends_on=[],
                user_params={},
                internal_config={},
                created_at=_now(),
            )
        ]
    )
    repo = AsyncMock()
    repo.get_tool_action.return_value = ta

    snap = CapabilitySnapshot(
        id=cap_id,
        kind="model",
        sha="sha1",
        cost={"cost_type": "per_frame", "unit_cost_usd": 0.000002},
    )
    caps_client = AsyncMock()
    caps_client.get.return_value = snap

    svc = _make_service(repo=repo, caps_client=caps_client)
    pricing = await svc.get_pricing(ta.id)
    assert pricing["totals_by_type"]["per_frame"] == pytest.approx(0.000002)
    assert len(pricing["breakdown"]) == 1
