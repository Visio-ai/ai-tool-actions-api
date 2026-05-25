from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

import yaml

# When running outside visio-research-models monorepo, set RESEARCH_MODELS_REPO
# to the local path of that repo so pipeline config loader can be found.
_research_models = os.environ.get("RESEARCH_MODELS_REPO")
if not _research_models:
    raise RuntimeError("RESEARCH_MODELS_REPO env var required (path to visio-research-models clone)")
PIPELINE_CORE_SRC = Path(_research_models) / "pipelines" / "_core" / "src"
if str(PIPELINE_CORE_SRC) not in sys.path:
    sys.path.insert(0, str(PIPELINE_CORE_SRC))

from pipeline.configs.loader import load_all_configs  # noqa: E402

from capabilities_solutions_api.app.use_cases.catalog_service import CatalogService  # noqa: E402
from capabilities_solutions_api.domain.models import (  # noqa: E402
    ClassicAlgorithmCapabilityDraft,
    ModelCapabilityDraft,
    SolutionDraft,
    SolutionStepDraft,
)
from capabilities_solutions_api.main.db import apply_schema, create_pool  # noqa: E402
from capabilities_solutions_api.main.settings import Settings  # noqa: E402
from capabilities_solutions_api.adapters.repositories.postgres import (  # noqa: E402
    PostgresCatalogRepository,
)


def _infer_algorithm(step) -> str:
    if step.model_name:
        lowered = step.model_name.lower()
        for candidate in ("rf-detr", "rt-detr-v2", "yolos", "dfine", "owlv2", "bytetrack", "csrt", "sam2"):
            if candidate in lowered:
                return candidate
        return lowered
    predictor = step.params.get("predictor", "")
    if predictor:
        return predictor.rsplit(".", 1)[-1].replace("Predictor", "").lower()
    return step.step_id


def _infer_capability_type(config_capability: str, step) -> str:
    if config_capability and config_capability != "pipeline":
        return config_capability
    model_name = (step.model_name or "").lower()
    if model_name.startswith("od-"):
        return "object_detection"
    if model_name.startswith("ot-"):
        return "object_tracking"
    if step.step_type == "local_capability":
        return "zone_analytics"
    return "pipeline"


def _io_contract(step) -> dict[str, Any]:
    return step.io_contract.model_dump() if step.io_contract is not None else {}


def _subscribers(step) -> list[dict[str, Any]]:
    return [subscriber.model_dump() for subscriber in step.subscribers]


def _legacy_aliases(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with path.open() as file:
        data = yaml.safe_load(file) or {}
    aliases: dict[str, list[str]] = {}
    for alias, payload in (data.get("solutions") or {}).items():
        solution_id = payload.get("solution_id")
        if not solution_id:
            continue
        aliases.setdefault(solution_id, []).append(alias)
    return aliases


async def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate pipeline YAML configs to Capabilities & Solutions API")
    parser.add_argument(
        "--configs-dir",
        default=str(REPO_ROOT / "pipelines" / "configs" / "detections"),
    )
    parser.add_argument(
        "--solutions-file",
        default=str(REPO_ROOT / "pipelines" / "configs" / "solutions.yaml"),
    )
    parser.add_argument(
        "--apply-schema",
        action="store_true",
        help="Apply database/schema.sql before migrating",
    )
    args = parser.parse_args()

    settings = Settings()
    pool = await create_pool(settings.database_dsn)
    try:
        if args.apply_schema:
            await apply_schema(pool)
        service = CatalogService(PostgresCatalogRepository(pool))
        configs = load_all_configs(args.configs_dir)
        aliases_by_solution = _legacy_aliases(Path(args.solutions_file))

        for config_key, config in sorted(configs.items()):
            config_capability, _, solution_name = config_key.partition(":")
            top_level_internal = {
                "pipeline_capability": config_capability,
                "subscribers": [subscriber.model_dump() for subscriber in config.subscribers],
                "legacy_aliases": aliases_by_solution.get(solution_name, []),
            }
            solution_draft = SolutionDraft(
                name=solution_name,
                description=f"Migrated from {config_key}",
                user_params={},
                internal_config=top_level_internal,
            )

            step_drafts: list[SolutionStepDraft] = []
            for index, step in enumerate(config.resolve_steps()):
                capability_id = None
                internal_config = {
                    "io_contract": _io_contract(step),
                }
                if step.serve_endpoint:
                    internal_config["serve_endpoint"] = step.serve_endpoint
                if step.poll_interval_seconds:
                    internal_config["poll_interval_seconds"] = step.poll_interval_seconds
                if step.poll_timeout_seconds:
                    internal_config["poll_timeout_seconds"] = step.poll_timeout_seconds
                if _subscribers(step):
                    internal_config["subscribers"] = _subscribers(step)

                if step.step_type == "postprocess":
                    pass
                elif step.step_type == "local_capability":
                    capability = await service.ensure_capability(
                        ClassicAlgorithmCapabilityDraft(
                            capability_type=_infer_capability_type(config_capability, step),
                            algorithm=_infer_algorithm(step),
                            user_params=dict(step.params),
                            internal_config=internal_config,
                        )
                    )
                    capability_id = capability.id
                    internal_config = {}
                else:
                    capability = await service.ensure_capability(
                        ModelCapabilityDraft(
                            capability_type=_infer_capability_type(config_capability, step),
                            algorithm=_infer_algorithm(step),
                            model_name=step.model_name or step.step_id,
                            model_version=step.model_version or "0.0.0",
                            confidence_threshold=step.confidence_threshold,
                            user_params=dict(step.params),
                            internal_config=internal_config,
                        )
                    )
                    capability_id = capability.id
                    internal_config = {}

                step_drafts.append(
                    SolutionStepDraft(
                        step_id=step.step_id,
                        step_type=step.step_type,
                        capability_id=capability_id,
                        position=index,
                        depends_on=list(step.depends_on),
                        user_params=dict(step.params),
                        internal_config=internal_config,
                    )
                )

            existing = await service.repository.get_solution_by_name_or_alias(solution_name)
            if existing is None:
                await service.create_solution(solution_draft, step_drafts)
                print(f"created\t{config_key}")
            else:
                await service.update_solution(
                    existing.id,
                    description=solution_draft.description,
                    user_params=solution_draft.user_params,
                    steps=step_drafts,
                )
                print(f"updated\t{config_key}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
