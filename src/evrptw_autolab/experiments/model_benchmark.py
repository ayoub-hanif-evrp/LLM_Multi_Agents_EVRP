"""Homogeneous five-agent × N-model comparison. Does not vary team size."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from evrptw_autolab.evaluation.fidelity import by_customer_count, load_all, split_instances
from evrptw_autolab.experiments.reports import write_model_table
from evrptw_autolab.llm.registry import (
    SKIPPED_NOT_INSTALLED,
    availability,
    make_backend,
    resolve_profile,
)
from evrptw_autolab.problem.private import smoke_instance
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver

ROOT = Path(__file__).resolve().parents[3]


def benchmark_models(
    *,
    model_ids: list[str],
    workspace: Path,
    data_root: Path | None = None,
    backend_factory: Any | None = None,
) -> list[dict[str, Any]]:
    instances = split_instances(load_all(data_root))["discovery"]
    smoke = by_customer_count(instances, [5])
    if not smoke:
        raise RuntimeError("no 5-customer discovery instances")
    rows: list[dict[str, Any]] = []
    for model_id in model_ids:
        profile = resolve_profile(model_id)
        status = availability(profile)
        row: dict[str, Any] = {
            "model_id": model_id,
            "model": profile.model,
            "team_mode": "five_agent",
            "status": status,
        }
        if status != "installed" and backend_factory is None:
            print(f"{SKIPPED_NOT_INSTALLED if status == SKIPPED_NOT_INSTALLED else status}: {profile.model}")
            rows.append(row)
            continue
        backend = backend_factory(profile) if backend_factory else make_backend(profile)
        result = bootstrap_solver(
            workspace / model_id,
            backend,
            model=profile.model,
            instance=smoke_instance(1),
            temperatures=profile.temperatures,
            discovery=instances,
        )
        row.update(
            {
                "status": "ran",
                "solver_id": result["solver_id"],
                "feasible": result["evaluation"]["feasible"],
                "vehicles": result["evaluation"]["vehicles"],
                "distance": result["evaluation"]["distance"],
                "activated": result["activated"],
            }
        )
        rows.append(row)
    write_model_table(rows, ROOT / "results" / "model_comparison" / "summary.json")
    return rows
