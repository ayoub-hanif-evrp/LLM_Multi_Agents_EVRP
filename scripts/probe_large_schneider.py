"""Time construction and energy repair on Schneider discovery c101_21.

This is not an RC2 instance. The script does not run ALNS.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v2" / "diagnostics" / "large_development" / "repair_trace.json"


def _faults(report) -> dict[str, int]:
    counts: dict[str, int] = {}
    for violation in report.violations:
        counts[violation.family] = counts.get(violation.family, 0) + 1
    return counts


def main() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "c101_21.txt")
    customers = sum(1 for node in spec.nodes if node.kind == "customer")
    stations = sum(1 for node in spec.nodes if node.kind == "station")
    started = time.monotonic()
    constructed = construct_greedy(spec, random.Random(7))
    construct_s = time.monotonic() - started
    before = evaluate(spec, constructed)
    deadline = time.monotonic() + 15.0
    repaired = repair_energy(spec, constructed, deadline=deadline)
    repair_s = time.monotonic() - started - construct_s
    after = evaluate(spec, repaired)

    from evrptw_autolab.backbone.construct import _customer_order, insert_customer_fast
    from evrptw_autolab.backbone.util import empty_route
    from evrptw_autolab.problem.v2.types import SolutionV2

    fast_started = time.monotonic()
    vehicle_id = spec.vehicle_types[0].type_id
    fast = SolutionV2(routes=[empty_route(spec, vehicle_id)], vehicle_assignments=[vehicle_id])
    rng = random.Random(7)
    for customer_id in _customer_order(spec, rng):
        fast = insert_customer_fast(spec, fast, customer_id)
    if len(fast.routes) > 1 and len(fast.routes[0]) == 2:
        fast.routes = fast.routes[1:]
        fast.vehicle_assignments = fast.vehicle_assignments[1:]
    fast_construct_s = time.monotonic() - fast_started
    fast_before = evaluate(spec, fast)
    fast_repaired = repair_energy(spec, fast, deadline=time.monotonic() + 15.0)
    fast_repair_s = time.monotonic() - fast_started - fast_construct_s
    fast_after = evaluate(spec, fast_repaired)
    payload = {
        "instance_id": "c101_21",
        "seed": 7,
        "customers": customers,
        "stations": stations,
        "routes_after_construction": len(constructed.routes),
        "construct_s": round(construct_s, 3),
        "repair_s": round(repair_s, 3),
        "before_feasible": before.feasible,
        "before_faults": _faults(before),
        "after_feasible": after.feasible,
        "after_faults": _faults(after),
        "after_key": list(after.objective_key) if after.feasible else None,
        "fast_routes": len(fast.routes),
        "fast_construct_s": round(fast_construct_s, 3),
        "fast_repair_s": round(fast_repair_s, 3),
        "fast_before_feasible": fast_before.feasible,
        "fast_before_faults": _faults(fast_before),
        "fast_after_feasible": fast_after.feasible,
        "fast_after_faults": _faults(fast_after),
        "fast_after_key": list(fast_after.objective_key) if fast_after.feasible else None,
        "fast_vehicles": fast_after.vehicles if fast_after.feasible else None,
        "note": "In-process construction plus one energy repair. No ALNS. Not RC2.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(payload, flush=True)


if __name__ == "__main__":
    main()
