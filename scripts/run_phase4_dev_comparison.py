"""Matched-budget development comparison of classical / handcrafted / random / live / multi-role.

Native objectives are never averaged across families. Live multi-role success is reported
separately from scripted arms.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.alns import repair_greedy
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate, is_better
from evrptw_autolab.discovery.controller import operator_fingerprint
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.research.compare import scripted_report
from evrptw_autolab.research.panel import development_case

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "diagnostics" / "phase4_dev_comparison.json"
SEEDS = (7, 11, 22)

HANDCRAFTED = (
    ("handcrafted_short", "delta_distance", "1"),
    ("handcrafted_long", "-1 * delta_distance", "1"),
)
RANDOM_POOL = (
    "delta_distance",
    "delta_travel_time",
    "delta_distance + incremental_energy_cost",
    "route_customer_count + delta_distance",
    "-1 * battery_margin + delta_distance",
)


def _op(operator_id: str, scoring: str, rule: str = "1") -> OperatorSpec:
    operator = OperatorSpec(
        operator_id=operator_id,
        version="1",
        source_agent="phase4",
        description=scoring,
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        candidate_scoring_policy=scoring,
        applicability_rule=rule,
        mine_counterexamples=False,
        fallback_operator="classical_default",
    )
    return operator.model_copy(update={"source_hash": operator_fingerprint(operator)})


def _repair_arm(
    spec: Any,
    solution: Any,
    removed: list[tuple[str, ...]],
    operator: OperatorSpec | None,
    *,
    seed: int,
) -> dict[str, Any]:
    repaired = repair_greedy(
        spec, solution, removed, random.Random(seed), operator, partition="development"
    )
    report = evaluate(spec, repaired)
    decision = repaired.metadata.get("search_decision") or {}
    return {
        "feasible": bool(report.feasible),
        "objective_key": [float(v) for v in report.objective_key],
        "changed": bool(decision.get("changed")),
        "action": decision.get("action"),
        "reason": decision.get("reason"),
        "changed_decisions": int(repaired.metadata.get("changed_decisions") or 0),
    }


def _paired_solve(family: str, path: Path, loader: Any, limit: float, iters: int, operator: OperatorSpec | None, seed: int) -> dict[str, Any]:
    spec = loader(path)
    classical = solve_classical(
        spec,
        seed=seed,
        time_limit_s=limit,
        alns_iterations=iters,
        hard_timeout=False,
        experiment_partition="development",
        policy=None,
    )
    candidate = solve_classical(
        spec,
        seed=seed,
        time_limit_s=limit,
        alns_iterations=iters,
        hard_timeout=False,
        experiment_partition="development",
        policy=operator,
    )
    c_rep = evaluate(spec, classical)
    p_rep = evaluate(spec, candidate)
    if c_rep.feasible and not p_rep.feasible:
        outcome = "feasibility_regression"
    elif is_better(p_rep, c_rep):
        outcome = "improved"
    elif is_better(c_rep, p_rep):
        outcome = "objective_regression"
    else:
        outcome = "tie"
    return {
        "family": family,
        "seed": seed,
        "classical_objective_key": [float(v) for v in c_rep.objective_key],
        "candidate_objective_key": [float(v) for v in p_rep.objective_key],
        "classical_feasible": bool(c_rep.feasible),
        "candidate_feasible": bool(p_rep.feasible),
        "outcome": outcome,
        "changed_decisions": int(candidate.metadata.get("changed_decisions") or 0),
        "policy_executed": bool(candidate.metadata.get("policy_executed")),
    }


def main() -> None:
    candidates = sorted(
        (ROOT / "results" / "cipher" / "live_signal").glob("ollama_signal_2026-11-16*.json"),
        key=lambda path: path.name,
    )
    live_path = candidates[-1] if candidates else ROOT / "results" / "cipher" / "live_signal" / "ollama_signal.json"
    live_payload = json.loads(live_path.read_text(encoding="utf-8")) if live_path.exists() else {}
    live_op = None
    if live_payload.get("operator"):
        live_op = OperatorSpec.model_validate(live_payload["operator"])
        live_op = live_op.model_copy(update={"mine_counterexamples": False})

    spec, solution, removed = development_case()
    baseline = _repair_arm(spec, solution, removed, None, seed=1)
    arms: dict[str, Any] = {"classical": baseline}
    for name, scoring, rule in HANDCRAFTED:
        arms[name] = _repair_arm(spec, solution, removed, _op(name, scoring, rule), seed=1)
    rng = random.Random(1)
    random_scoring = rng.choice(RANDOM_POOL)
    arms["random_valid"] = _repair_arm(
        spec, solution, removed, _op("random_valid", random_scoring, "1"), seed=1
    )
    arms["random_valid"]["scoring"] = random_scoring
    if live_op is not None:
        arms["live_multi_role"] = _repair_arm(spec, solution, removed, live_op, seed=1)
        arms["live_multi_role"]["live_gate"] = live_payload.get("gate")
        arms["live_multi_role"]["scoring"] = live_op.candidate_scoring_policy
        arms["live_multi_role"]["applicability_rule"] = live_op.applicability_rule
    scripted = scripted_report()

    paired_rows = []
    if live_op is not None and live_payload.get("gate") in {"beneficial", "ok", "no_improvement", "objective_regression", "behaviorally_inert"}:
        cases = (
            ("schneider", ROOT / "dataset/schneider/raw_instances/c101C5.txt", load_schneider_v2, 5.0, 20),
            ("hiermann", ROOT / "dataset/hiermann-et-al-2017-set-1/c101_21.txt", load_hiermann, 8.0, 10),
        )
        for family, path, loader, limit, iters in cases:
            if not path.exists():
                continue
            for seed in SEEDS:
                paired_rows.append(
                    _paired_solve(family, path, loader, limit, iters, live_op, seed)
                )

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_phase4_dev_comparison",
        "live_artifact": str(live_path.relative_to(ROOT)) if live_path.exists() else None,
        "live_gate": live_payload.get("gate"),
        "development_repair_arms": arms,
        "scripted_b0_b6": scripted,
        "paired_family_seeds": paired_rows,
        "note": (
            "Phase 4 framework under matched development budgets. "
            "A publication claim requires live_gate=beneficial with changed decisions."
        ),
        "research_claim_allowed": live_payload.get("gate") == "beneficial",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, "live_gate=", payload["live_gate"], flush=True)


if __name__ == "__main__":
    main()
