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


def _opt_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


def _snapshot_from(data: dict) -> CapabilitySnapshot:
    # service capabilities carry a free-form `cost` dict (different schema);
    # only inference_cost has the InferenceCost shape
    raw_cost = data.get("inference_cost")
    return CapabilitySnapshot(
        id=UUID(data["id"]),
        kind=data["kind"],
        sha=data["sha"],
        cost=_inference_cost_from(raw_cost),
        status=data.get("status", "draft"),
        blueprint_id=_opt_uuid(data.get("blueprint_id")),
        default_foundation_id=_opt_uuid(data.get("default_foundation_id")),
    )
