"""Measure classical repair ranking overhead before/after lazy feature extraction."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.decision_features import insertion_delta_distance, insertion_features_v4
from evrptw_autolab.backbone.route_screen import screen_repair_route
from evrptw_autolab.backbone.util import make_customer_stop, vehicle_for_route
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.backbone.construct import construct_greedy
import random

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "v2" / "repair_scoring_overhead.json"


def main() -> None:
    spec = load_schneider_v2(ROOT / "dataset/schneider/raw_instances/c101C5.txt")
    sol = construct_greedy(spec, random.Random(7), policy=None)
    # Pick a customer not on route 0 if possible.
    node_id = next(n.id for n in spec.nodes if n.kind == "customer")
    route = sol.routes[0]
    vehicle = vehicle_for_route(spec, sol, 0)
    positions = list(range(1, len(route)))

    def eager():
        for pos in positions:
            trial = list(route)
            trial.insert(pos, make_customer_stop(node_id, spec))
            ok, distance = screen_repair_route(spec, trial, vehicle, allow_battery_debt=True)
            if not ok:
                continue
            feats = insertion_features_v4(spec, route, pos, node_id, vehicle)
            _ = float(distance), float(feats["delta_distance"])

    def lazy():
        for pos in positions:
            trial = list(route)
            trial.insert(pos, make_customer_stop(node_id, spec))
            ok, distance = screen_repair_route(spec, trial, vehicle, allow_battery_debt=True)
            if not ok:
                continue
            _ = float(distance), insertion_delta_distance(spec, route, pos, node_id)

    # Warmup
    eager()
    lazy()
    n = 200
    t0 = time.perf_counter()
    for _ in range(n):
        eager()
    eager_s = time.perf_counter() - t0
    t0 = time.perf_counter()
    for _ in range(n):
        lazy()
    lazy_s = time.perf_counter() - t0
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_repair_scoring_overhead_v1",
        "instance_id": "c101C5",
        "repeats": n,
        "positions": len(positions),
        "eager_full_features_s": round(eager_s, 4),
        "lazy_delta_only_s": round(lazy_s, 4),
        "speedup": round(eager_s / lazy_s, 3) if lazy_s > 0 else None,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
