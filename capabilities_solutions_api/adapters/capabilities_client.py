from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

from capabilities_solutions_api.domain.errors import NotFoundError
from capabilities_solutions_api.domain.models import InferenceCost


@dataclass(slots=True)
class CapabilitySnapshot:
    id: UUID
    kind: str
    sha: str
    cost: InferenceCost | None
    status: str = "draft"
    blueprint_id: UUID | None = None
    default_foundation_id: UUID | None = None


class CapabilitiesClient:
    def __init__(self, base_url: str, http_client: httpx.AsyncClient) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = http_client

    async def get(self, capability_id: UUID) -> CapabilitySnapshot:
        resp = await self._client.get(f"{self._base_url}/capabilities/{capability_id}")
        if resp.status_code == 404:
            raise NotFoundError(f"Capability {capability_id} not found in capabilities-api")
        resp.raise_for_status()
        return _snapshot_from(resp.json())

    async def get_by_sha(self, sha: str) -> CapabilitySnapshot | None:
        resp = await self._client.get(
            f"{self._base_url}/internal/capabilities/by-sha/{sha}"
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return _snapshot_from(resp.json())

    async def list_trained_for_blueprint(
        self, blueprint_id: UUID, status: str = "active"
    ) -> list[CapabilitySnapshot]:
        """Trained models instantiated from a blueprint, newest first (server-ordered)."""
        resp = await self._client.get(
            f"{self._base_url}/capabilities",
            params={"kind": "model", "blueprint_id": str(blueprint_id), "status": status},
        )
        resp.raise_for_status()
        return [_snapshot_from(item) for item in resp.json()]


SECONDS_PER_DAY_AT_15FPS = 15 * 86400  # 1_296_000


def _inference_cost_from(d: dict | None) -> InferenceCost | None:
    if not d:
        return None
    return InferenceCost(
        hardware=d.get("hardware", ""),
        rate_per_hour_usd=float(d.get("rate_per_hour_usd", 0.0)),
        inference_time_ms_per_frame=float(d.get("inference_time_ms_per_frame", 0.0)),
        cost_per_frame_usd=float(d.get("cost_per_frame_usd", 0.0)),
        cost_per_camera_day_usd_at_15fps=float(d.get("cost_per_camera_day_usd_at_15fps", 0.0)),
    )


def _inference_cost_from_metadata(metadata: dict | None) -> InferenceCost | None:
    """Build InferenceCost from the metadata shape (MD-loaded capabilities).

    metadata.cost_per_frame_usd is the canonical per-frame cost.
    metadata.performance.latency_ms and metadata.hardware.reference_gpu enrich
    the snapshot. rate_per_hour_usd is not modeled on the MD side, so the
    caller's pricing rollup loses that one number unless the legacy
    inference_cost blob is also present.
    """
    if not metadata:
        return None
    cpf = metadata.get("cost_per_frame_usd")
    if cpf is None:
        return None
    perf = metadata.get("performance") or {}
    hw = metadata.get("hardware") or {}
    return InferenceCost(
        hardware=hw.get("reference_gpu", "") or "",
        rate_per_hour_usd=0.0,
        inference_time_ms_per_frame=float(perf.get("latency_ms", 0.0) or 0.0),
        cost_per_frame_usd=float(cpf),
        cost_per_camera_day_usd_at_15fps=float(cpf) * SECONDS_PER_DAY_AT_15FPS,
    )


def _opt_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _snapshot_from(data: dict) -> CapabilitySnapshot:
    # Prefer the new metadata shape; fall back to the legacy inference_cost
    # blob so capabilities created before the MD migration still price.
    # service capabilities carry a free-form `cost` dict (different schema)
    # and contribute nothing here.
    cost = _inference_cost_from_metadata(data.get("metadata"))
    if cost is None:
        cost = _inference_cost_from(data.get("inference_cost"))
    return CapabilitySnapshot(
        id=UUID(data["id"]),
        kind=data["kind"],
        sha=data["sha"],
        cost=cost,
        status=data.get("status", "draft"),
        blueprint_id=_opt_uuid(data.get("blueprint_id")),
        default_foundation_id=_opt_uuid(data.get("default_foundation_id")),
    )
