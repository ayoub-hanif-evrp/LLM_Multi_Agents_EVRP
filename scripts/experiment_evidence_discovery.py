"""EXPERIMENT 2–3 — evidence-guided live discovery + matched controls.

Uses headroom-audit training evidence. Does not reject operators that tie on the
synthetic four-node case. Budgets are predeclared and fail-closed.
"""

from __future__ import annotations

import json
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate, is_better
from evrptw_autolab.discovery.controller import (
    APPLICABILITY_FEATURES,
    REPAIR_INSERTION_FEATURES,
    SCORING_FEATURES,
    CallBudget,
    admit,
    normalize_operator_expressions,
    operator_fingerprint,
)
from evrptw_autolab.discovery.messages import Critique, Hypothesis, validate_hypothesis
from evrptw_autolab.discovery.policy_language import validate_expression
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.llm.registry import availability, make_backend, resolve_profile
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.research.panel import development_case

ROOT = Path(__file__).resolve().parents[1]
HEADROOM = ROOT / "results" / "cipher" / "research" / "headroom_audit.json"
OUT = ROOT / "results" / "cipher" / "research" / "evidence_discovery.json"

MODEL_ID = "qwen25_coder_14b"
MAX_PROPOSALS = 3
CALLS_PER_PROPOSAL = 3  # architect + specialist + optional critic
EVAL_SEEDS = (7, 11, 22)
DEV_CASES = (
    ("schneider", "c101C5", ROOT / "dataset/schneider/raw_instances/c101C5.txt", load_schneider_v2, 5.0, 20),
    ("schneider", "c101_21", ROOT / "dataset/schneider/raw_instances/c101_21.txt", load_schneider_v2, 10.0, 24),
    ("hiermann", "c101_21", ROOT / "dataset/hiermann-et-al-2017-set-1/c101_21.txt", load_hiermann, 8.0, 10),
)

HANDCRAFTED = (
    ("handcrafted_short", "delta_distance", "1"),
    ("handcrafted_long", "-1 * delta_distance", "1"),
    ("handcrafted_downstream_proxy", "delta_distance - 0.01 * battery_margin", "1"),
)
RANDOM_POOL = (
    "delta_distance",
    "delta_travel_time",
    "delta_distance + incremental_energy_cost",
    "route_customer_count + delta_distance",
    "-1 * battery_margin + delta_distance",
    "delta_travel_time - 0.1 * battery_margin",
)


def _parse_json_object(text: str) -> dict[str, Any]:
    blob = text.strip()
    if blob.startswith("```"):
        lines = blob.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        blob = "\n".join(lines).strip()
    # Prefer the largest balanced {...} object.
    start = blob.find("{")
    end = blob.rfind("}")
    if start >= 0 and end > start:
        blob = blob[start : end + 1]
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        # Common model damage: trailing commas / single quotes.
        repaired = blob.replace("'", '"')
        repaired = repaired.replace(",}", "}").replace(",]", "]")
        payload = json.loads(repaired)
    if not isinstance(payload, dict):
        raise ValueError("model reply is not a JSON object")
    return payload


def _evidence_blob(examples: list[dict[str, Any]], limit: int = 8) -> str:
    compact = []
    for ex in examples[:limit]:
        compact.append(
            {
                "family": ex["family"],
                "instance": ex["instance_id"],
                "classical_features": ex["classical_features"],
                "classical_acceptance": ex["classical_acceptance"],
                "classical_final_objective": ex["classical_objective_key"],
                "better_features": ex["better_features"],
                "better_acceptance": ex["better_acceptance"],
                "better_final_objective": ex["better_objective_key"],
            }
        )
    return json.dumps(compact, indent=2)


def _architect_prompt(evidence: str) -> str:
    return (
        "Return ONE compact JSON object only (no markdown) with keys: hypothesis, "
        "target_bottleneck, affected_capabilities, proposed_operator_id, "
        "expected_useful_conditions, expected_failure_conditions, measurable_prediction. "
        "affected_capabilities must be a JSON array of CapabilityFlags names such as "
        "[\"time_windows\"]. Hypothesis must concern DOWNSTREAM vehicle/distance quality, "
        "not only immediate insertion cost. Keep every string short. Evidence (measured):\n"
        f"{evidence}"
    )


