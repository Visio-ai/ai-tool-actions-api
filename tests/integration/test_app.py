from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient


_TOOL_ACTION_PAYLOAD = {
    "name": "person-heatmap",
    "display_name": "Person Heatmap",
    "category": "spatial-analytics",
    "status": "active",
    "sensor_type": "camera",
    "supported_modes": ["video", "snap"],
    "setup": {"mounting": "ceiling", "fps_default": 15},
    "output_schema_ref": "schemas/person-heatmap-output/v1",
    "use_cases": "Retail traffic analysis",
    "technical_overview": "Accumulates bbox centers into 2D grid",
    "limitations": "Accuracy depends on upstream detector",
    "slas": [
        {"delivery_mode": "video", "sla_seconds": 60},
        {"delivery_mode": "snap", "sla_seconds": 600},
    ],
    "steps": [
        {
            "step_id": "person-detection",
            "step_type": "model",
            "capability_sha": "abc123mock",
            "position": 0,
            "depends_on": [],
            "user_params": {"confidence_threshold": 0.3},
        },
        {
            "step_id": "heatmap-accumulation",
            "step_type": "classic_algorithm",
            "capability_sha": "def456mock",
            "position": 1,
            "depends_on": ["person-detection"],
            "user_params": {"grid_width": 100, "grid_height": 100, "window_minutes": 60},
        },
    ],
}


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_create_and_get_tool_action(client: AsyncClient) -> None:
    resp = await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["name"] == "person-heatmap"
    assert data["status"] == "active"
    assert len(data["steps"]) == 2
    assert len(data["slas"]) == 2
    assert data["sha"] != ""

    ta_id = data["id"]
    resp2 = await client.get(f"/tool-actions/{ta_id}")
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "person-heatmap"


@pytest.mark.asyncio
async def test_list_tool_actions(client: AsyncClient) -> None:
    await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    resp = await client.get("/tool-actions")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_list_filter_by_status(client: AsyncClient) -> None:
    await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    resp = await client.get("/tool-actions?status=active")
    assert resp.status_code == 200
    for ta in resp.json():
        assert ta["status"] == "active"


@pytest.mark.asyncio
async def test_update_tool_action(client: AsyncClient) -> None:
    resp = await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    assert resp.status_code == 201, resp.text
    ta_id = resp.json()["id"]

    patch_resp = await client.patch(f"/tool-actions/{ta_id}", json={"status": "deprecated"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "deprecated"


@pytest.mark.asyncio
async def test_delete_tool_action(client: AsyncClient) -> None:
    resp = await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    assert resp.status_code == 201, resp.text
    ta_id = resp.json()["id"]

    del_resp = await client.delete(f"/tool-actions/{ta_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/tool-actions/{ta_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_config(client: AsyncClient) -> None:
    resp = await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    assert resp.status_code == 201, resp.text
    ta_id = resp.json()["id"]

    config_resp = await client.get(f"/tool-actions/{ta_id}/config")
    assert config_resp.status_code == 200
    config = config_resp.json()
    assert config["name"] == "person-heatmap"
    assert config["output_schema_ref"] == "schemas/person-heatmap-output/v1"
    assert len(config["steps"]) == 2


@pytest.mark.asyncio
async def test_get_pricing(client: AsyncClient, mock_capabilities_client) -> None:
    cap_id = str(uuid4())
    payload = dict(_TOOL_ACTION_PAYLOAD)
    payload["name"] = "pricing-test-action"
    payload["steps"] = [
        {
            "step_id": "od",
            "step_type": "model",
            "capability_id": cap_id,
            "capability_sha": "",
            "position": 0,
            "depends_on": [],
            "user_params": {},
        },
    ]
    resp = await client.post("/tool-actions", json=payload)
    assert resp.status_code == 201, resp.text
    ta_id = resp.json()["id"]

    pricing_resp = await client.get(f"/tool-actions/{ta_id}/pricing")
    assert pricing_resp.status_code == 200
    pricing = pricing_resp.json()
    assert pricing["tool_action_id"] == ta_id
    # single model step -> totals equal the mocked capability's inference cost
    assert pricing["totals"]["cost_per_frame_usd"] == pytest.approx(0.000002)
    assert pricing["totals"]["hardware"] == "T4"


@pytest.mark.asyncio
async def test_get_tool_action_by_name(client: AsyncClient) -> None:
    await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    resp = await client.get("/internal/tool-actions/by-name/person-heatmap")
    assert resp.status_code == 200
    assert resp.json()["name"] == "person-heatmap"


@pytest.mark.asyncio
async def test_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/tool-actions/{uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_name_conflict(client: AsyncClient) -> None:
    await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    resp2 = await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_sensor_assignment_crud(client: AsyncClient) -> None:
    resp = await client.post("/tool-actions", json=_TOOL_ACTION_PAYLOAD)
    assert resp.status_code == 201, resp.text
    ta_id = resp.json()["id"]
    sensor_id = "cam-001"

    create_resp = await client.post(
        f"/sensors/{sensor_id}/tool-actions",
        json={"tool_action_id": ta_id, "is_active": True, "config_overrides": {}},
    )
    assert create_resp.status_code == 201
    sa = create_resp.json()
    assert sa["sensor_id"] == sensor_id
    assert sa["tool_action_id"] == ta_id
    assert sa["tool_action_sha"] != ""

    list_resp = await client.get(f"/sensors/{sensor_id}/tool-actions")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    get_resp = await client.get(f"/sensors/{sensor_id}/tool-actions/{ta_id}")
    assert get_resp.status_code == 200

    patch_resp = await client.patch(
        f"/sensors/{sensor_id}/tool-actions/{ta_id}",
        json={"is_active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_active"] is False

    del_resp = await client.delete(f"/sensors/{sensor_id}/tool-actions/{ta_id}")
    assert del_resp.status_code == 204

    list_after = await client.get(f"/sensors/{sensor_id}/tool-actions")
    assert list_after.json() == []
