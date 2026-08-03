"""ChargeCEGIS experiment CLI: correctness smoke check, pilot run, and full-dataset run.

Three commands, by design (see project spec section 16, "minimal codebase"):

    python -m chargecegis.experiment validate-core
    python -m chargecegis.experiment run-pilot --config configs/experiments.yaml
    python -m chargecegis.experiment run-full-dataset --config configs/experiments.yaml

``validate-core`` never writes results; it is the pre-flight equal-budget gate that must pass
before any pilot or full-dataset campaign starts: it certifies that every equal-budget ranking
method (see :mod:`chargecegis.alns` ``EQUAL_BUDGET_METHODS``) shares the same merged initial
solution, the same candidate pool (and hash) at iteration 0, and evaluates the same number of
pooled candidates -- only the ranking function may differ.

``run-pilot`` and ``run-full-dataset`` are both restartable, keyed by
``(experiment_version, source_hash, config_hash, method, instance_id, seed)``: every completed run
is written atomically as ``results/raw/runs/{key}.json`` (and, for equal-budget methods,
``results/raw/invocations/{key}.jsonl``); the aggregated CSVs consumed by
:mod:`chargecegis.statistics` / :mod:`chargecegis.plots` are then rebuilt from scratch from those
per-run artifacts, so the aggregate can never accumulate stale or double-counted rows across
restarts, and a run is only included once its recorded ``policy_calls`` matches the number of
invocation rows actually written for it.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import time
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
import yaml

from chargecegis.alns import (
    EQUAL_BUDGET_METHODS,
    ALNSConfig,
    ALNSResult,
    remove_empty_routes,
    run_alns,
    solution_hash,
)
from chargecegis.construction import (
    ChargingReconstructionConfig,
    construct_initial_solution,
    construct_merged_initial_solution,
    insert_customers_best_fit,
)
from chargecegis.data import discover_instances, load_instance
from chargecegis.features import FEATURE_NAMES, FeatureNormalizer, compute_features_for_solutions
from chargecegis.moves import enumerate_removal_units, sample_candidate_pool
from chargecegis.problem import Instance, Route, Solution
from chargecegis.propagation import arc_metrics

app = typer.Typer(no_args_is_help=True)

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = Path(__file__).resolve().parent
CONFIGS_DIR = ROOT / "configs"
DEFAULT_EXPERIMENTS_CONFIG = CONFIGS_DIR / "experiments.yaml"
SOLVER_CONFIG_PATH = CONFIGS_DIR / "solver.yaml"
MODELS_CONFIG_PATH = CONFIGS_DIR / "models.yaml"

RESULTS_DIR = ROOT / "results"
RAW_DIR = RESULTS_DIR / "raw"
RUNS_DIR = RAW_DIR / "runs"
INVOCATIONS_DIR = RAW_DIR / "invocations"
TABLES_DIR = RESULTS_DIR / "tables"
FIGURES_DIR = RESULTS_DIR / "figures"
MANIFESTS_DIR = RESULTS_DIR / "manifests"

AGGREGATED_RUNS_CSV = RAW_DIR / "full_dataset_runs.csv"
AGGREGATED_INVOCATIONS_CSV = RAW_DIR / "move_invocations.csv"

DEFAULT_STATUS = "PRELIMINARY_DETERMINISTIC_VALIDATION"

RUN_FIELDS = [
    "run_key", "experiment_version", "method", "method_kind", "instance_id", "family", "scale",
    "seed", "feasible", "vehicles", "distance", "station_count", "charging_distance",
    "charging_time", "runtime_seconds", "time_to_best", "iterations_completed", "policy_calls",
    "effective_moves", "accepted_moves", "new_best_moves", "initial_solution_hash",
    "final_solution_hash", "config_hash", "source_hash",
]

MOVE_INVOCATION_FIELDS = [
    "run_key", "experiment_version", "method", "instance_id", "seed",
    "iteration", "policy_id", "move_type", "candidate_count", "selected_move_hash",
    "policy_score", "feasible", "vehicles_before", "vehicles_after", "distance_before",
    "distance_after", "station_count_before", "station_count_after",
    "customer_sequence_changed", "station_sequence_changed", "accepted", "new_best",
    "runtime_ms", "candidate_pool_hash", "selected_unit_hashes",
]


def ensure_results_tree() -> None:
    for directory in (RAW_DIR, RUNS_DIR, INVOCATIONS_DIR, TABLES_DIR, FIGURES_DIR, MANIFESTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    readme = RESULTS_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# ChargeCEGIS results\n\nSee the project root README for details. "
            "This placeholder is created automatically by `chargecegis.experiment`.\n",
            encoding="utf-8",
        )


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def compute_source_hash(src_root: Path = SRC_ROOT) -> str:
    """SHA-256 over every ``*.py`` file under ``src/chargecegis``, ordered by filename."""
    hasher = hashlib.sha256()
    for path in sorted(src_root.glob("*.py")):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _build_charging_config(solver_config: dict[str, Any]) -> ChargingReconstructionConfig:
    charging_cfg = solver_config.get("charging_reconstruction", {})
    return ChargingReconstructionConfig(
        max_station_candidates_per_gap=charging_cfg.get("max_station_candidates_per_gap", 5),
        max_inserted_stations_per_route=charging_cfg.get("max_inserted_stations_per_route", 3),
        max_repair_attempts_per_move=charging_cfg.get("max_repair_attempts_per_move", 30),
        beam_width=charging_cfg.get("beam_width", 8),
        max_expansions=charging_cfg.get("max_expansions", 80),
    )


def records_invocations(method: str) -> bool:
    """Whether ``method`` uses the per-iteration invocation log (every equal-budget ranking
    method; ``CLASSIC_ALNS_REFERENCE`` deliberately does not, see :mod:`chargecegis.alns`)."""
    return EQUAL_BUDGET_METHODS[method].get("destroy_mode") == "equal_budget"


def method_kind(method: str) -> str:
    return "equal_budget" if records_invocations(method) else "classic"


def build_run_config(
    method: str,
    *,
    seed: int,
    max_iterations: int,
    solver_config: dict[str, Any],
    validation_config: dict[str, Any],
    normalizer: FeatureNormalizer | None,
) -> ALNSConfig:
    if method not in EQUAL_BUDGET_METHODS:
        raise typer.BadParameter(f"unknown method: {method!r}")
    spec = EQUAL_BUDGET_METHODS[method]
    alns_cfg = solver_config.get("alns", {})
    policy_search_cfg = solver_config.get("policy_search", {})
    default_pool = policy_search_cfg.get("candidate_pool", {})
    pool_cfg = validation_config.get("candidate_pool", default_pool)
    charging = _build_charging_config(solver_config)
    is_equal_budget = spec.get("destroy_mode") == "equal_budget"
    return ALNSConfig(
        seed=seed,
        max_iterations=max_iterations,
        destroy_fraction=alns_cfg.get("destroy_fraction", 0.25),
        initial_temperature=alns_cfg.get("initial_temperature", 5.0),
        cooling_rate=alns_cfg.get("cooling_rate", 0.995),
        destroy_mode=spec.get("destroy_mode", "random"),
        move_selection_mode=spec.get("move_selection_mode", "random"),
        ranking_mode=spec.get("ranking_mode", "random"),
        handcrafted_name=spec.get("handcrafted_name", "combined"),
        charging=charging,
        normalizer=normalizer if is_equal_budget else None,
        policy_id=method,
        removal_units_per_iteration=validation_config.get(
            "removal_units_per_iteration", policy_search_cfg.get("removal_units_per_iteration", 5)
        ),
        max_segment_length=validation_config.get(
            "max_segment_length", policy_search_cfg.get("max_segment_length", 3)
        ),
        candidate_pool_max_per_route=pool_cfg.get("max_per_route", 5),
        candidate_pool_max_total=pool_cfg.get("max_total", 100),
        use_merged_initial=policy_search_cfg.get("use_merged_initial", True),
    )


def config_hash(method: str, config: ALNSConfig) -> str:
    payload = {
        "method": method,
        "destroy_mode": config.destroy_mode,
        "move_selection_mode": config.move_selection_mode,
        "ranking_mode": config.ranking_mode,
        "handcrafted_name": config.handcrafted_name,
        "max_iterations": config.max_iterations,
        "destroy_fraction": config.destroy_fraction,
        "initial_temperature": config.initial_temperature,
        "cooling_rate": config.cooling_rate,
        "max_moves_per_type": config.max_moves_per_type,
        "removal_units_per_iteration": config.removal_units_per_iteration,
        "max_segment_length": config.max_segment_length,
        "candidate_pool_max_per_route": config.candidate_pool_max_per_route,
        "candidate_pool_max_total": config.candidate_pool_max_total,
        "use_merged_initial": config.use_merged_initial,
        "charging": asdict(config.charging),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def run_key(
    experiment_version: str, source_hash_value: str, config_hash_value: str,
    method: str, instance_id: str, seed: int,
) -> str:
    """Stable identity for one ``(experiment_version, source_hash, config_hash, method,
    instance_id, seed)`` run: doubles as the restart key and the per-run artifact filename stem.
    A source or config change yields a different key automatically (never a silent overwrite of
    results produced under different code/config)."""
    payload = {
        "experiment_version": experiment_version,
        "source_hash": source_hash_value,
        "config_hash": config_hash_value,
        "method": method,
        "instance_id": instance_id,
        "seed": seed,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def station_metrics(instance: Instance, solution: Solution) -> tuple[float, float, int]:
    """Total charging detour distance, total charging duration, and station-visit count."""
    detour = charge_time = 0.0
    count = 0
    for route in solution.routes:
        for i, stop in enumerate(route.schedule):
            if stop.node_id not in instance.station_ids:
                continue
            count += 1
            charge_time += stop.charging_duration
            if 0 < i < len(route.node_ids) - 1:
                p, s, q = route.node_ids[i - 1:i + 2]
                detour += (
                    arc_metrics(instance, p, s).distance
                    + arc_metrics(instance, s, q).distance
                    - arc_metrics(instance, p, q).distance
                )
    return detour, charge_time, count


def _select_family_representatives(instances: list[Instance]) -> dict[str, Instance]:
    """One small instance per Schneider family (deterministic: lowest instance id wins)."""
    reps: dict[str, Instance] = {}
    for instance in sorted(instances, key=lambda inst: inst.instance_id):
        family = instance.metadata.get("family", "")
        if family and family not in reps:
            reps[family] = instance
    return reps


def _strip_customers_local(solution: Solution, customer_ids: Sequence[str]) -> Solution:
    removed = set(customer_ids)
    routes = tuple(
        Route(r.vehicle_index, tuple(n for n in r.node_ids if n not in removed)) for r in solution.routes
    )
    return Solution(routes, solution.metadata)


def fit_normalization_balanced(
    representatives: dict[str, Instance],
    *,
    charging: ChargingReconstructionConfig,
    seed: int = 0,
    samples_per_family: int = 5,
) -> FeatureNormalizer:
    """Fit on a small, family-balanced sample: one small instance per Schneider family, using
    the merged initial solution plus a handful of equal-budget destroy/repair states (see
    :func:`chargecegis.construction.construct_merged_initial_solution` and
    :func:`chargecegis.moves.enumerate_removal_units`)."""
    vectors: list[dict[str, float]] = []
    families: list[str] = []
    for family, instance in sorted(representatives.items()):
        construction = construct_merged_initial_solution(instance, seed=seed, config=charging)
        if not construction.feasible:
            continue
        solution = construction.solution
        units = enumerate_removal_units(instance, solution, max_segment_length=3)
        pool = sample_candidate_pool(
            units, rng=random.Random(seed), max_per_route=5, max_total=max(samples_per_family * 4, 1)
        )
        for unit in pool[:samples_per_family]:
            destroyed = remove_empty_routes(_strip_customers_local(solution, unit.customer_ids), instance)
            repaired = insert_customers_best_fit(
                instance, destroyed, unit.customer_ids, config=charging, rng=random.Random(seed)
            )
            repaired = remove_empty_routes(repaired, instance)
            try:
                feats = compute_features_for_solutions(instance, solution, repaired, unit)
            except ValueError:
                continue
            vectors.append(feats)
            families.append(family)
    if not vectors:
        vectors, families = [{name: 0.0 for name in FEATURE_NAMES}], ["none"]
    return FeatureNormalizer().fit_balanced(vectors, families)


def run_single_experiment(
    instance: Instance,
    method: str,
    seed: int,
    *,
    experiment_version: str,
    max_iterations: int,
    solver_config: dict[str, Any],
    validation_config: dict[str, Any],
    normalizer: FeatureNormalizer | None,
    source_hash_value: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = build_run_config(
        method, seed=seed, max_iterations=max_iterations, solver_config=solver_config,
        validation_config=validation_config, normalizer=normalizer,
    )
    result: ALNSResult = run_alns(instance, config=config)
    detour, charge_time, stations = station_metrics(instance, result.solution)
    c_hash = config_hash(method, config)
    key = run_key(experiment_version, source_hash_value, c_hash, method, instance.instance_id, seed)
    logs_invocations = records_invocations(method)
    row = {
        "run_key": key,
        "experiment_version": experiment_version,
        "method": method,
        "method_kind": method_kind(method),
        "instance_id": instance.instance_id,
        "family": instance.metadata.get("family", ""),
        "scale": instance.metadata.get("scale", ""),
        "seed": seed,
        "feasible": result.feasible,
        "vehicles": result.objective.vehicles_used,
        "distance": result.objective.total_distance,
        "station_count": stations,
        "charging_distance": detour,
        "charging_time": charge_time,
        "runtime_seconds": result.runtime_seconds,
        "time_to_best": result.time_to_best,
        "iterations_completed": result.iterations,
        "policy_calls": result.policy_calls,
        "effective_moves": result.effective_moves,
        "accepted_moves": result.accepted_moves,
        "new_best_moves": result.new_best_moves,
        "initial_solution_hash": result.initial_solution_hash,
        "final_solution_hash": result.final_solution_hash,
        "config_hash": c_hash,
        "source_hash": source_hash_value,
        "records_invocations": logs_invocations,
    }
    move_rows: list[dict[str, Any]] = []
    if logs_invocations:
        for invocation in result.invocations:
            move_rows.append({
                "run_key": key,
                "experiment_version": experiment_version,
                "method": method,
                "instance_id": instance.instance_id,
                "seed": seed,
                **invocation.as_dict(),
            })
    return row, move_rows


def write_run_artifacts(key: str, row: dict[str, Any], move_rows: list[dict[str, Any]]) -> None:
    """Atomic per-run persistence: one JSON fragment plus (for equal-budget methods) one JSONL
    invocation fragment, written under a filename derived from the run's own identity key."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{key}.json").write_text(
        json.dumps(row, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    invocation_path = INVOCATIONS_DIR / f"{key}.jsonl"
    if move_rows:
        INVOCATIONS_DIR.mkdir(parents=True, exist_ok=True)
        with invocation_path.open("w", encoding="utf-8") as handle:
            for move_row in move_rows:
                handle.write(json.dumps(move_row, sort_keys=True, default=str) + "\n")
    elif invocation_path.exists():
        invocation_path.unlink()


def completed_keys() -> set[str]:
    if not RUNS_DIR.exists():
        return set()
    return {p.stem for p in RUNS_DIR.glob("*.json")}


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def rebuild_aggregates() -> tuple[int, int]:
    """Rebuild ``results/raw/full_dataset_runs.csv`` and ``move_invocations.csv`` from every
    validated per-run artifact under ``results/raw/runs`` / ``results/raw/invocations``.

    A run is included only if, for equal-budget methods, its recorded ``policy_calls`` equals the
    number of invocation rows actually written for it; classic (non-equal-budget) runs are never
    expected to carry invocation rows. Rebuilding from scratch on every call (rather than ever
    appending) is what keeps the aggregate free of stale or double-counted rows across restarts.
    """
    run_rows: list[dict[str, Any]] = []
    move_rows: list[dict[str, Any]] = []
    dropped = 0
    if RUNS_DIR.exists():
        for run_path in sorted(RUNS_DIR.glob("*.json")):
            row = json.loads(run_path.read_text(encoding="utf-8"))
            key = row.get("run_key", run_path.stem)
            invocation_path = INVOCATIONS_DIR / f"{key}.jsonl"
            rows: list[dict[str, Any]] = []
            if invocation_path.exists():
                for line in invocation_path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        rows.append(json.loads(line))
            expects_invocations = bool(row.get("records_invocations", False))
            if expects_invocations and int(row.get("policy_calls", 0)) != len(rows):
                dropped += 1
                continue
            if not expects_invocations and rows:
                dropped += 1
                continue
            run_rows.append(row)
            move_rows.extend(rows)
    _write_csv(AGGREGATED_RUNS_CSV, RUN_FIELDS, run_rows)
    _write_csv(AGGREGATED_INVOCATIONS_CSV, MOVE_INVOCATION_FIELDS, move_rows)
    return len(run_rows), dropped


def write_manifests(
    *,
    all_instances: list[Instance],
    dev_instances: list[Instance],
    normalizer: FeatureNormalizer,
    source_hash_value: str,
    experiment_config: dict[str, Any],
) -> None:
    MANIFESTS_DIR.mkdir(parents=True, exist_ok=True)
    (MANIFESTS_DIR / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "count": len(all_instances),
                "instances": [
                    {
                        "instance_id": inst.instance_id,
                        "family": inst.metadata.get("family"),
                        "scale": inst.metadata.get("scale"),
                        "num_customers": len(inst.customer_ids),
                        "num_stations": len(inst.station_ids),
                    }
                    for inst in all_instances
                ],
            },
            indent=2, sort_keys=True,
        ),
        encoding="utf-8",
    )
    (MANIFESTS_DIR / "source_hash.json").write_text(
        json.dumps({"source_hash": source_hash_value, "files": sorted(p.name for p in SRC_ROOT.glob("*.py"))},
                   indent=2, sort_keys=True),
        encoding="utf-8",
    )
    normalizer.save(MANIFESTS_DIR / "feature_normalization.json")
    model_config = load_yaml(MODELS_CONFIG_PATH) if MODELS_CONFIG_PATH.exists() else {}
    (MANIFESTS_DIR / "model_manifest.json").write_text(
        json.dumps(model_config, indent=2, sort_keys=True), encoding="utf-8",
    )
    (MANIFESTS_DIR / "experiment_config.json").write_text(
        json.dumps(
            {
                **experiment_config,
                "dev_instance_ids": [inst.instance_id for inst in dev_instances],
            },
            indent=2, sort_keys=True, default=str,
        ),
        encoding="utf-8",
    )


