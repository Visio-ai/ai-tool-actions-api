from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from capabilities_solutions_api.domain.models import SolutionDraft


def _create_capability(client: TestClient, **overrides) -> dict:
    payload = {
        "capability_type": "object_detection",
        "algorithm": "rf-detr",
        "model_name": "od-rf-detr-plate-counting",
        "model_version": "0.1.0",
        "step_type": "async_inference",
        "confidence_threshold": 0.35,
        "user_params": {"frame_stride": 6},
        "internal_config": {
            "serve_endpoint": "http://od-rf-detr/process",
            "poll_interval_seconds": 30,
            "poll_timeout_seconds": 3600,
            "io_contract": {"payload_template": {"video_uri": "{request.model_input_meta.video_uri}"}},
        },
    }
    payload.update(overrides)
    response = client.post("/capabilities", json=payload)
    assert response.status_code == 201
    return response.json()


def _create_solution(client: TestClient, capability_id: str, **overrides) -> dict:
    payload = {
        "name": "plate_counting_divino_fogao_v2",
        "description": "Integration test solution",
        "user_params": {"zones": [{"id": "base"}]},
        "steps": [
            {
                "step_id": "detect_video",
                "step_type": "async_inference",
                "capability_id": capability_id,
                "depends_on": [],
                "user_params": {"confidence_threshold": 0.5, "fps": 2.5},
            }
        ],
    }
    payload.update(overrides)
    response = client.post("/solutions", json=payload)
    assert response.status_code == 201
    return response.json()


def test_capability_solution_and_assignment_flow(client: TestClient) -> None:
    capability = _create_capability(client)
    solution = _create_solution(client, capability["id"])

    config_response = client.get(f"/solutions/{solution['id']}/config")
    assert config_response.status_code == 200
    resolved = config_response.json()
    assert resolved["solution_id"] == "plate_counting_divino_fogao_v2"
    assert resolved["steps"][0]["serve_endpoint"] == "http://od-rf-detr/process"
    assert resolved["steps"][0]["params"]["frame_stride"] == 6
    assert resolved["steps"][0]["params"]["fps"] == 2.5

    assignment_response = client.post(
        "/sensors/checkout-dvf0002/solutions",
        json={
            "solution_id": solution["id"],
            "config_overrides": {"zones": [{"id": "camera"}]},
        },
    )
    assert assignment_response.status_code == 201
    assignment = assignment_response.json()
    assert assignment["drifted"] is False

    assignment_config_response = client.get(
        f"/sensors/checkout-dvf0002/solutions/{assignment['id']}/config"
    )
    assert assignment_config_response.status_code == 200
    assignment_config = assignment_config_response.json()
    assert assignment_config["user_params"]["zones"] == [{"id": "camera"}]

    delete_response = client.delete(f"/solutions/{solution['id']}")
    assert delete_response.status_code == 409


def test_capability_schema_internal_config_and_patch_update_sha(client: TestClient) -> None:
    capability = _create_capability(client)

    schema_response = client.get(f"/capabilities/{capability['id']}/schema")
    assert schema_response.status_code == 200
    assert schema_response.json()["schema"]["properties"]["user_params"]["properties"]["frame_stride"]["type"] == "integer"

    internal_config_response = client.get(f"/capabilities/{capability['id']}/internal-config")
    assert internal_config_response.status_code == 200
    assert internal_config_response.json()["internal_config"]["serve_endpoint"] == "http://od-rf-detr/process"

    patch_response = client.patch(
        f"/capabilities/{capability['id']}",
        json={
            "confidence_threshold": 0.55,
            "user_params": {"frame_stride": 3, "fps": 2.5},
        },
    )
    assert patch_response.status_code == 200
    updated = patch_response.json()

    assert updated["confidence_threshold"] == 0.55
    assert updated["user_params"] == {"frame_stride": 3, "fps": 2.5}
    assert updated["sha"] != capability["sha"]

    internal_config_response = client.get(f"/capabilities/{capability['id']}/internal-config")
    assert internal_config_response.status_code == 200
    assert internal_config_response.json()["internal_config"]["serve_endpoint"] == "http://od-rf-detr/process"


def test_solution_update_increments_version_and_marks_assignment_drift(client: TestClient) -> None:
    capability = _create_capability(client)
    solution = _create_solution(client, capability["id"])

    assignment_response = client.post(
        "/sensors/checkout-dvf0002/solutions",
        json={"solution_id": solution["id"], "config_overrides": {"zones": [{"id": "camera"}]}},
    )
    assert assignment_response.status_code == 201
    assignment = assignment_response.json()

    update_response = client.patch(
        f"/solutions/{solution['id']}",
        json={"user_params": {"zones": [{"id": "updated"}]}},
    )
    assert update_response.status_code == 200
    updated_solution = update_response.json()

    assert updated_solution["version"] == 2
    assert updated_solution["sha"] != solution["sha"]

    assignments_response = client.get("/sensors/checkout-dvf0002/solutions")
    assert assignments_response.status_code == 200
    assignments = assignments_response.json()
    assert assignments[0]["id"] == assignment["id"]
    assert assignments[0]["drifted"] is True
    assert assignments[0]["solution_sha"] == assignment["solution_sha"]
    assert assignments[0]["current_solution_sha"] == updated_solution["sha"]


