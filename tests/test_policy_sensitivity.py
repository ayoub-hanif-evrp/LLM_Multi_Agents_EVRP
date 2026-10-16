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
