from capabilities_solutions_api.domain.sha import compute_sha


def test_compute_sha_is_stable_for_key_order() -> None:
    left = {"name": "solution", "steps": [{"a": 1, "b": 2}], "user_params": {"x": 1, "y": 2}}
    right = {"user_params": {"y": 2, "x": 1}, "steps": [{"b": 2, "a": 1}], "name": "solution"}

    assert compute_sha(left) == compute_sha(right)