def _specialist_prompt(hypothesis: Hypothesis, evidence: str) -> str:
    scoring = ", ".join(sorted(REPAIR_INSERTION_FEATURES))
    return (
        "Return ONE compact JSON object only (no markdown) with exactly these keys: "
        "operator_id, version, source_agent, description, operator_family, "
        "implementation_reference, required_capabilities, forbidden_capabilities, "
        "required_features, hard_preconditions, candidate_scoring_policy, "
        "applicability_rule, fallback_operator. "
        "Set operator_family=\"repair\", implementation_reference=\"repair_greedy\", "
        "fallback_operator=\"classical_default\", applicability_rule=\"1\", "
        "required_capabilities=[\"time_windows\"], forbidden_capabilities=[], "
        "required_features=[], hard_preconditions=[]. "
        f"candidate_scoring_policy must be a SHORT arithmetic string over ONLY: {scoring}. "
        "Lower scores are preferred. Example forms: \"delta_distance - 0.2 * battery_margin\". "
        "Do not nest objects for scoring. Hypothesis: "
        f"{hypothesis.hypothesis}. Evidence: {evidence}"
    )


def _critic_prompt(hypothesis: Hypothesis, operator: OperatorSpec, evidence: str, decision: dict[str, Any]) -> str:
    scoring = ", ".join(sorted(REPAIR_INSERTION_FEATURES))
    return (
        "Return ONE compact JSON object only (no markdown) with keys: what_failed, "
        "operator_should_change, applicability_should_change, scoring_should_change, "
        "evidence_too_weak, revised_applicability_rule, revised_candidate_scoring_policy. "
        "Revise at most once. Prefer applicability_rule \"1\". "
        f"revised_candidate_scoring_policy must be a short string over: {scoring}. "
        f"Current scoring={operator.candidate_scoring_policy}. "
        f"Decision={json.dumps(decision)}. Evidence={evidence}"
    )


