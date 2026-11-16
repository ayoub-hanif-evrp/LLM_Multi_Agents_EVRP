"""Compare cold-spawn vs warm-spawn classical solves for equivalence."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import ClassicalSolver, reset_warm_worker, solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "diagnostics" / "worker_equivalence.json"


def _fingerprint(solution: Any) -> str:
    routes = [[(s.node_id, s.event, s.charge_amount) for s in route] for route in solution.routes]
    blob = json.dumps(
        {
            "routes": routes,
            "assignments": list(solution.vehicle_assignments),
            "changed_decisions": solution.metadata.get("changed_decisions"),
            "source_hash": solution.metadata.get("source_hash"),
            "method_attribution": solution.metadata.get("method_attribution"),
            "policy_executed": solution.metadata.get("policy_executed"),
            "alns_iterations": solution.metadata.get("alns_iterations"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _snapshot(spec: Any, solution: Any, runtime_s: float) -> dict[str, Any]:
    report = evaluate(spec, solution)
    return {
        "runtime_s": round(runtime_s, 4),
        "feasible": bool(report.feasible),
        "objective_key": [float(v) for v in report.objective_key],
        "vehicles": report.vehicles,
        "alns_iterations_done": solution.metadata.get("alns_iterations"),
        "changed_decisions": int(solution.metadata.get("changed_decisions") or 0),
        "policy_executed": bool(solution.metadata.get("policy_executed")),
        "method_attribution": solution.metadata.get("method_attribution"),
        "source_hash": solution.metadata.get("source_hash"),
        "hard_timeout_triggered": bool(solution.metadata.get("hard_timeout_triggered")),
        "return_status": solution.metadata.get("return_status"),
        "fingerprint": _fingerprint(solution),
    }


def _handcrafted() -> OperatorSpec:
    return OperatorSpec(
        operator_id="long_detour",
        version="1",
        source_agent="handcrafted",
        description="Prefer short insertion deltas.",
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        candidate_scoring_policy="delta_distance",
        applicability_rule="1",
        mine_counterexamples=False,
        fallback_operator="classical_default",
        source_hash="handcrafted-verify",
    )


def _run_case(
    *,
    family: str,
    instance_id: str,
    path: Path,
    loader: Any,
    limit: float,
    iters: int,
    policy: OperatorSpec | None,
) -> dict[str, Any]:
    print(f"case {family}/{instance_id} start", flush=True)
    spec = loader(path)
    kwargs = {
        "seed": 7,
        "time_limit_s": limit,
        "alns_iterations": iters,
        "experiment_partition": "development",
        "policy": policy,
    }
    reset_warm_worker()
    t0 = time.perf_counter()
    inproc = solve_classical(spec, hard_timeout=False, **kwargs)
    inproc_s = time.perf_counter() - t0
    print(f"  inprocess {inproc_s:.3f}s", flush=True)

    reset_warm_worker()
    t1 = time.perf_counter()
    cold = solve_classical(spec, hard_timeout=True, **kwargs)
    cold_s = time.perf_counter() - t1
    print(f"  cold {cold_s:.3f}s", flush=True)

    t2 = time.perf_counter()
    warm = solve_classical(spec, hard_timeout=True, **kwargs)
    warm_s = time.perf_counter() - t2
    print(f"  warm {warm_s:.3f}s", flush=True)

    timed = ClassicalSolver(
        seed=1,
        time_limit_s=0.35,
        alns_iterations=1,
        use_alns=False,
        debug_sleep_s=3.0,
        debug_publish_before_sleep=True,
        hard_timeout=True,
        experiment_partition="development",
    ).solve(spec)
    print(f"  timeout_status={timed.metadata.get('return_status')}", flush=True)

    crash = ClassicalSolver(
        seed=1,
        time_limit_s=2.0,
        alns_iterations=1,
        use_alns=False,
        debug_crash=True,
        hard_timeout=True,
        experiment_partition="development",
    ).solve(spec)
    print(f"  crash_status={crash.metadata.get('return_status')}", flush=True)

    reset_warm_worker()
    t3 = time.perf_counter()
    after = solve_classical(spec, hard_timeout=True, **kwargs)
    after_s = time.perf_counter() - t3
    print(f"  after_recovery {after_s:.3f}s", flush=True)

    a = _snapshot(spec, inproc, inproc_s)
    b = _snapshot(spec, cold, cold_s)
    c = _snapshot(spec, warm, warm_s)
    d = _snapshot(spec, after, after_s)
    spawn_equal = (
        b["objective_key"] == c["objective_key"] == d["objective_key"]
        and b["fingerprint"] == c["fingerprint"] == d["fingerprint"]
        and b["feasible"] == c["feasible"] == d["feasible"]
        and b["changed_decisions"] == c["changed_decisions"] == d["changed_decisions"]
        and b["method_attribution"] == c["method_attribution"] == d["method_attribution"]
        and not b["hard_timeout_triggered"]
        and not c["hard_timeout_triggered"]
        and not d["hard_timeout_triggered"]
    )
    return {
        "family": family,
        "instance_id": instance_id,
        "policy": policy is not None,
        "inprocess": a,
        "cold": b,
        "warm": c,
        "after_timeout_crash_recovery": d,
        "timeout_status": timed.metadata.get("return_status"),
        "crash_status": crash.metadata.get("return_status"),
        "spawn_modes_equivalent": spawn_equal,
        "inprocess_matches_spawn": a["fingerprint"] == b["fingerprint"]
        and a["objective_key"] == b["objective_key"],
        "equivalent": spawn_equal,
    }


def main() -> None:
    cases = [
        ("schneider", "c101C5", ROOT / "dataset/schneider/raw_instances/c101C5.txt", load_schneider_v2, 2.0, 8, None),
        (
            "schneider",
            "c101C5-policy",
            ROOT / "dataset/schneider/raw_instances/c101C5.txt",
            load_schneider_v2,
            2.0,
            8,
            _handcrafted(),
        ),
        ("hiermann", "c101_21", ROOT / "dataset/hiermann-et-al-2017-set-1/c101_21.txt", load_hiermann, 3.0, 5, None),
    ]
    rows = []
    for family, instance_id, path, loader, limit, iters, policy in cases:
        if not path.exists():
            rows.append({"family": family, "instance_id": instance_id, "status": "missing"})
            continue
        row = _run_case(
            family=family,
            instance_id=instance_id,
            path=path,
            loader=loader,
            limit=limit,
            iters=iters,
            policy=policy,
        )
        rows.append(row)
        print(family, instance_id, "equivalent" if row["equivalent"] else "MISMATCH", flush=True)
    payload = {
        "protocol": "cipher_worker_equivalence",
        "rows": rows,
        "all_equivalent": all(bool(r.get("equivalent")) for r in rows if "equivalent" in r),
        "note": "Primary check is cold/warm/recovery under hard_timeout=True. In-process may differ due to deadline margins.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, "all_equivalent=", payload["all_equivalent"], flush=True)


if __name__ == "__main__":
    main()
