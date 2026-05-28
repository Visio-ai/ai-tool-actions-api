from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4, UUID

import pytest

from capabilities_solutions_api.adapters.capabilities_client import CapabilitySnapshot
from capabilities_solutions_api.app.use_cases.catalog_service import (
    ToolActionCatalogService,
    _resolve_step_capability,
)
from capabilities_solutions_api.domain.errors import ConflictError, NotFoundError, ValidationError
from capabilities_solutions_api.domain.models import (
    ActionStep,
    ActionStepDraft,
    InferenceCost,
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
        cost=_cost(),
        status="active",
    )
    caps_client = AsyncMock()
    caps_client.get.return_value = snap

    svc = _make_service(repo=repo, caps_client=caps_client)
    pricing = await svc.get_pricing(ta.id)
    assert pricing.tool_action_id == ta.id
    assert pricing.totals.cost_per_frame_usd == pytest.approx(0.001)
    assert pricing.totals.hardware == "T4"


def _cost() -> InferenceCost:
    return InferenceCost(
        hardware="T4",
        rate_per_hour_usd=0.5,
        inference_time_ms_per_frame=10.0,
        cost_per_frame_usd=0.001,
        cost_per_camera_day_usd_at_15fps=2.0,
    )


@pytest.mark.asyncio
async def test_resolve_non_blueprint_returns_self():
    cap_id = uuid4()
    cost = _cost()
    client = AsyncMock()
    client.get.return_value = CapabilitySnapshot(
        id=cap_id, kind="model", sha="sha_model", cost=cost, status="active"
    )

    resolved = await _resolve_step_capability(cap_id, client)

    assert resolved.source == "self"
    assert resolved.capability_id == cap_id
    assert resolved.kind == "model"
    assert resolved.sha == "sha_model"
    assert resolved.cost is cost
    client.list_trained_for_blueprint.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_blueprint_prefers_trained_model():
    bp_id, trained_id = uuid4(), uuid4()
    trained_cost = _cost()
    client = AsyncMock()
    client.get.return_value = CapabilitySnapshot(
        id=bp_id, kind="model_blueprint", sha="sha_bp", cost=None,
        default_foundation_id=uuid4(),
    )
    client.list_trained_for_blueprint.return_value = [
        CapabilitySnapshot(id=trained_id, kind="model", sha="sha_trained", cost=trained_cost, status="active")
    ]

    resolved = await _resolve_step_capability(bp_id, client)

    assert resolved.source == "trained_model"
    assert resolved.capability_id == trained_id
    assert resolved.sha == "sha_trained"
    assert resolved.cost is trained_cost
    client.list_trained_for_blueprint.assert_awaited_once_with(bp_id, status="active")
    # default foundation must not be fetched when a trained model exists
    client.get.assert_awaited_once_with(bp_id)


@pytest.mark.asyncio
async def test_resolve_blueprint_falls_back_to_default_foundation():
    bp_id, foundation_id = uuid4(), uuid4()
    foundation_cost = _cost()
    bp_snap = CapabilitySnapshot(
        id=bp_id, kind="model_blueprint", sha="sha_bp", cost=None,
        default_foundation_id=foundation_id,
    )
    foundation_snap = CapabilitySnapshot(
        id=foundation_id, kind="foundation_model", sha="sha_fnd", cost=foundation_cost, status="active"
    )
    client = AsyncMock()
    client.get.side_effect = [bp_snap, foundation_snap]
    client.list_trained_for_blueprint.return_value = []

    resolved = await _resolve_step_capability(bp_id, client)

    assert resolved.source == "default_foundation"
    assert resolved.capability_id == foundation_id
    assert resolved.sha == "sha_fnd"
    assert resolved.cost is foundation_cost


@pytest.mark.asyncio
async def test_resolve_blueprint_unresolved_without_trained_or_foundation():
    bp_id = uuid4()
    client = AsyncMock()
    client.get.return_value = CapabilitySnapshot(
        id=bp_id, kind="model_blueprint", sha="sha_bp", cost=None, default_foundation_id=None
    )
    client.list_trained_for_blueprint.return_value = []

    resolved = await _resolve_step_capability(bp_id, client)

    assert resolved.source == "unresolved"
    assert resolved.capability_id == bp_id
    assert resolved.sha == "sha_bp"
