"""Migrate visio-research-models pipeline configs into the split Capabilities &
Solutions APIs.

Architecture (post-split):
- ``visio-ai-capabilities-api`` owns *capabilities* (one per model / classic
  algorithm). A capability is identified by its ``sha`` (kind + capability_type
  + algorithm + model_name + model_version + confidence_threshold).
- This repo (``visio-processing-capabilities-solutions-api``) owns *tool actions*
  (a.k.a. solutions): an ordered chain of steps, each step referencing a
  capability by ``capability_id`` + ``capability_sha``.

Source of truth for a step's model version is the *pipeline step* itself
(``model_version`` in the config), NOT ``capabilities/{algo}/pyproject.toml`` and
NOT the detection manifest (which has no version). Capabilities are therefore
created with the step's version, and ``detections/*.yaml`` only *enriches* the
capability's non-sha metadata (HuggingFace model id, revision, serving) matched
by detection ``name`` == step ``model_name``. This guarantees the phase-2 step
always joins the phase-1 capability.

Transport is HTTP against both running APIs. Registration is idempotent
(upsert): capabilities are looked up by sha, tool actions by name.

Required env:
  RESEARCH_MODELS_REPO   path to a visio-research-models clone (for the pipeline
                         config loader and the detections/ directory).
Optional env:
  CAPABILITIES_API_URL   default http://localhost:8001
  SOLUTIONS_API_URL      default http://localhost:8000

Usage:
  RESEARCH_MODELS_REPO=../visio-research-models \
  CAPABILITIES_API_URL=http://localhost:8001 \
  SOLUTIONS_API_URL=http://localhost:8000 \
  python scripts/migrate_yaml_to_api.py [--dry-run]

Run notes:
- The interpreter must have the pipeline config loader importable (i.e. run with
  visio-research-models' venv, which also needs ``httpx`` installed) — this repo
  has no venv of its own and the loader lives in that repo.
- Re-runs are idempotent. On a tool-action update the ``PATCH`` refreshes both
  the step list and top-level ``internal_config`` (pipeline subscribers), so
  changes to ``pipeline__*.yaml`` subscribers propagate on a re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml

# ─── Locate visio-research-models so its pipeline config loader is importable ───

_RESEARCH_MODELS = os.environ.get("RESEARCH_MODELS_REPO")
if not _RESEARCH_MODELS:
    raise RuntimeError(
        "RESEARCH_MODELS_REPO env var required (path to a visio-research-models clone)"
    )
RESEARCH_MODELS_REPO = Path(_RESEARCH_MODELS).resolve()
_LOADER_SRC = RESEARCH_MODELS_REPO / "pipelines" / "_core" / "src"
if str(_LOADER_SRC) not in sys.path:
    sys.path.insert(0, str(_LOADER_SRC))

from pipeline.configs.loader import load_all_configs  # noqa: E402
from pipeline.models.pipeline_config import StepConfig  # noqa: E402

# ─── Step type / capability kind translation ───────────────────────────────────
# Pipeline step types are dispatched in ``_build_step`` to this repo's
# VALID_STEP_TYPES {model, classic_algorithm, service}. ``postprocess`` is a pure
# in-pipeline transform with no capability.

_MODEL_NAME_PREFIX_TO_TYPE = {
    "od-": "object-detection",
    "ot-": "object-tracking",
    "reid-": "re-identification",
    "vp-": "video-processing",
    "c-": "classification",
    "s-": "segmentation",
    "za-": "zone-analytics",
}

# Predictor module root -> capability_type, for local_capability steps that carry
# no model_name (only a ``params.predictor`` dotted path).
_PREDICTOR_PREFIX_TO_TYPE = {
    "za_zone_eval": "zone-analytics",
    "reid": "re-identification",
    "vacancy": "zone-analytics",
    "clip": "video-processing",
}

_ALGORITHM_TOKENS = (
    "rf-detr",
    "rt-detr-v2",
    "yolos",
    "dfine",
    "detr",
    "owlv2",
    "bytetrack",
    "sfsort",
    "csrt",
    "sam2",
    "fast-reid",
    "osnet",
    "tfrec",
)


# ─── sha helpers (mirror each API's canonical-JSON sha) ─────────────────────────

def _compute_sha(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _model_capability_sha(capability_type: str, algorithm: str, model_name: str,
                          model_version: str, confidence_threshold: float) -> str:
    # Mirrors capabilities_api.app.use_cases.catalog_service._compute_sha (model).
    return _compute_sha({
        "kind": "model",
        "capability_type": capability_type,
        "algorithm": algorithm,
        "model_name": model_name,
        "model_version": model_version,
        "confidence_threshold": confidence_threshold,
    })


def _classic_capability_sha(capability_type: str, algorithm: str) -> str:
    # Mirrors capabilities_api.app.use_cases.catalog_service._compute_sha (classic).
    return _compute_sha({
        "kind": "classic_algorithm",
        "capability_type": capability_type,
        "algorithm": algorithm,
    })


# ─── Inference helpers ──────────────────────────────────────────────────────────

def _infer_capability_type(step: StepConfig) -> str:
    name = (step.model_name or "").lower()
    for prefix, cap_type in _MODEL_NAME_PREFIX_TO_TYPE.items():
        if name.startswith(prefix):
            return cap_type
    predictor = step.params.get("predictor", "")
    if predictor:
        root = predictor.split(".", 1)[0]
        for prefix, cap_type in _PREDICTOR_PREFIX_TO_TYPE.items():
            if root.startswith(prefix):
                return cap_type
    return step.step_id


def _infer_algorithm(step: StepConfig) -> str:
    name = (step.model_name or "").lower()
    if name:
        for token in _ALGORITHM_TOKENS:
            if token in name:
                return token
        return name
    predictor = step.params.get("predictor", "")
    if predictor:
        cls = predictor.rsplit(".", 1)[-1]
        return cls.replace("Predictor", "").lower() or step.step_id
    return step.step_id


def _step_internal_config(step: StepConfig) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    if step.io_contract is not None:
        cfg["io_contract"] = step.io_contract.model_dump()
    if step.serve_endpoint:
        cfg["serve_endpoint"] = step.serve_endpoint
    if step.poll_interval_seconds:
        cfg["poll_interval_seconds"] = step.poll_interval_seconds
    if step.poll_timeout_seconds:
        cfg["poll_timeout_seconds"] = step.poll_timeout_seconds
    if step.subscribers:
        cfg["subscribers"] = [s.model_dump() for s in step.subscribers]
    if step.async_protocol is not None:
        cfg["async_protocol"] = step.async_protocol.model_dump()
    return cfg


# ─── Detection manifests (enrichment, matched by name) ──────────────────────────

def _load_detections(detections_dir: Path) -> dict[str, dict]:
    detections: dict[str, dict] = {}
    if not detections_dir.is_dir():
        return detections
    for yaml_file in detections_dir.glob("*.yaml"):
        with yaml_file.open() as f:
            data = yaml.safe_load(f)
        if isinstance(data, dict) and data.get("name"):
            detections[data["name"]] = data
    return detections


def _enrichment(detection: dict | None) -> tuple[str | None, dict, dict]:
    """Return (weights_url, config, infra_config) derived from a detection manifest.

    None of these feed the capability sha, so enrichment never breaks the join.
    """
    if not detection:
        return None, {}, {}
    model = detection.get("model") or {}
    weights_url = model.get("model_id") or None
    config: dict[str, Any] = {}
    if model:
        config["model"] = model
    if detection.get("classes"):
        config["classes"] = detection["classes"]
    if detection.get("inference"):
        config["inference"] = detection["inference"]
    infra_config: dict[str, Any] = {}
    if detection.get("serving"):
        infra_config["serving"] = detection["serving"]
    for key in ("type", "client"):
        if detection.get(key):
            infra_config[key] = detection[key]
    return weights_url, config, infra_config


# ─── HTTP: capabilities-api (upsert by sha) ─────────────────────────────────────

class CapabilitiesApi:
    def __init__(self, client: httpx.AsyncClient, base_url: str, dry_run: bool) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._dry = dry_run
        self._sha_cache: dict[str, str] = {}  # sha -> capability_id

    async def _get_id_by_sha(self, sha: str) -> str | None:
        resp = await self._client.get(f"{self._base}/internal/capabilities/by-sha/{sha}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()["id"]

    async def ensure(self, sha: str, payload: dict) -> tuple[str, str]:
        """Create the capability if absent; return (capability_id, sha)."""
        if sha in self._sha_cache:
            return self._sha_cache[sha], sha
        if self._dry:
            cap_id = f"<dry:{sha}>"
            self._sha_cache[sha] = cap_id
            return cap_id, sha
        existing = await self._get_id_by_sha(sha)
        if existing is not None:
            self._sha_cache[sha] = existing
            return existing, sha
        resp = await self._client.post(f"{self._base}/capabilities", json=payload)
        if resp.status_code == 409:
            # Lost a race or sha already present; fetch it.
            existing = await self._get_id_by_sha(sha)
            if existing is None:
                resp.raise_for_status()
            self._sha_cache[sha] = existing  # type: ignore[assignment]
            return existing, sha  # type: ignore[return-value]
        resp.raise_for_status()
        cap_id = resp.json()["id"]
        self._sha_cache[sha] = cap_id
        return cap_id, sha


# ─── HTTP: solutions-api (upsert by name) ───────────────────────────────────────

class SolutionsApi:
    def __init__(self, client: httpx.AsyncClient, base_url: str, dry_run: bool) -> None:
        self._client = client
        self._base = base_url.rstrip("/")
        self._dry = dry_run

    async def upsert(self, payload: dict) -> str:
        name = payload["name"]
        if self._dry:
            return "dry-run"
        resp = await self._client.get(f"{self._base}/internal/tool-actions/by-name/{name}")
        if resp.status_code == 200:
            tool_action_id = resp.json()["id"]
            patch = {k: v for k, v in payload.items() if k != "name"}
            up = await self._client.patch(
                f"{self._base}/tool-actions/{tool_action_id}", json=patch
            )
            up.raise_for_status()
            return "updated"
        if resp.status_code != 404:
            resp.raise_for_status()
        created = await self._client.post(f"{self._base}/tool-actions", json=payload)
        created.raise_for_status()
        return "created"


# ─── Build payloads ─────────────────────────────────────────────────────────────

def _build_step(step: StepConfig, position: int,
                detections: dict[str, dict]) -> tuple[dict, dict | None]:
    """Return (step_payload, capability_payload_or_None).

    The capability payload carries a synthetic ``_sha`` key used for the upsert
    lookup; it is stripped before POSTing.
    """
    internal_config = _step_internal_config(step)
    step_payload: dict[str, Any] = {
        "step_id": step.step_id,
        "depends_on": list(step.depends_on),
        "user_params": dict(step.params),
        "position": position,
        "internal_config": internal_config,
    }

    match step.step_type:
        case "postprocess":
            step_payload["step_type"] = "classic_algorithm"
            return step_payload, None

        case "local_capability":
            step_payload["step_type"] = "classic_algorithm"
            capability_type = _infer_capability_type(step)
            algorithm = _infer_algorithm(step)
            cap_payload = {
                "_sha": _classic_capability_sha(capability_type, algorithm),
                "kind": "classic_algorithm",
                "capability_type": capability_type,
                "algorithm": algorithm,
                "status": "active",
                "display_name": step.step_id,
                "config": dict(step.params),
            }
            return step_payload, cap_payload

        case "async_inference" | "inference":
            step_payload["step_type"] = "model"
            capability_type = _infer_capability_type(step)
            algorithm = _infer_algorithm(step)
            model_name = step.model_name
            model_version = step.model_version or "0.0.0"
            confidence = step.confidence_threshold
            weights_url, config, infra_config = _enrichment(detections.get(model_name))
            cap_payload = {
                "_sha": _model_capability_sha(
                    capability_type, algorithm, model_name, model_version, confidence
                ),
                "kind": "model",
                "capability_type": capability_type,
                "algorithm": algorithm,
                "model_name": model_name,
                "model_version": model_version,
                "confidence_threshold": confidence,
                "status": "active",
                "display_name": model_name,
                "weights_url": weights_url,
                "config": config,
                "infra_config": infra_config,
            }
            return step_payload, cap_payload

        case _:
            raise ValueError(
                f"step {step.step_id!r}: unmapped step_type {step.step_type!r}"
            )


# ─── Main ────────────────────────────────────────────────────────────────────────

async def run(args: argparse.Namespace) -> None:
    configs_dir = Path(args.configs_dir).resolve()
    detections_dir = Path(args.detections_dir).resolve()

    configs = load_all_configs(str(configs_dir))
    detections = _load_detections(detections_dir)
    print(f"loaded {len(configs)} pipeline configs, {len(detections)} detection manifests")

    async with httpx.AsyncClient(timeout=30.0) as client:
        caps_api = CapabilitiesApi(client, args.capabilities_url, args.dry_run)
        solutions_api = SolutionsApi(client, args.solutions_url, args.dry_run)

        for config_key, config in sorted(configs.items()):
            config_capability, _, solution_name = config_key.partition(":")
            step_payloads: list[dict] = []

            for position, step in enumerate(config.resolve_steps()):
                step_payload, cap_payload = _build_step(step, position, detections)
                if cap_payload is not None:
                    sha = cap_payload.pop("_sha")
                    cap_id, cap_sha = await caps_api.ensure(sha, cap_payload)
                    step_payload["capability_id"] = cap_id
                    step_payload["capability_sha"] = cap_sha
                step_payloads.append(step_payload)

            tool_action_payload = {
                "name": solution_name,
                "display_name": solution_name,
                "category": config_capability,
                "status": "active",
                "sensor_type": "camera",
                "internal_config": {
                    "pipeline_capability": config_capability,
                    "subscribers": [s.model_dump() for s in config.subscribers],
                },
                "steps": step_payloads,
            }

            if args.dry_run:
                print(f"\n=== {config_key} ===")
                print(json.dumps(tool_action_payload, indent=2, default=str))
            else:
                result = await solutions_api.upsert(tool_action_payload)
                print(f"{result}\t{config_key}\t({len(step_payloads)} steps)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate pipeline YAML configs to the Capabilities & Solutions APIs"
    )
    parser.add_argument(
        "--configs-dir",
        default=str(RESEARCH_MODELS_REPO / "pipelines" / "configs" / "detections"),
    )
    parser.add_argument(
        "--detections-dir",
        default=str(RESEARCH_MODELS_REPO / "detections"),
    )
    parser.add_argument(
        "--capabilities-url",
        default=os.environ.get("CAPABILITIES_API_URL", "http://localhost:8001"),
    )
    parser.add_argument(
        "--solutions-url",
        default=os.environ.get("SOLUTIONS_API_URL", "http://localhost:8000"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and print payloads without calling either API",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
