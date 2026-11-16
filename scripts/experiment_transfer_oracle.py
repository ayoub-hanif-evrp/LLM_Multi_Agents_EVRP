"""EXPERIMENT 4 diagnostic — freeze a beneficial handcrafted oracle and test transfer.

This is NOT an LLM-discovered operator. It answers whether a policy that wins on
development Schneider also helps/harms other families under selective vs always-on use.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate, is_better
from evrptw_autolab.discovery.controller import operator_fingerprint
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "research" / "transfer_oracle.json"

SEEDS = (7, 11, 22)
CASES = (
    ("schneider", "c101C5", ROOT / "dataset/schneider/raw_instances/c101C5.txt", load_schneider_v2, 5.0, 20),
    ("schneider", "c101_21", ROOT / "dataset/schneider/raw_instances/c101_21.txt", load_schneider_v2, 10.0, 24),
    ("hiermann", "c101_21", ROOT / "dataset/hiermann-et-al-2017-set-1/c101_21.txt", load_hiermann, 8.0, 10),
    ("montoya", "tc0c10s2cf1", ROOT / "dataset/montoya-et-al-2017/tc0c10s2cf1.xml", load_montoya, 8.0, 16),
    ("goeke", "c101C6", ROOT / "dataset/goeke-2018/c101C6.txt", load_goeke, 6.0, 12),
)


def _op(rule: str) -> OperatorSpec:
    operator = OperatorSpec(
        operator_id="oracle_short",
        version="1",
        source_agent="handcrafted_oracle",
        description="delta_distance",
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        candidate_scoring_policy="delta_distance",
        applicability_rule=rule,
        mine_counterexamples=False,
        fallback_operator="classical_default",
    )
    return operator.model_copy(update={"source_hash": operator_fingerprint(operator)})


def _outcome(c_rep, p_rep) -> str:
    if c_rep.feasible and not p_rep.feasible:
        return "feasibility_regression"
    if is_better(p_rep, c_rep):
        return "improved"
    if is_better(c_rep, p_rep):
        return "objective_regression"
    return "tie"


def main() -> None:
    modes = {
        "always_on": _op("1"),
        "selective_high_util": _op("route_utilization - 0.5"),
        "classical_fallback": None,  # explicit classical reference arm
    }
    rows = []
    for mode, operator in modes.items():
        for family, instance_id, path, loader, limit, iters in CASES:
            if not path.exists():
                continue
            spec = loader(path)
            for seed in SEEDS:
                classical = solve_classical(
                    spec,
                    seed=seed,
                    time_limit_s=limit,
                    alns_iterations=iters,
                    hard_timeout=False,
                    experiment_partition="development",
                    policy=None,
                )
                if operator is None:
                    candidate = classical
                else:
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
                rows.append(
                    {
                        "mode": mode,
                        "family": family,
                        "instance_id": instance_id,
                        "seed": seed,
                        "outcome": _outcome(c_rep, p_rep),
                        "classical_objective_key": [float(v) for v in c_rep.objective_key],
                        "candidate_objective_key": [float(v) for v in p_rep.objective_key],
                        "changed_decisions": int(candidate.metadata.get("changed_decisions") or 0),
                        "policy_executed": bool(candidate.metadata.get("policy_executed")),
                    }
                )
                print(mode, family, instance_id, seed, rows[-1]["outcome"], flush=True)
    summary = {}
    by_instance = {}
    for row in rows:
        key = f"{row['mode']}/{row['family']}"
        summary.setdefault(
            key, {"improved": 0, "tie": 0, "objective_regression": 0, "feasibility_regression": 0}
        )
        summary[key][row["outcome"]] = summary[key].get(row["outcome"], 0) + 1
        ikey = f"{row['mode']}/{row['family']}/{row['instance_id']}"
        by_instance.setdefault(
            ikey, {"improved": 0, "tie": 0, "objective_regression": 0, "feasibility_regression": 0}
        )
        by_instance[ikey][row["outcome"]] = by_instance[ikey].get(row["outcome"], 0) + 1
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_transfer_oracle_v1",
        "operator": modes["always_on"].model_dump(),
        "note": (
            "Handcrafted oracle frozen from development wins. Not LLM-discovered. "
            "Modes: always_on, selective_high_util, classical_fallback."
        ),
        "rows": rows,
        "summary": summary,
        "summary_by_instance": by_instance,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