def _load_all_instances(data_root: Path) -> list[Instance]:
    return [load_instance(p) for p in discover_instances(data_root)]


def _run_campaign(
    *,
    instances: list[Instance],
    methods: list[str],
    seeds: list[int],
    experiment_version: str,
    max_iterations: int,
    solver_config: dict[str, Any],
    validation_config: dict[str, Any],
    normalizer: FeatureNormalizer,
    source_hash_value: str,
) -> tuple[int, int]:
    """Run every ``(instance, method, seed)`` combination, skipping any already-completed key."""
    completed = completed_keys()
    executed = skipped = 0
    for instance in sorted(instances, key=lambda inst: inst.instance_id):
        for method in methods:
            for seed in seeds:
                config = build_run_config(
                    method, seed=seed, max_iterations=max_iterations, solver_config=solver_config,
                    validation_config=validation_config, normalizer=normalizer,
                )
                c_hash = config_hash(method, config)
                key = run_key(experiment_version, source_hash_value, c_hash, method, instance.instance_id, seed)
                if key in completed:
                    skipped += 1
                    continue
                row, move_rows = run_single_experiment(
                    instance, method, seed, experiment_version=experiment_version,
                    max_iterations=max_iterations, solver_config=solver_config,
                    validation_config=validation_config, normalizer=normalizer,
                    source_hash_value=source_hash_value,
                )
                write_run_artifacts(key, row, move_rows)
                completed.add(key)
                executed += 1
    return executed, skipped