def _op(operator_id: str, scoring: str, rule: str = "1") -> OperatorSpec:
    operator = OperatorSpec(
        operator_id=operator_id,
        version="1",
        source_agent="experiment",
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


def _paired_outcome(classical, candidate) -> str:
    if classical.feasible and not candidate.feasible:
        return "feasibility_regression"
    if is_better(candidate, classical):
        return "improved"
    if is_better(classical, candidate):
        return "objective_regression"
    return "tie"


def _evaluate_operator(name: str, operator: OperatorSpec | None) -> dict[str, Any]:
    paired = []
    for family, instance_id, path, loader, limit, iters in DEV_CASES:
        if not path.exists():
            continue
        spec = loader(path)
        for seed in EVAL_SEEDS:
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
            paired.append(
                {
                    "family": family,
                    "instance_id": instance_id,
                    "seed": seed,
                    "outcome": _paired_outcome(c_rep, p_rep),
                    "classical_objective_key": [float(v) for v in c_rep.objective_key],
                    "candidate_objective_key": [float(v) for v in p_rep.objective_key],
                    "classical_feasible": bool(c_rep.feasible),
                    "candidate_feasible": bool(p_rep.feasible),
                    "changed_decisions": int(candidate.metadata.get("changed_decisions") or 0),
                    "policy_executed": bool(candidate.metadata.get("policy_executed")),
                }
            )
    outcomes = [r["outcome"] for r in paired]
    changed = sum(int(r["changed_decisions"]) for r in paired)
    from evrptw_autolab.research.gates import paired_gate

    origin = "handcrafted"
    lower = name.lower()
    if "llm" in lower or "multi" in lower or lower.startswith("single"):
        origin = "llm"
    elif "random" in lower:
        origin = "random"
    elif lower.startswith("classical"):
        origin = "classical"
    gate_info = paired_gate(outcomes, changed_decisions_total=changed, policy_origin=origin)
    return {
        "name": name,
        "operator": None if operator is None else operator.model_dump(),
        "gate": gate_info["quality_gate"],
        "wins": gate_info["wins"],
        "ties": gate_info["ties"],
        "losses": gate_info["losses"],
        "changed_decisions_total": changed,
        "signals": gate_info,
        "paired": paired,
    }


def _discover_one(
    backend: Any,
    evidence: str,
    *,
    proposal_index: int,
    budget: CallBudget,
) -> dict[str, Any]:
    from evrptw_autolab.backbone.alns import repair_greedy

    spec, solution, removed = development_case()
    try:
        hypothesis = Hypothesis.model_validate(
            _parse_json_object(budget.charge(backend, "architect", _architect_prompt(evidence)))
        )
        validate_hypothesis(hypothesis)
        payload = _coerce_operator_payload(
            _parse_json_object(
                budget.charge(backend, "routing_specialist", _specialist_prompt(hypothesis, evidence))
            )
        )
        proposed = OperatorSpec.model_validate(payload)
        seen: set[str] = set()
        digest = admit(proposed, seen, spec.capabilities)
        operator = normalize_operator_expressions(proposed).model_copy(
            update={"source_hash": digest, "mine_counterexamples": False}
        )
        repaired = repair_greedy(
            spec, solution, removed, random.Random(1 + proposal_index), operator, partition="development"
        )
        decision = repaired.metadata.get("search_decision") or {}
        critique = Critique.model_validate(
            _parse_json_object(
                budget.charge(
                    backend,
                    "critic",
                    _critic_prompt(hypothesis, operator, evidence, decision if isinstance(decision, dict) else {}),
                )
            )
        )
        revised_parts: list[str] = []
        updates: dict[str, Any] = {}
        if (
            not critique.evidence_too_weak
            and critique.applicability_should_change
            and critique.revised_applicability_rule
        ):
            updates["applicability_rule"] = validate_expression(
                critique.revised_applicability_rule, APPLICABILITY_FEATURES | SCORING_FEATURES
            )
            revised_parts.append("applicability_rule")
        if (
            not critique.evidence_too_weak
            and critique.scoring_should_change
            and critique.revised_candidate_scoring_policy
        ):
            updates["candidate_scoring_policy"] = validate_expression(
                critique.revised_candidate_scoring_policy, SCORING_FEATURES | APPLICABILITY_FEATURES
            )
            revised_parts.append("candidate_scoring_policy")
        if updates:
            updates["version"] = f"{operator.version}.1"
            candidate = operator.model_copy(update=updates)
            digest2 = operator_fingerprint(candidate)
            if digest2 not in seen:
                seen.add(digest2)
                operator = candidate.model_copy(update={"source_hash": digest2})
        return {
            "status": "ok",
            "proposal_index": proposal_index,
            "hypothesis": hypothesis.model_dump(),
            "operator": operator.model_dump(),
            "critique": critique.model_dump(),
            "critic_revised_parts": revised_parts,
            "synthetic_decision": decision,
            "llm_calls": budget.used,
            "prompt_tokens": budget.prompt_tokens,
            "completion_tokens": budget.completion_tokens,
        }
    except Exception as exc:  # noqa: BLE001 — preserve failed proposals
        return {
            "status": "failed",
            "proposal_index": proposal_index,
            "error": f"{type(exc).__name__}: {exc}",
            "llm_calls": budget.used,
            "prompt_tokens": budget.prompt_tokens,
            "completion_tokens": budget.completion_tokens,
        }


def _coerce_operator_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "operator_spec" in payload and isinstance(payload["operator_spec"], dict):
        payload = payload["operator_spec"]
    elif "operator" in payload and isinstance(payload["operator"], dict):
        payload = payload["operator"]
    scoring = payload.get("candidate_scoring_policy")
    if isinstance(scoring, dict):
        # Model sometimes returns feature weights; convert to a linear expression.
        terms = [f"({float(weight)} * {name})" for name, weight in scoring.items() if name in REPAIR_INSERTION_FEATURES]
        payload["candidate_scoring_policy"] = " + ".join(terms) if terms else "delta_distance"
    payload.setdefault("operator_id", "llm_repair")
    payload.setdefault("version", "1")
    payload.setdefault("source_agent", "llm")
    payload.setdefault("description", str(payload.get("candidate_scoring_policy") or "repair"))
    payload["operator_family"] = "repair"
    payload["implementation_reference"] = "repair_greedy"
    payload["required_capabilities"] = ["time_windows"]
    payload["forbidden_capabilities"] = []
    payload["required_features"] = []
    payload["hard_preconditions"] = []
    payload["applicability_rule"] = payload.get("applicability_rule") or "1"
    if payload["applicability_rule"] in {"true", "True"}:
        payload["applicability_rule"] = "1"
    payload["fallback_operator"] = "classical_default"
    payload["mine_counterexamples"] = False
    return payload


def _single_llm_proposal(backend: Any, evidence: str, budget: CallBudget) -> dict[str, Any]:
    """One-shot specialist-only baseline with matched remaining call budget of 1."""
    scoring = ", ".join(sorted(REPAIR_INSERTION_FEATURES))
    prompt = (
        "Return ONE compact JSON object only (no markdown) with keys operator_id, version, "
        "source_agent, description, operator_family, implementation_reference, "
        "required_capabilities, forbidden_capabilities, required_features, hard_preconditions, "
        "candidate_scoring_policy, applicability_rule, fallback_operator. "
        "operator_family=\"repair\"; implementation_reference=\"repair_greedy\"; "
        "required_capabilities=[\"time_windows\"]; applicability_rule=\"1\"; "
        "fallback_operator=\"classical_default\". "
        f"candidate_scoring_policy must be a SHORT string over ONLY: {scoring}. "
        f"Use this downstream evidence: {evidence}"
    )
    try:
        payload = _coerce_operator_payload(
            _parse_json_object(budget.charge(backend, "routing_specialist", prompt))
        )
        proposed = OperatorSpec.model_validate(payload)
        digest = admit(proposed, set(), development_case()[0].capabilities)
        operator = normalize_operator_expressions(proposed).model_copy(update={"source_hash": digest})
        return {"status": "ok", "operator": operator.model_dump(), "llm_calls": budget.used}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}", "llm_calls": budget.used}


