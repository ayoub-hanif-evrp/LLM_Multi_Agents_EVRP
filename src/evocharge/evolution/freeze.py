"""Freeze experiment contracts before an M9B evolution run."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evocharge.agents.prompt_loader import prompt_hash
from evocharge.evaluation.dev_set import development_manifest
from evocharge.operators.generated_api import API_VERSION
from evocharge.operators.primitives import catalogue_hash
from evocharge.reproducibility import hash_mapping, sha256_file, sha256_text, source_state


def _contract_hash(project_root: Path) -> str | None:
    path = project_root / "data" / "contracts" / "schneider_v1.0.json"
    if path.is_file():
        return sha256_file(path)
    return None


def _objective_hash(project_root: Path) -> str | None:
    # Prefer documented objective definition if present
    for rel in (
        "docs/objective_definition.md",
        "data/contracts/objective_definition.json",
    ):
        path = project_root / rel
        if path.is_file():
            return sha256_file(path)
    return sha256_text("lexicographic_vehicles_distance_v1")


def build_freeze_manifest(
    project_root: Path,
    *,
    config: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    prompts = {
        "coding_system.md": prompt_hash("coding_system.md"),
        "coding_task.md": prompt_hash("coding_task.md"),
    }
    ss = source_state(project_root)
    ss_payload = ss.model_dump() if hasattr(ss, "model_dump") else dict(ss)
    payload = {
        "frozen_at": datetime.now(UTC).isoformat(),
        "api_version": API_VERSION,
        "primitive_catalogue_hash": catalogue_hash(),
        "dataset_contract_hash": _contract_hash(project_root),
        "objective_definition_hash": _objective_hash(project_root),
        "development_manifest": development_manifest(project_root),
        "metamorphic_suite_id": "m9a_metamorphic_v1",
        "prompt_hashes": prompts,
        "model_configuration": {
            "model": model,
            "sequential_requests": True,
            "model_limitation_note": (
                "qwen3:4b acceptable for first controlled M9B run; "
                "not claimed as primary publishable coding model."
            ),
        },
        "evaluation_budgets": dict(config.get("evaluation") or {}),
        "population_budgets": dict(config.get("population") or {}),
        "source_state": ss_payload,
        "mutation_allowed_during_run": False,
        "schneider_transfer": False,
        "hidden_test_evaluation": False,
    }
    payload["freeze_hash"] = hash_mapping(
        {k: v for k, v in payload.items() if k != "freeze_hash"}
    )
    return payload


def write_freeze_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
