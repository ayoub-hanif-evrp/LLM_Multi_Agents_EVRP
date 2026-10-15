"""Multi-agent component synthesis on the classical backbone.

Cheap by default. Does not start multi-hour campaigns. Uses FakeBackend in tests.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal, cast

from evrptw_autolab.agents.base import extract_json, extract_python_source
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, SIGNATURES, ComponentKind
from evrptw_autolab.components.loader import load_bundle, validate_component_source, write_bundle
from evrptw_autolab.components.schemas import (
    AlgorithmPlan,
    CandidateDecision,
    ComponentProposal,
    ExperimentFeedback,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2

ROOT = Path(__file__).resolve().parents[3]
PROMPTS = ROOT / "prompts" / "components"

OwnerRole = Literal["architect", "routing", "charging", "search", "critic"]

ROLE_FOR: dict[ComponentKind, OwnerRole] = {
    "insertion_score": "routing",
    "station_score": "charging",
    "removal_priority": "search",
}


def _prompt(name: str) -> str:
    path = PROMPTS / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _call_json(backend: Any, *, role: str, prompt: str, model: str, temperature: float = 0.2) -> dict[str, Any]:
    raw = backend.complete(prompt=prompt, role=role, temperature=temperature, model=model, json_mode=True)
    return extract_json(raw)


def _extract_code(payload: dict[str, Any], kind: ComponentKind) -> str:
    code = str(payload.get("code") or "")
    if f"def {kind}" not in code:
        # Sometimes models wrap code in markdown inside JSON string.
        recovered = extract_python_source(code) if code else ""
        if f"def {kind}" in recovered:
            return recovered
        return DEFAULT_SOURCES[kind]
    return code


def synthesize_components(
    spec: ProblemSpecV2,
    backend: Any,
    *,
    model: str = "fake",
    seed: int = 0,
    time_limit_s: float = 3.0,
    max_rounds: int = 2,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Run five-role component synthesis and evaluate with the classical backbone."""
    started = time.monotonic()
    llm_calls = 0
    work = work_dir or (ROOT / "workspace" / "components" / f"seed{seed}")
    work.mkdir(parents=True, exist_ok=True)

    # 1) Architect plan
    plan_raw = _call_json(
        backend,
        role="architect",
        prompt=_prompt("architect") + f"\n\nVariant family={spec.family} caps={spec.capabilities}",
        model=model,
    )
    llm_calls += 1
    plan = AlgorithmPlan.model_validate(plan_raw)
    wanted: list[ComponentKind] = list(plan.components) or [
        "insertion_score",
        "station_score",
        "removal_priority",
    ]

    sources: dict[ComponentKind, str] = {}
    owners: dict[ComponentKind, str] = {}
    provenance: list[dict[str, Any]] = [{"role": "architect", "plan": plan.model_dump()}]

    # 2) Generate each component via its owning role
    for kind in wanted:
        role = ROLE_FOR[kind]
        prompt_name = {"routing": "routing", "charging": "charging", "search": "search"}[role]
        payload = _call_json(
            backend,
            role=role,
            prompt=_prompt(prompt_name) + f"\n\nSignature:\n{SIGNATURES[kind]}",
            model=model,
        )
        llm_calls += 1
        try:
            proposal = ComponentProposal.model_validate({**payload, "component": kind, "owner_role": role})
            code = _extract_code(proposal.model_dump(), kind)
        except Exception:  # noqa: BLE001
            code = DEFAULT_SOURCES[kind]
            proposal = ComponentProposal(
                component=kind, owner_role=role, code=code, rationale="fallback_default"
            )
        check = validate_component_source(kind, code)
        if not check.get("ok"):
            # One repair attempt with default if invalid.
            code = DEFAULT_SOURCES[kind]
            check = validate_component_source(kind, code)
        sources[kind] = code
        owners[kind] = role
        provenance.append(
            {
                "role": role,
                "component": kind,
                "valid": bool(check.get("ok")),
                "detail": check.get("detail"),
                "proposal": proposal.model_dump(),
            }
        )

    bundle, errors = load_bundle(sources, owners)
    write_bundle(bundle, work / "bundle")

    # 3) Solve with classical backbone + policies
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=40,
        policy=bundle,
    )
    report = evaluate(spec, solution)

    feedback = ExperimentFeedback(
        feasible=bool(report.feasible),
        objective=report.objective,
        vehicles=report.vehicles,
        distance=report.total_distance,
        fault_family=(report.first_fault.family if report.first_fault else ""),
        detail=(report.first_fault.detail if report.first_fault else ""),
        llm_calls=llm_calls,
    )

    # 4) Critic decision (does not override evaluator)
    decision_raw = _call_json(
        backend,
        role="critic",
        prompt=_prompt("critic") + f"\n\nFeedback:\n{feedback.model_dump_json()}",
        model=model,
    )
    llm_calls += 1
    try:
        decision = CandidateDecision.model_validate(decision_raw)
    except Exception:  # noqa: BLE001
        decision = CandidateDecision(
            verdict="ACCEPT" if report.feasible else "REVISE",
            reason="fallback",
            next_component="none",
        )

    # Optional single revision round if critic asks and not feasible.
    rounds = 1
    if not report.feasible and decision.verdict == "REVISE" and max_rounds > 1:
        rounds = 2
        target = decision.next_component
        if target in ROLE_FOR:
            kind = cast(ComponentKind, target)
            role = ROLE_FOR[kind]
            prompt_name = {"routing": "routing", "charging": "charging", "search": "search"}[role]
            payload = _call_json(
                backend,
                role=role,
                prompt=(
                    _prompt(prompt_name)
                    + f"\n\nPrevious failed. Fault={feedback.fault_family}: {feedback.detail}\n"
                    + f"Signature:\n{SIGNATURES[kind]}"
                ),
                model=model,
            )
            llm_calls += 1
            code = _extract_code(payload, kind)
            if validate_component_source(kind, code).get("ok"):
                sources[kind] = code
                owners[kind] = role
            bundle, errors = load_bundle(sources, owners)
            write_bundle(bundle, work / "bundle")
            solution = solve_classical(
                spec, seed=seed, time_limit_s=time_limit_s, alns_iterations=40, policy=bundle
            )
            report = evaluate(spec, solution)
            feedback = ExperimentFeedback(
                feasible=bool(report.feasible),
                objective=report.objective,
                vehicles=report.vehicles,
                distance=report.total_distance,
                fault_family=(report.first_fault.family if report.first_fault else ""),
                detail=(report.first_fault.detail if report.first_fault else ""),
                llm_calls=llm_calls,
            )

    # Critic cannot accept an infeasible evaluator result.
    final_verdict = decision.verdict
    if final_verdict == "ACCEPT" and not report.feasible:
        final_verdict = "REJECT"

    result = {
        "experiment": "component_synthesis",
        "family": spec.family,
        "instance_id": spec.instance_id,
        "seed": seed,
        "feasible": bool(report.feasible),
        "objective": report.objective,
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "fault_family": feedback.fault_family,
        "detail": feedback.detail,
        "llm_calls": llm_calls,
        "rounds": rounds,
        "critic_verdict": final_verdict,
        "load_errors": errors,
        "bundle_dir": str(work / "bundle"),
        "routes": [[s.node_id for s in route] for route in solution.routes],
        "wall_s": time.monotonic() - started,
        "provenance": provenance,
        "plan": plan.model_dump(),
        "note": (
            "Human-authored classical backbone + LLM-generated scoring components. "
            "Evaluator alone decides feasibility."
        ),
    }
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