def _methods_from_config(validation_config: dict[str, Any], *, include_classic: bool) -> list[str]:
    equal_budget_methods = list(validation_config.get("equal_budget_methods", list(EQUAL_BUDGET_METHODS)[:-1]))
    classic_method = str(validation_config.get("classic_reference", "CLASSIC_ALNS_REFERENCE"))
    methods = list(equal_budget_methods)
    if include_classic:
        methods.append(classic_method)
    for method in methods:
        if method not in EQUAL_BUDGET_METHODS:
            raise typer.BadParameter(f"unknown method in validation config: {method!r}")
    return methods


@app.command("validate-core")
def validate_core() -> None:
    """Fast deterministic smoke check: dataset discovery, construction, and the equal-budget
    ranking-method contract (shared initial solution, shared candidate pool, shared pool size).

    Must complete in a few seconds and print ``OK``. This is the pre-flight gate for
    ``run-pilot`` / ``run-full-dataset``; it writes no files under ``results/``.
    """
    paths = discover_instances()
    if len(paths) != 92:
        typer.echo(f"FAIL: expected 92 Schneider instances, found {len(paths)}")
        raise typer.Exit(code=1)

    instance_path = next((p for p in paths if p.stem == "c101C5"), None)
    if instance_path is None:
        typer.echo("FAIL: c101C5 instance not found")
        raise typer.Exit(code=1)
    instance = load_instance(instance_path)

    dedicated = construct_initial_solution(instance)
    if not dedicated.feasible:
        typer.echo("FAIL: dedicated-route construction is not feasible for c101C5")
        raise typer.Exit(code=1)

    merged_a = construct_merged_initial_solution(instance, seed=0)
    merged_b = construct_merged_initial_solution(instance, seed=0)
    if not merged_a.feasible or solution_hash(merged_a.solution) != solution_hash(merged_b.solution):
        typer.echo("FAIL: merged initial construction is not deterministic for a fixed seed")
        raise typer.Exit(code=1)

    noop_result = run_alns(
        instance,
        config=ALNSConfig(seed=0, max_iterations=3, destroy_mode="noop", move_selection_mode="noop"),
        initial=merged_a.solution,
    )
    if not noop_result.feasible:
        typer.echo("FAIL: no-op ALNS control produced an infeasible solution")
        raise typer.Exit(code=1)

    solver_config = load_yaml(SOLVER_CONFIG_PATH) if SOLVER_CONFIG_PATH.exists() else {}
    experiments_config = load_yaml(DEFAULT_EXPERIMENTS_CONFIG) if DEFAULT_EXPERIMENTS_CONFIG.exists() else {}
    validation_config = experiments_config.get("validation", {})
    equal_budget_methods = _methods_from_config(validation_config, include_classic=False)
    normalizer = FeatureNormalizer().fit([{name: 0.0 for name in FEATURE_NAMES}])

    initial_hashes: set[str] = set()
    pool_hashes: set[str] = set()
    candidate_counts: set[int] = set()
    removal_units_per_iteration: set[int] = set()
    for method in equal_budget_methods:
        config = build_run_config(
            method, seed=0, max_iterations=1, solver_config=solver_config,
            validation_config=validation_config, normalizer=normalizer,
        )
        result = run_alns(instance, config=config, initial=merged_a.solution)
        if not result.invocations:
            typer.echo(f"FAIL: {method} recorded no invocations at iteration 0")
            raise typer.Exit(code=1)
        initial_hashes.add(result.initial_solution_hash)
        pool_hashes.add(result.invocations[0].candidate_pool_hash)
        candidate_counts.add(result.invocations[0].candidate_count)
        removal_units_per_iteration.add(config.removal_units_per_iteration)

    if len(initial_hashes) != 1:
        typer.echo("FAIL: equal-budget methods do not share the same initial solution hash")
        raise typer.Exit(code=1)
    if len(pool_hashes) != 1:
        typer.echo("FAIL: equal-budget methods do not share the same candidate-pool hash at iteration 0")
        raise typer.Exit(code=1)
    if len(candidate_counts) != 1:
        typer.echo("FAIL: equal-budget methods evaluated a different number of pooled candidates")
        raise typer.Exit(code=1)
    if len(removal_units_per_iteration) != 1:
        typer.echo("FAIL: equal-budget methods do not share the same removal-unit budget k")
        raise typer.Exit(code=1)

    classic_method = str(validation_config.get("classic_reference", "CLASSIC_ALNS_REFERENCE"))
    classic_config = build_run_config(
        classic_method, seed=0, max_iterations=3, solver_config=solver_config,
        validation_config=validation_config, normalizer=None,
    )
    classic_result = run_alns(instance, config=classic_config, initial=merged_a.solution)
    if not classic_result.feasible:
        typer.echo(f"FAIL: {classic_method} produced an infeasible solution")
        raise typer.Exit(code=1)
    if classic_result.invocations:
        typer.echo(f"FAIL: {classic_method} must not record equal-budget invocations")
        raise typer.Exit(code=1)

    typer.echo("OK")


