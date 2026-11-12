"""One capped live-operator signal on Schneider and Hiermann. Fail closed."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate, is_better
from evrptw_autolab.discovery.controller import (
    operator_fingerprint,
    run_live_cycle,
    run_scripted_cycle,
)
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.v2.report import EvaluationReportV2

ROOT = Path(__file__).resolve().parents[3]

CASES = (
    ("schneider", "c101C5", ROOT / "dataset" / "schneider" / "raw_instances" / "c101C5.txt", 5.0, 20, load_schneider_v2),
    ("hiermann", "c101_21", ROOT / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt", 8.0, 10, load_hiermann),
)
SEED = 7


def paired_outcome(
    classical: EvaluationReportV2,
    candidate: EvaluationReportV2,
) -> str:
    """Classify one family comparison. Families are never averaged together."""
    if classical.feasible and not candidate.feasible:
        return "feasibility_regression"
    if candidate.feasible and not classical.feasible:
        return "improved"
    if is_better(candidate, classical):
        return "improved"
    if is_better(classical, candidate):
        return "objective_regression"
    return "tie"


def run_signal(
    *,
    backend: str = "fake",
    model_id: str = "qwen25_coder_14b",
    max_calls: int = 4,
    destination: Path | None = None,
) -> dict[str, Any]:
    """Discover one operator, then compare classical vs policy on two development instances."""
    out = destination or (ROOT / "results" / "cipher" / "live_signal" / f"{backend}_signal.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if backend == "fake":
        discovery = run_scripted_cycle(max_calls=max_calls)
        discovery["backend"] = "fake"
        discovery["model_id"] = "fake"
    elif backend == "ollama":
        discovery = run_live_cycle(model_id=model_id, max_calls=max_calls)
    else:
        raise ValueError(f"unsupported backend {backend}")

    if discovery.get("error") or discovery.get("operator") is None:
        payload = {
            "created_at": datetime.now(UTC).isoformat(),
            "backend": discovery.get("backend", backend),
            "model_id": discovery.get("model_id", model_id),
            "llm_calls": int(discovery.get("llm_calls") or 0),
            "prompt_tokens": int(discovery.get("prompt_tokens") or 0),
            "completion_tokens": int(discovery.get("completion_tokens") or 0),
            "gate": "discovery_failed",
            "diagnosis": discovery.get("error") or "operator missing",
            "operator": None,
            "discovery_decision": discovery.get("decision") or {},
            "counterexamples": discovery.get("counterexamples") or [],
            "paired": [],
            "final_test": "No untouched final set is declared. Schneider RC2 is not a blind test.",
        }
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    operator = OperatorSpec.model_validate(discovery["operator"])
    if not operator.source_hash:
        operator = operator.model_copy(update={"source_hash": operator_fingerprint(operator)})
    operator = operator.model_copy(update={"mine_counterexamples": False})

    decision = discovery.get("decision") or {}
    gate = "ok"
    diagnosis = None
    if not decision:
        gate = "no_search_decision"
        diagnosis = "discovery produced no search_decision"
    elif not decision.get("changed") and not discovery.get("counterexamples"):
        gate = "behaviorally_inert"
        diagnosis = (
            f"operator did not change the development repair "
            f"(action={decision.get('action')}, reason={decision.get('reason')})"
        )

    paired: list[dict[str, Any]] = []
    if gate == "ok":
        for family, instance_id, path, time_limit, iterations, loader in CASES:
            spec = loader(path)
            classical = solve_classical(
                spec,
                seed=SEED,
                time_limit_s=time_limit,
                alns_iterations=iterations,
                hard_timeout=False,
                experiment_partition="development",
                policy=None,
            )
            candidate = solve_classical(
                spec,
                seed=SEED,
                time_limit_s=time_limit,
                alns_iterations=iterations,
                hard_timeout=False,
                experiment_partition="development",
                policy=operator,
            )
            classical_report = evaluate(spec, classical)
            candidate_report = evaluate(spec, candidate)
            outcome = paired_outcome(classical_report, candidate_report)
            paired.append(
                {
                    "family": family,
                    "instance_id": instance_id,
                    "seed": SEED,
                    "classical_feasible": bool(classical_report.feasible),
                    "candidate_feasible": bool(candidate_report.feasible),
                    "classical_objective_key": [float(v) for v in classical_report.objective_key],
                    "candidate_objective_key": [float(v) for v in candidate_report.objective_key],
                    "outcome": outcome,
                    "policy_executed": bool(candidate.metadata.get("policy_executed")),
                    "changed_decisions": int(candidate.metadata.get("changed_decisions") or 0),
                    "source_hash": candidate.metadata.get("source_hash"),
                    "method_attribution": candidate.metadata.get("method_attribution"),
                }
            )

        outcomes = [row["outcome"] for row in paired]
        changed_total = sum(int(row["changed_decisions"]) for row in paired)
        if "feasibility_regression" in outcomes:
            gate = "feasibility_regression"
            diagnosis = "candidate lost feasibility on a development instance"
        elif "objective_regression" in outcomes:
            gate = "objective_regression"
            worse = [row["family"] for row in paired if row["outcome"] == "objective_regression"]
            diagnosis = f"feasible but worse native objective on: {', '.join(worse)}"
        elif changed_total == 0 and all(outcome == "tie" for outcome in outcomes):
            gate = "behaviorally_inert"
            diagnosis = "paired solves matched classical with zero changed decisions"
        elif "improved" in outcomes:
            gate = "beneficial"
            improved = [row["family"] for row in paired if row["outcome"] == "improved"]
            diagnosis = f"native objective improved on: {', '.join(improved)}"
        else:
            gate = "no_improvement"
            diagnosis = "operator ran without native-objective improvement"

    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "backend": discovery.get("backend", backend),
        "model_id": discovery.get("model_id", model_id),
        "llm_calls": int(discovery.get("llm_calls") or 0),
        "prompt_tokens": int(discovery.get("prompt_tokens") or 0),
        "completion_tokens": int(discovery.get("completion_tokens") or 0),
        "gate": gate,
        "diagnosis": diagnosis,
        "operator": operator.model_dump(),
        "discovery_decision": decision,
        "counterexamples": discovery.get("counterexamples") or [],
        "paired": paired,
        "final_test": "No untouched final set is declared. Schneider RC2 is not a blind test.",
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload
