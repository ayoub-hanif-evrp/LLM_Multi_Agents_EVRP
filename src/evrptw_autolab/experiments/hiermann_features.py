"""Hand-written Hiermann policies that can see route length and fleet cost.

These expressions are not model output. A policy is kept only when it stays
feasible and its native cost is strictly better than both the frozen classical
call and the default scoring bundle on every measured seed.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import default_sources, wrap_expression
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.v2.features import (
    FEATURE_SCHEMA_V3,
    FEATURE_SCHEMA_V4,
    FEATURE_SCHEMA_VERSION,
)

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "dataset" / "hiermann-et-al-2017-set-1"
OUT = ROOT / "results" / "recovery_v2" / "hiermann_features.json"


def _policy(removal: str | None, insertion: str | None) -> Any:
    sources = default_sources(FEATURE_SCHEMA_VERSION)
    schema = FEATURE_SCHEMA_VERSION
    if removal is not None:
        sources["removal_priority"] = wrap_expression("removal_priority", removal, FEATURE_SCHEMA_V3)
        schema = FEATURE_SCHEMA_V3
    if insertion is not None:
        sources["insertion_score"] = wrap_expression("insertion_score", insertion, FEATURE_SCHEMA_V3)
        schema = FEATURE_SCHEMA_V3
    bundle, errors = load_bundle(sources, feature_schema=schema)
    if errors:
        raise RuntimeError(errors)
    return bundle


ARMS: dict[str, Any] = {
    "classical_call": None,
    "default_bundle": _policy(None, None),
    "remove_long_route": _policy("own_route_distance", None),
    "penalise_new_route": _policy(None, "delta_distance + new_route_fixed_cost"),
}


def solve_arm(instance: str, seed: int, arm: str) -> dict[str, Any]:
    spec = load_hiermann(DATA / f"{instance}.txt")
    started = time.perf_counter()
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=15.0,
        alns_iterations=40,
        policy=ARMS[arm],
    )
    report = evaluate(spec, solution)
    return {
        "instance_id": instance,
        "seed": seed,
        "arm": arm,
        "origin": "classical_call" if arm == "classical_call" else "hand_written_policy",
        "llm_calls": 0,
        "feasible": bool(report.feasible),
        "objective_key": [float(value) for value in report.objective_key] if report.feasible else None,
        "vehicles": report.vehicles if report.feasible else None,
        "distance": report.total_distance if report.feasible else None,
        "first_fault": None if report.first_fault is None else report.first_fault.family,
        "wall_s": round(time.perf_counter() - started, 3),
        "completed_within_budget": bool(solution.metadata.get("completed_within_budget")),
    }


def _comparable(row: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        row["feasible"]
        and baseline["feasible"]
        and row["completed_within_budget"]
        and baseline["completed_within_budget"]
        and row["objective_key"] is not None
        and baseline["objective_key"] is not None
    )


def _no_loss(row: dict[str, Any], baseline: dict[str, Any]) -> bool:
    if not _comparable(row, baseline):
        return False
    return tuple(row["objective_key"]) <= tuple(baseline["objective_key"])


def _strict_win(row: dict[str, Any], baseline: dict[str, Any]) -> bool:
    if not _comparable(row, baseline):
        return False
    return tuple(row["objective_key"]) < tuple(baseline["objective_key"])


def _holds_on_measured_pairs(rows: list[dict[str, Any]], arm: str) -> bool:
    """No loss on any measured pair, and at least one strict improvement."""
    baseline = {
        (row["instance_id"], int(row["seed"])): row
        for row in rows
        if row["arm"] == "classical_call"
    }
    matched = [row for row in rows if row["arm"] == arm]
    if not matched:
        return False
    improved = False
    for row in matched:
        base = baseline.get((row["instance_id"], int(row["seed"])))
        if base is None or not _no_loss(row, base):
            return False
        improved = improved or _strict_win(row, base)
    return improved


def main() -> None:
    rows: list[dict[str, Any]] = []
    gate = [(name, 7, "c101_21") for name in ARMS]
    for arm, seed, instance in gate:
        rows.append(solve_arm(instance, seed, arm))
    by_arm = {row["arm"]: row for row in rows}
    classical = by_arm["classical_call"]
    default = by_arm["default_bundle"]
    winners = [
        arm
        for arm in ("remove_long_route", "penalise_new_route")
        if _strict_win(by_arm[arm], classical) and _strict_win(by_arm[arm], default)
    ]
    if winners:
        for seed in (11, 22):
            for arm in ("classical_call", "default_bundle", *winners):
                rows.append(solve_arm("c101_21", seed, arm))
        still: list[str] = []
        for arm in winners:
            arm_rows = sorted(
                (row for row in rows if row["arm"] == arm and row["instance_id"] == "c101_21"),
                key=lambda item: int(item["seed"]),
            )
            classical_rows = sorted(
                (row for row in rows if row["arm"] == "classical_call" and row["instance_id"] == "c101_21"),
                key=lambda item: int(item["seed"]),
            )
            default_rows = sorted(
                (row for row in rows if row["arm"] == "default_bundle" and row["instance_id"] == "c101_21"),
                key=lambda item: int(item["seed"]),
            )
            kept = all(
                _no_loss(row, base) and _no_loss(row, other)
                for row, base, other in zip(arm_rows, classical_rows, default_rows, strict=True)
            )
            improved = any(
                _strict_win(row, base) or _strict_win(row, other)
                for row, base, other in zip(arm_rows, classical_rows, default_rows, strict=True)
            )
            if kept and improved:
                still.append(arm)
        if still:
            for instance in ("r101_21", "c201_21"):
                for seed in (7, 11, 22):
                    for arm in ("classical_call", *still):
                        rows.append(solve_arm(instance, seed, arm))
        winners = [
            arm
            for arm in still
            if _holds_on_measured_pairs(rows, arm)
        ]
    payload = {
        "time_limit_s": 15.0,
        "alns_iterations": 40,
        "llm_calls": 0,
        "promoted": winners,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"promoted": winners, "rows": rows}, indent=2))


def measure_marginal_removal(out: Path | None = None) -> dict[str, Any]:
    """One predeclared removal score. Do not replace the expression after a loss."""
    sources = default_sources(FEATURE_SCHEMA_VERSION)
    sources["removal_priority"] = wrap_expression(
        "removal_priority", "marginal_removal_distance", FEATURE_SCHEMA_V4
    )
    bundle, errors = load_bundle(sources, feature_schema=FEATURE_SCHEMA_VERSION)
    if errors:
        raise RuntimeError(errors)
    target = out or (ROOT / "results" / "recovery_v4" / "marginal_removal.json")
    rows: list[dict[str, Any]] = []
    for instance in ("c101_21", "r101_21", "c201_21"):
        for seed in (7, 11, 22):
            for arm, policy, origin in (
                ("classical_call", None, "classical_call"),
                ("marginal_removal_distance", bundle, "hand_written_feature_check"),
            ):
                spec = load_hiermann(DATA / f"{instance}.txt")
                started = time.perf_counter()
                solution = solve_classical(
                    spec,
                    seed=seed,
                    time_limit_s=15.0,
                    alns_iterations=40,
                    policy=policy,
                )
                report = evaluate(spec, solution)
                rows.append(
                    {
                        "instance_id": instance,
                        "seed": seed,
                        "arm": arm,
                        "origin": origin,
                        "llm_calls": 0,
                        "feasible": bool(report.feasible),
                        "objective_key": (
                            [float(value) for value in report.objective_key] if report.feasible else None
                        ),
                        "vehicles": report.vehicles if report.feasible else None,
                        "distance": report.total_distance if report.feasible else None,
                        "wall_s": round(time.perf_counter() - started, 3),
                        "completed_within_budget": bool(solution.metadata.get("completed_within_budget")),
                    }
                )
    losses = []
    wins = []
    for instance in ("c101_21", "r101_21", "c201_21"):
        for seed in (7, 11, 22):
            base = next(row for row in rows if row["arm"] == "classical_call" and row["instance_id"] == instance and row["seed"] == seed)
            trial = next(
                row
                for row in rows
                if row["arm"] == "marginal_removal_distance" and row["instance_id"] == instance and row["seed"] == seed
            )
            pair = {"instance_id": instance, "seed": seed}
            if not (
                trial["feasible"]
                and base["feasible"]
                and trial["completed_within_budget"]
                and tuple(trial["objective_key"]) <= tuple(base["objective_key"])
            ):
                losses.append(pair)
            elif tuple(trial["objective_key"]) < tuple(base["objective_key"]):
                wins.append(pair)
    decision = "kept" if wins and not losses else "NOT_GENERALIZED"
    payload = {
        "expression": "marginal_removal_distance",
        "schema_for_repair": FEATURE_SCHEMA_VERSION,
        "time_limit_s": 15.0,
        "alns_iterations": 40,
        "llm_calls": 0,
        "decision": decision,
        "wins": wins,
        "losses": losses,
        "rows": rows,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def measure_native_repair(out: Path | None = None) -> dict[str, Any]:
    """Classical call after native-cost insertion. Zero model calls. Does not edit a rejected score."""
    previous = json.loads((ROOT / "results" / "recovery_v4" / "marginal_removal.json").read_text(encoding="utf-8"))
    baseline = {
        (row["instance_id"], row["seed"]): row
        for row in previous["rows"]
        if row["arm"] == "classical_call"
    }
    target = out or (ROOT / "results" / "recovery_v4" / "native_energy_repair.json")
    rows: list[dict[str, Any]] = []
    for instance in ("c101_21", "r101_21", "c201_21"):
        spec = load_hiermann(DATA / f"{instance}.txt")
        for seed in (7, 11, 22):
            started = time.perf_counter()
            solution = solve_classical(spec, seed=seed, time_limit_s=15.0, alns_iterations=40)
            report = evaluate(spec, solution)
            prior = baseline[(instance, seed)]
            rows.append(
                {
                    "instance_id": instance,
                    "seed": seed,
                    "arm": "classical_native_energy_repair",
                    "origin": "classical_call",
                    "llm_calls": 0,
                    "feasible": bool(report.feasible),
                    "objective_key": [float(value) for value in report.objective_key] if report.feasible else None,
                    "previous_classical": prior["objective_key"],
                    "vehicles": report.vehicles if report.feasible else None,
                    "previous_vehicles": prior["vehicles"],
                    "wall_s": round(time.perf_counter() - started, 3),
                    "completed_within_budget": bool(solution.metadata.get("completed_within_budget")),
                }
            )
    losses = []
    wins = []
    for row in rows:
        pair = {"instance_id": row["instance_id"], "seed": row["seed"]}
        if not (
            row["feasible"]
            and row["completed_within_budget"]
            and row["objective_key"] is not None
            and tuple(row["objective_key"]) <= tuple(row["previous_classical"])
        ):
            losses.append(pair)
        elif tuple(row["objective_key"]) < tuple(row["previous_classical"]):
            wins.append(pair)
    if wins and not losses:
        decision = "improved"
    elif wins and losses:
        decision = "mixed"
    else:
        decision = "NOT_IMPROVED"
    payload = {
        "origin": "classical_call",
        "llm_calls": 0,
        "time_limit_s": 15.0,
        "alns_iterations": 40,
        "decision": decision,
        "wins": wins,
        "losses": losses,
        "rows": rows,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    main()
