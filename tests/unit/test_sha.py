from __future__ import annotations

from capabilities_solutions_api.domain.models import ActionStepDraft, ToolActionDraft, ToolActionSLA
from capabilities_solutions_api.domain.sha import compute_tool_action_sha


def _make_draft(**overrides) -> ToolActionDraft:
    draft = ToolActionDraft(
        name="person-heatmap",
        sensor_type="camera",
        supported_modes=["video", "snap"],
        setup={"mounting": "ceiling"},
        output_schema_ref="schemas/person-heatmap-output/v1",
        slas=[ToolActionSLA(delivery_mode="video", sla_seconds=60)],
        steps=[
            ActionStepDraft(
                step_id="od",
                step_type="model",
                capability_sha="abc123",
                position=0,
            )
        ],
    )
    for k, v in overrides.items():
        setattr(draft, k, v)
    return draft


def test_sha_is_16_chars():
    assert len(compute_tool_action_sha(_make_draft())) == 16


def test_sha_deterministic():
    assert compute_tool_action_sha(_make_draft()) == compute_tool_action_sha(_make_draft())


def test_sha_changes_on_name_change():
    assert compute_tool_action_sha(_make_draft()) != compute_tool_action_sha(_make_draft(name="other"))


def test_sha_changes_on_output_schema_ref_change():
    d1 = _make_draft()
    d2 = _make_draft(output_schema_ref="schemas/other/v2")
    assert compute_tool_action_sha(d1) != compute_tool_action_sha(d2)


def test_sha_changes_on_capability_sha_change():
    d1 = _make_draft()
    d2 = _make_draft(
        steps=[ActionStepDraft(step_id="od", step_type="model", capability_sha="diff", position=0)]
    )
    assert compute_tool_action_sha(d1) != compute_tool_action_sha(d2)


def test_sha_stable_on_descriptive_fields():
    base_sha = compute_tool_action_sha(_make_draft())
    d2 = _make_draft(
        display_name="New Display",
        use_cases="New use cases",
        technical_overview="Updated overview",
        limitations="New limitations",
    )
    assert compute_tool_action_sha(d2) == base_sha


def test_sha_stable_on_status_change():
    assert compute_tool_action_sha(_make_draft(status="draft")) == compute_tool_action_sha(_make_draft(status="active"))


def test_sha_changes_on_sla_change():
    d1 = _make_draft(slas=[ToolActionSLA(delivery_mode="video", sla_seconds=60)])
    d2 = _make_draft(slas=[ToolActionSLA(delivery_mode="video", sla_seconds=120)])
    assert compute_tool_action_sha(d1) != compute_tool_action_sha(d2)


def test_sha_independent_of_modes_order():
    d1 = _make_draft(supported_modes=["video", "snap"])
    d2 = _make_draft(supported_modes=["snap", "video"])
    assert compute_tool_action_sha(d1) == compute_tool_action_sha(d2)
