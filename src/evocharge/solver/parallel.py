"""Parallel multi-instance evaluation with deterministic per-worker seeds."""

from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from evocharge.solver.alns import ALNSConfig
from evocharge.solver.memory import recommend_workers


def _worker(payload: dict[str, Any]) -> dict[str, Any]:
    # Import inside worker for Windows spawn safety
    from evocharge.data.schneider_parser import parse_schneider_file
    from evocharge.solver.alns import ALNSConfig, run_alns

    cfg = ALNSConfig(**payload["config"])
    cfg.seed = int(payload["seed"])
    inst = parse_schneider_file(payload["instance_path"])
    result = run_alns(
        inst,
        config=cfg,
        run_dir=Path(payload["run_dir"]),
        run_id=payload["run_id"],
        instance_path=payload["instance_path"],
        contract_path=Path(payload["contract_path"]) if payload.get("contract_path") else None,
    )
    return {
        "run_id": result.run_id,
        "instance_id": inst.instance_id,
        "feasible": result.feasible,
        "elapsed_seconds": result.elapsed_seconds,
        "objective": result.objective.model_dump(),
        "cache_hits": result.cache_hits,
        "cache_misses": result.cache_misses,
        "peak_rss_mb": result.peak_rss_mb,
        "profile": result.profile,
        "seed": result.seed,
    }


def run_instances_parallel(
    instance_paths: list[Path],
    *,
    base_config: ALNSConfig,
    artifacts_root: Path,
    base_seed: int,
    max_workers: int | None = None,
    contract_path: Path | None = None,
) -> list[dict[str, Any]]:
    workers = recommend_workers(max_workers or base_config.max_workers)
    jobs = []
    for i, path in enumerate(instance_paths):
        run_id = f"parallel_{path.stem}_s{base_seed + i}"
        jobs.append(
            {
                "instance_path": str(path),
                "config": asdict(base_config),
                "seed": base_seed + i,
                "run_dir": str(artifacts_root / run_id),
                "run_id": run_id,
                "contract_path": str(contract_path) if contract_path else None,
            }
        )

    results: list[dict[str, Any]] = []
    if workers == 1 or len(jobs) == 1:
        for job in jobs:
            results.append(_worker(job))
        return results

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_worker, job): job for job in jobs}
        for fut in as_completed(futures):
            results.append(fut.result())
    results.sort(key=lambda r: r["run_id"])
    return results


def write_batch_summary(path: Path, results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    feasible = [r for r in results if r.get("feasible")]
    runtimes = [float(r["elapsed_seconds"]) for r in results]
    runtimes_sorted = sorted(runtimes)
    median = runtimes_sorted[len(runtimes_sorted) // 2] if runtimes_sorted else 0.0
    summary = {
        "n_instances": len(results),
        "feasible_count": len(feasible),
        "feasible_rate": (len(feasible) / len(results)) if results else 0.0,
        "median_runtime_seconds": median,
        "max_runtime_seconds": max(runtimes) if runtimes else 0.0,
        "results": results,
        "ollama_calls": 0,
    }
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