def main() -> None:
    started = time.perf_counter()
    headroom = json.loads(HEADROOM.read_text(encoding="utf-8"))
    evidence_rows = list(headroom.get("training_evidence") or [])
    evidence = _evidence_blob(evidence_rows)
    profile = resolve_profile(MODEL_ID)
    status = availability(profile)
    if status != "installed":
        raise RuntimeError(f"model {MODEL_ID} not installed: {status}")
    backend = make_backend(profile)

    proposals = []
    total_calls = 0
    total_prompt = 0
    total_completion = 0
    for i in range(MAX_PROPOSALS):
        budget = CallBudget(CALLS_PER_PROPOSAL, model=profile.model, max_tokens=12_000, wall_s=600.0)
        result = _discover_one(backend, evidence, proposal_index=i, budget=budget)
        proposals.append(result)
        total_calls += int(result.get("llm_calls") or 0)
        total_prompt += int(result.get("prompt_tokens") or 0)
        total_completion += int(result.get("completion_tokens") or 0)
        print("proposal", i, result.get("status"), result.get("error") or (result.get("operator") or {}).get("candidate_scoring_policy"), flush=True)

    # Matched single-LLM budget: one generation call (not 3 roles × proposals).
    single_budget = CallBudget(1, model=profile.model, max_tokens=4_000, wall_s=300.0)
    single = _single_llm_proposal(backend, evidence, single_budget)
    total_calls += int(single.get("llm_calls") or 0)
    total_prompt += int(single_budget.prompt_tokens)
    total_completion += int(single_budget.completion_tokens)
    print("single_llm", single.get("status"), flush=True)

    evaluations = []
    evaluations.append(_evaluate_operator("classical", None))
    print("eval classical", evaluations[-1]["gate"], flush=True)

    for name, scoring, rule in HANDCRAFTED:
        evaluations.append(_evaluate_operator(name, _op(name, scoring, rule)))
        print("eval", name, evaluations[-1]["gate"], evaluations[-1]["wins"], "wins", flush=True)

    rng = random.Random(7)
    random_scoring = rng.choice(RANDOM_POOL)
    evaluations.append(_evaluate_operator("random_valid", _op("random_valid", random_scoring, "1")))
    evaluations[-1]["scoring"] = random_scoring
    print("eval random_valid", evaluations[-1]["gate"], flush=True)

    if single.get("status") == "ok":
        op = OperatorSpec.model_validate(single["operator"])
        evaluations.append(_evaluate_operator("single_llm", op))
        print("eval single_llm", evaluations[-1]["gate"], flush=True)

    multi_evals = []
    for prop in proposals:
        if prop.get("status") != "ok":
            continue
        op = OperatorSpec.model_validate(prop["operator"])
        ev = _evaluate_operator(f"multi_role_{prop['proposal_index']}", op)
        ev["proposal_index"] = prop["proposal_index"]
        multi_evals.append(ev)
        evaluations.append(ev)
        print("eval", ev["name"], ev["gate"], ev["wins"], "wins", flush=True)

    beneficial = [e for e in evaluations if e["gate"] == "beneficial"]
    payload = {
        "created_at": datetime.now(UTC).isoformat(),
        "protocol": "cipher_evidence_discovery_v1",
        "model_id": MODEL_ID,
        "model": profile.model,
        "model_digest": getattr(backend, "digest", None),
        "headroom_decision": headroom.get("decision"),
        "evidence_examples_used": min(8, len(evidence_rows)),
        "llm_budget": {
            "max_proposals": MAX_PROPOSALS,
            "calls_per_proposal": CALLS_PER_PROPOSAL,
            "total_calls": total_calls,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
        },
        "proposals": proposals,
        "single_llm_proposal": single,
        "evaluations": evaluations,
        "beneficial_operators": [e["name"] for e in beneficial],
        "wall_s": round(time.perf_counter() - started, 2),
        "research_signal": (
            "go"
            if beneficial
            else "no_beneficial_operator_under_budget"
        ),
        "note": (
            "Synthetic four-node unchanged decisions do not block paired development evaluation. "
            "Families are never averaged."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, "signal=", payload["research_signal"], flush=True)


if __name__ == "__main__":
    main()