@app.command("run-pilot")
def run_pilot(
    config: Path = typer.Option(DEFAULT_EXPERIMENTS_CONFIG, "--config", help="Path to experiments.yaml"),
    include_classic: bool = typer.Option(
        True, "--include-classic/--no-include-classic",
        help="Also run the classic (non-equal-budget) reference, reported separately.",
    ),
    max_iterations: int | None = typer.Option(
        None, "--max-iterations",
        help="Override validation.max_iterations for a faster/slower pilot.",
    ),
) -> None:
    """Pilot campaign: ``validation.pilot_instances`` x equal-budget ranking methods x
    ``validation.seeds`` (plus, by default, the classic reference on the same grid).

    Restartable via the same ``(experiment_version, source_hash, config_hash, method,
    instance_id, seed)`` key as ``run-full-dataset``, so a later full-dataset run naturally
    skips every pilot combination it already covers.
    """
    ensure_results_tree()
    experiments_config = load_yaml(config)
    solver_config = load_yaml(SOLVER_CONFIG_PATH) if SOLVER_CONFIG_PATH.exists() else {}
    validation_config = experiments_config.get("validation", {})
    experiment_version = str(validation_config.get("status", DEFAULT_STATUS))

    seeds: list[int] = list(validation_config.get("seeds", [0, 1, 2]))
    configured_max = int(validation_config.get("max_iterations", 20))
    max_iterations = int(max_iterations) if max_iterations is not None else configured_max
    pilot_ids: list[str] = list(validation_config.get("pilot_instances", []))
    methods = _methods_from_config(validation_config, include_classic=include_classic)

    data_root = ROOT / experiments_config.get("data_root", "dataset/schneider/raw_instances")
    all_instances = _load_all_instances(data_root)
    pilot_instances = [inst for inst in all_instances if inst.instance_id in pilot_ids]
    missing = set(pilot_ids) - {inst.instance_id for inst in pilot_instances}
    if missing:
        raise typer.BadParameter(f"pilot instances not found in dataset: {sorted(missing)}")

    small_instances = [inst for inst in all_instances if inst.metadata.get("scale") == "small"]
    representatives = _select_family_representatives(small_instances)
    charging = _build_charging_config(solver_config)
    normalizer = fit_normalization_balanced(representatives, charging=charging)
    source_hash_value = compute_source_hash()

    write_manifests(
        all_instances=all_instances,
        dev_instances=list(representatives.values()),
        normalizer=normalizer,
        source_hash_value=source_hash_value,
        experiment_config={
            "command": "run-pilot",
            "status": experiment_version,
            "methods": methods,
            "seeds": seeds,
            "max_iterations": max_iterations,
            "pilot_instance_ids": pilot_ids,
            "normalizer_families": list(representatives),
        },
    )

    executed, skipped = _run_campaign(
        instances=pilot_instances, methods=methods, seeds=seeds,
        experiment_version=experiment_version, max_iterations=max_iterations,
        solver_config=solver_config, validation_config=validation_config,
        normalizer=normalizer, source_hash_value=source_hash_value,
    )
    kept, dropped = rebuild_aggregates()
    typer.echo(
        f"Pilot run complete: {executed} runs executed, {skipped} already completed, "
        f"{kept} rows in the aggregate ({dropped} dropped for an invocation-count mismatch)."
    )


