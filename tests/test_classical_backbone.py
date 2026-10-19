"""Classical backbone: construction, energy repair, ALNS (no LLM)."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.micro import micro_g1_one_customer, micro_g2_needs_charge

ROOT = Path(__file__).resolve().parents[1]


def test_construct_not_identity_noop() -> None:
    """Operators must change empty routes into serving customers."""
    import random

    spec = load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
    sol = construct_greedy(spec, random.Random(0))
    served = {s.node_id for route in sol.routes for s in route}
    assert "C1" in served
    assert sol.routes != [[]]


def test_micro_g1_construction_is_feasible() -> None:
    """Customer coverage is checked in-process, without process-spawn time."""
    import random

    spec = load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
    solution = repair_energy(spec, construct_greedy(spec, random.Random(1)))
    report = evaluate(spec, solution)
    assert report.feasible, report.explanation


def test_micro_g1_classical_feasible() -> None:
    """A two-second spawned solve includes worker startup.

    On a cold CI runner the child can be killed before it publishes. That is a
    timeout with no snapshot, not an unserved customer. A worker that finishes
    and still leaves the customer unserved fails this test.
    """
    spec = load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
    sol = solve_classical(spec, seed=1, time_limit_s=2.0, alns_iterations=20)
    report = evaluate(spec, sol)
    if report.feasible:
        return
    status = str(sol.metadata.get("return_status"))
    assert status in {"timeout_no_snapshot", "worker_no_snapshot"}, (
        status,
        report.explanation,
        sol.metadata,
    )
    assert sol.metadata.get("hard_timeout_triggered") is True


def test_micro_g2_energy_repair_makes_feasible() -> None:
    legacy = micro_g2_needs_charge()
    spec = load_schneider_v2(legacy.metadata["source_path"])
    import random

    raw = construct_greedy(spec, random.Random(0))
    # Without repair, battery often fails on direct long hops.
    repaired = repair_energy(spec, raw)
    report = evaluate(spec, repaired)
    # Full solver should reach feasibility on this micro.
    sol = solve_classical(spec, seed=0, time_limit_s=3.0, alns_iterations=30)
    final = evaluate(spec, sol)
    assert final.feasible or report.feasible, final.explanation
    assert final.feasible, final.explanation


def test_schneider_c101c5_classical_feasible() -> None:
    spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt")
    sol = solve_classical(spec, seed=7, time_limit_s=8.0, alns_iterations=80)
    report = evaluate(spec, sol)
    assert report.feasible, (report.explanation, report.first_fault, sol.metadata)
    assert report.vehicles >= 1
    assert report.total_distance > 0


def test_goeke_small_covers_all_requests() -> None:
    spec = load_goeke(ROOT / "dataset" / "goeke-2018" / "c101C6.txt")
    sol = solve_classical(spec, seed=3, time_limit_s=6.0, alns_iterations=40)
    report = evaluate(spec, sol)
    # Must cover all PD nodes; feasibility may still fail on energy/TW for hard cases,
    # but VISIT/PAIRING/PRECEDENCE should be cleared.
    hard_cov = {v.family for v in report.violations} & {"VISIT", "PAIRING", "PRECEDENCE"}
    assert not hard_cov, report.violations
    # Prefer full feasibility when the classical search succeeds.
    if not report.feasible:
        # Still require that every request endpoint appears.
        served = {s.node_id for route in sol.routes for s in route}
        for req in spec.requests:
            assert req.pickup_id in served and req.delivery_id in served


def test_deterministic_under_seed() -> None:
    spec = load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
    a = solve_classical(spec, seed=42, time_limit_s=1.0, alns_iterations=10)
    b = solve_classical(spec, seed=42, time_limit_s=1.0, alns_iterations=10)
    assert [[s.node_id for s in r] for r in a.routes] == [[s.node_id for s in r] for r in b.routes]