def test_capability_update_cascades_solution_sha_and_assignment_drift(client: TestClient) -> None:
    capability = _create_capability(client)
    solution = _create_solution(client, capability["id"])

    assignment_response = client.post(
        "/sensors/checkout-dvf0002/solutions",
        json={"solution_id": solution["id"], "config_overrides": {}},
    )
    assert assignment_response.status_code == 201
    assignment = assignment_response.json()

    patch_response = client.patch(
        f"/capabilities/{capability['id']}",
        json={
            "confidence_threshold": 0.6,
            "user_params": {"frame_stride": 2, "fps": 3.0},
        },
    )
    assert patch_response.status_code == 200
    updated_capability = patch_response.json()
    assert updated_capability["sha"] != capability["sha"]

    solution_response = client.get(f"/solutions/{solution['id']}")
    assert solution_response.status_code == 200
    updated_solution = solution_response.json()
    assert updated_solution["sha"] != solution["sha"]
    assert updated_solution["version"] == solution["version"]

    assignments_response = client.get("/sensors/checkout-dvf0002/solutions")
    assert assignments_response.status_code == 200
    assignments = assignments_response.json()
    assert assignments[0]["id"] == assignment["id"]
    assert assignments[0]["drifted"] is True
    assert assignments[0]["solution_sha"] == assignment["solution_sha"]
    assert assignments[0]["current_solution_sha"] == updated_solution["sha"]

    config_response = client.get(f"/solutions/{solution['id']}/config")
    assert config_response.status_code == 200
    resolved = config_response.json()
    assert resolved["steps"][0]["confidence_threshold"] == 0.5
    assert resolved["steps"][0]["params"]["frame_stride"] == 2
    assert resolved["steps"][0]["params"]["fps"] == 2.5


def test_solution_delete_succeeds_after_assignment_is_inactive(client: TestClient) -> None:
    capability = _create_capability(client)
    solution = _create_solution(client, capability["id"])

    assignment_response = client.post(
        "/sensors/checkout-dvf0002/solutions",
        json={"solution_id": solution["id"], "config_overrides": {}},
    )
    assert assignment_response.status_code == 201
    assignment = assignment_response.json()

    deactivate_response = client.patch(
        f"/sensors/checkout-dvf0002/solutions/{assignment['id']}",
        json={"is_active": False},
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    delete_response = client.delete(f"/solutions/{solution['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/solutions/{solution['id']}")
    assert get_response.status_code == 404

    assignments_response = client.get("/sensors/checkout-dvf0002/solutions")
    assert assignments_response.status_code == 200
    assert assignments_response.json() == []


def test_solution_creation_validates_dependencies(client: TestClient) -> None:
    capability = _create_capability(client)

    response = client.post(
        "/solutions",
        json={
            "name": "invalid_solution",
            "description": "Invalid dependency order",
            "user_params": {},
            "steps": [
                {
                    "step_id": "track",
                    "step_type": "async_inference",
                    "capability_id": capability["id"],
                    "depends_on": ["detect"],
                    "user_params": {},
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "unknown prior steps" in response.json()["detail"]


def test_invalid_capability_step_type_returns_database_constraint_error(client: TestClient) -> None:
    response = client.post(
        "/capabilities",
        json={
            "capability_type": "object_detection",
            "algorithm": "rf-detr",
            "model_name": "od-rf-detr-plate-counting",
            "model_version": "0.1.0",
            "step_type": "unsupported",
            "confidence_threshold": 0.35,
            "user_params": {},
            "internal_config": {},
        },
    )

    assert response.status_code == 422
    assert "step_type" in response.json()["detail"]


def test_invalid_solution_step_type_returns_database_constraint_error(client: TestClient) -> None:
    capability = _create_capability(client)

    response = client.post(
        "/solutions",
        json={
            "name": "invalid_step_type_solution",
            "description": "Invalid step type",
            "user_params": {},
            "steps": [
                {
                    "step_id": "detect_video",
                    "step_type": "unsupported",
                    "capability_id": capability["id"],
                    "depends_on": [],
                    "user_params": {},
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "step_type" in response.json()["detail"]


def test_duplicate_solution_name_returns_conflict(client: TestClient) -> None:
    capability = _create_capability(client)
    _create_solution(client, capability["id"])

    response = client.post(
        "/solutions",
        json={
            "name": "plate_counting_divino_fogao_v2",
            "description": "Duplicate",
            "user_params": {},
            "steps": [
                {
                    "step_id": "detect_video",
                    "step_type": "async_inference",
                    "capability_id": capability["id"],
                    "depends_on": [],
                    "user_params": {},
                }
            ],
        },
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_internal_solution_lookup_supports_legacy_alias(client: TestClient) -> None:
    service = client.app.state.catalog_service
    asyncio.run(
        service.create_solution(
            SolutionDraft(
                name="plate_counting_divino_fogao_v2",
                description="With alias",
                user_params={},
                internal_config={
                    "pipeline_capability": "pipeline",
                    "legacy_aliases": ["video-od-tracking-divino-fogao"],
                },
            ),
            [],
        )
    )

    lookup_response = client.get("/internal/solutions/by-name/video-od-tracking-divino-fogao")
    assert lookup_response.status_code == 200
    assert lookup_response.json()["name"] == "plate_counting_divino_fogao_v2"
    assert lookup_response.json()["legacy_aliases"] == ["video-od-tracking-divino-fogao"]

    config_response = client.get("/internal/solutions/by-name/video-od-tracking-divino-fogao/config")
    assert config_response.status_code == 200
    assert config_response.json()["solution_id"] == "plate_counting_divino_fogao_v2"
    assert config_response.json()["capability"] == "pipeline"
    assert config_response.json()["steps"] == []