@app.command("run-full-dataset")
def run_full_dataset(
    config: Path = typer.Option(DEFAULT_EXPERIMENTS_CONFIG, "--config", help="Path to experiments.yaml"),
) -> None:
    """Run every equal-budget ranking method plus the classic reference on all 92 Schneider
    instances across the validation seeds.

    Restartable: any ``(experiment_version, source_hash, config_hash, method, instance_id,
    seed)`` key already present under ``results/raw/runs/`` is skipped. Before committing to the
    full sweep, this command times ``validation.smoke_instances`` and prints a wall-clock
    estimate; if the projected total exceeds the configured time budget, ``max_iterations`` is
    reduced and the decision is recorded in ``results/manifests/experiment_config.json``.
    """
    ensure_results_tree()
    experiments_config = load_yaml(config)
    solver_config = load_yaml(SOLVER_CONFIG_PATH) if SOLVER_CONFIG_PATH.exists() else {}
    validation_config = experiments_config.get("validation", {})
    experiment_version = str(validation_config.get("status", DEFAULT_STATUS))

    seeds: list[int] = list(validation_config.get("seeds", [0, 1, 2]))
    configured_max_iterations = int(validation_config.get("max_iterations", 20))
    reduced_max_iterations = int(validation_config.get("reduced_max_iterations", 10))
    time_budget_hours = float(validation_config.get("time_budget_hours", 2))
    representative_ids: list[str] = list(
        validation_config.get("smoke_instances", validation_config.get("pilot_instances", []))
    )
    methods = _methods_from_config(validation_config, include_classic=True)

    data_root = ROOT / experiments_config.get("data_root", "dataset/schneider/raw_instances")
    all_instances = _load_all_instances(data_root)
    small_instances = [inst for inst in all_instances if inst.metadata.get("scale") == "small"]
    representatives = _select_family_representatives(small_instances)
    charging = _build_charging_config(solver_config)
    normalizer = fit_normalization_balanced(representatives, charging=charging)
    source_hash_value = compute_source_hash()

    representative_instances = [inst for inst in all_instances if inst.instance_id in representative_ids]
    if not representative_instances:
        representative_instances = all_instances[:5]
    total_runs = len(representative_instances) * len(methods) * len(seeds)
    started = time.perf_counter()
    for instance in representative_instances:
        for method in methods:
            for seed in seeds:
                run_single_experiment(
                    instance, method, seed, experiment_version=experiment_version,
                    max_iterations=configured_max_iterations, solver_config=solver_config,
                    validation_config=validation_config, normalizer=normalizer,
                    source_hash_value=source_hash_value,
                )
    representative_seconds = time.perf_counter() - started
    avg_seconds_per_run = representative_seconds / max(total_runs, 1)
    full_run_count = len(all_instances) * len(methods) * len(seeds)
    estimated_seconds = avg_seconds_per_run * full_run_count
    typer.echo(
        f"Representative timing: {total_runs} runs in {representative_seconds:.1f}s "
        f"({avg_seconds_per_run:.3f}s/run). Estimated full campaign "
        f"({full_run_count} runs at max_iterations={configured_max_iterations}): "
        f"{estimated_seconds / 3600:.2f} hours."
    )

    budget_seconds = time_budget_hours * 3600
    if estimated_seconds > budget_seconds:
        effective_max_iterations = reduced_max_iterations
        decision = "reduced_iterations"
        estimated_seconds *= reduced_max_iterations / max(configured_max_iterations, 1)
        typer.echo(
            f"Estimate exceeds {time_budget_hours:.1f}h budget; reducing max_iterations to "
            f"{reduced_max_iterations} (revised estimate: {estimated_seconds / 3600:.2f} hours)."
        )
    else:
        effective_max_iterations = configured_max_iterations
        decision = "as_configured"
        typer.echo("Estimate within budget; continuing with the configured max_iterations.")

    write_manifests(
        all_instances=all_instances,
        dev_instances=list(representatives.values()),
        normalizer=normalizer,
        source_hash_value=source_hash_value,
        experiment_config={
            "command": "run-full-dataset",
            "status": experiment_version,
            "methods": methods,
            "seeds": seeds,
            "configured_max_iterations": configured_max_iterations,
            "effective_max_iterations": effective_max_iterations,
            "decision": decision,
            "representative_instance_ids": representative_ids,
            "representative_runs": total_runs,
            "representative_seconds": representative_seconds,
            "estimated_total_hours": estimated_seconds / 3600,
            "full_run_count": full_run_count,
            "normalizer_families": list(representatives),
        },
    )

    executed, skipped = _run_campaign(
        instances=all_instances, methods=methods, seeds=seeds,
        experiment_version=experiment_version, max_iterations=effective_max_iterations,
        solver_config=solver_config, validation_config=validation_config,
        normalizer=normalizer, source_hash_value=source_hash_value,
    )
    kept, dropped = rebuild_aggregates()
    typer.echo(
        f"Full-dataset run complete: {executed} runs executed, {skipped} already completed, "
        f"{kept} rows in the aggregate ({dropped} dropped for an invocation-count mismatch)."
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
