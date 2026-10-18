"""Valid nondefault scores must change solver decisions on a controlled instance."""
from __future__ import annotations

import random
from pathlib import Path

from evrptw_autolab.backbone.alns import destroy_worst
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import _best_station_between
from evrptw_autolab.backbone.util import vehicle_for_route
from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

BODY = """\
StringID   Type       x          y          demand     ReadyTime  DueDate    ServiceTime
D0         d          0.0        0.0        0.0        0.0        1000.0     0.0
S_near     f          10.0       0.0        0.0        0.0        1000.0     0.0
S_far      f          40.0       30.0       0.0        0.0        1000.0     0.0
C_early    c          1.0        0.0        1.0        0.0        100.0      0.0
C_mid      c          8.0        6.0        1.0        0.0        500.0      0.0
C_late     c          20.0       0.0        1.0        0.0        900.0      0.0

Q Vehicle fuel tank capacity /100.0/
C Vehicle load capacity /100.0/
r fuel consumption rate /1.0/
g inverse refueling rate /1.0/
v average Velocity /1.0/
"""


def _spec(tmp_path: Path):
    path = tmp_path / "micro_policy.txt"
    path.write_text(BODY, encoding="utf-8")
    return load_schneider_v2(path)


def _bundle(kind: str, expression: str, **rest: str):
    sources = {
        "insertion_score": wrap_expression("insertion_score", rest.get("insertion", "delta_distance")),
        "station_score": wrap_expression("station_score", rest.get("station", "detour")),
        "removal_priority": wrap_expression("removal_priority", rest.get("removal", "due_time")),
    }
    sources[kind] = wrap_expression(kind, expression)  # type: ignore[index]
    bundle, errors = load_bundle(sources)
    assert not errors, errors
    bundle.call_counts = {}  # type: ignore[attr-defined]
    return bundle


def _route_ids(spec, policy) -> list[str]:
    sol = construct_greedy(spec, random.Random(0), policy=policy)
    return [stop.node_id for stop in sol.routes[0]]


def test_insertion_score_changes_customer_order(tmp_path: Path) -> None:
    # Wide windows. The third customer has unequal edge detours, so minimizing
    # versus maximizing delta_distance selects a different slot.
    body = (
        BODY.replace("100.0      0.0", "1000.0     0.0")
        .replace("500.0      0.0", "1000.0     0.0")
        .replace("900.0      0.0", "1000.0     0.0")
    )
    path = tmp_path / "micro_insert.txt"
    path.write_text(body, encoding="utf-8")
    spec = load_schneider_v2(path)
    near = _bundle("insertion_score", "delta_distance")
    far = _bundle("insertion_score", "-1.0 * delta_distance")
    assert _route_ids(spec, near) != _route_ids(spec, far)
    assert near.call_counts["insertion_score"] > 0


def test_station_score_changes_station_choice(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    vehicle = spec.vehicle_types[0]
    short = _bundle("station_score", "detour")
    long = _bundle("station_score", "-1.0 * detour")
    a = _best_station_between(spec, "D0", "C_late", vehicle, battery_arrival=100.0, policy=short)
    b = _best_station_between(spec, "D0", "C_late", vehicle, battery_arrival=100.0, policy=long)
    assert a is not None and b is not None and a != b
    assert short.call_counts["station_score"] > 0


def test_removal_priority_changes_destroy_choice(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    base = _bundle("removal_priority", "due_time")
    sol = construct_greedy(spec, random.Random(0), policy=base)
    early = _bundle("removal_priority", "due_time")
    late = _bundle("removal_priority", "-1.0 * due_time")
    _, removed_early = destroy_worst(spec, sol, random.Random(1), 1, policy=early)
    _, removed_late = destroy_worst(spec, sol, random.Random(1), 1, policy=late)
    assert removed_early != removed_late
    assert early.call_counts["removal_priority"] > 0
    assert vehicle_for_route(spec, sol, 0).type_id


def test_recorded_montoya_removal_source_is_linked_but_not_fully_proven() -> None:
    from evrptw_autolab.experiments.montoya_attribution import provenance_manifest

    manifest = provenance_manifest()
    removal = manifest["components"]["removal_priority"]
    assert "due_time - route_distance_share * 5.0 + float(rng_value > 0.5)" in removal["executed_source"]
    assert manifest["model_digest"] is None
    assert manifest["original_model_response"] is None
    assert manifest["classification"] == "promising_policy_ablation_incomplete_generation_provenance"
    assert manifest["original_bundle_feasible"] is False
    assert manifest["instance_sha256"]


def _pair(instance: str, seed: int, outcome: str, default_duration: float, removal_duration: float) -> list[dict]:
    common = {
        "instance_id": instance,
        "seed": seed,
        "vehicles": 3,
        "first_fault": "OK: feasible",
        "feasible": True,
    }
    return [
        {**common, "variant": "default", "duration": default_duration, "paired_outcome": "baseline"},
        {**common, "variant": "removal_only", "duration": removal_duration, "paired_outcome": outcome},
    ]


def test_replication_summary_does_not_treat_one_seed_as_general() -> None:
    from evrptw_autolab.experiments.montoya_attribution import (
        DEPLOYMENT_SEEDS,
        DEVELOPMENT_INSTANCES,
        summarize_replication,
    )

    assert DEVELOPMENT_INSTANCES == ("tc0c10s2cf1", "tc0c10s3cf1")
    assert DEPLOYMENT_SEEDS == (7, 11, 22)
    rows = _pair("tc0c10s2cf1", 7, "candidate", 32.0, 25.0)
    rows += _pair("tc0c10s2cf1", 11, "baseline", 25.0, 32.0)
    summary = summarize_replication(rows)
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["classification"] == "specialized_not_universally_superior"
    tied = _pair("tc0c10s2cf1", 11, "tie", 25.4, 25.4)
    mixed = summarize_replication(rows[:2] + tied)
    assert mixed["classification"] == "improves_a_subset_of_development_pairs"


def test_infeasible_objective_does_not_beat_feasible_baseline() -> None:
    from evrptw_autolab.experiments.policy_sensitivity import paired_feasible_outcome

    assert paired_feasible_outcome(True, (32.115,), False, (22.768,)) == "baseline"
    assert paired_feasible_outcome(True, (2.0, 270.0), True, (2.0, 267.0)) == "candidate"
    assert paired_feasible_outcome(False, (1.0,), False, (0.0,)) == "tie_infeasible"
