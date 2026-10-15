"""Multi-agent component synthesis on the classical backbone.

Cheap by default. Does not start multi-hour campaigns. Uses FakeBackend in tests.
"""
from __future__ import annotations

import hashlib
import json
import logging
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
logger = logging.getLogger(__name__)

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


def _source_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()[:16]


def _extract_code(payload: dict[str, Any], kind: ComponentKind) -> tuple[str, str]:
    """Return (code, extraction_status)."""
    code = str(payload.get("code") or "")
    if f"def {kind}" not in code:
        recovered = extract_python_source(code) if code else ""
        if f"def {kind}" in recovered:
            return recovered, "recovered_from_markdown"
        return DEFAULT_SOURCES[kind], "fallback_missing_def"
    return code, "ok"


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
    llm_tokens = 0
    work = work_dir or (ROOT / "workspace" / "components" / f"seed{seed}")
    work.mkdir(parents=True, exist_ok=True)

    plan_raw = _call_json(
        backend,
        role="architect",
        prompt=_prompt("architect") + f"\n\nVariant family={spec.family} caps={spec.capabilities}",
        model=model,
    )
    llm_calls += 1
    llm_tokens += int(getattr(backend, "last_tokens", 0) or 0)
    plan = AlgorithmPlan.model_validate(plan_raw)
    wanted: list[ComponentKind] = list(plan.components) or [
        "insertion_score",
        "station_score",
        "removal_priority",
    ]

    sources: dict[ComponentKind, str] = {}
    owners: dict[ComponentKind, str] = {}
    provenance: list[dict[str, Any]] = [{"role": "architect", "plan": plan.model_dump()}]
    component_attribution: list[dict[str, Any]] = []

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
        llm_tokens += int(getattr(backend, "last_tokens", 0) or 0)
        generated_raw = str(payload.get("code") or "")
        fallback_reason = ""
        llm_generated = True
        try:
            proposal = ComponentProposal.model_validate({**payload, "component": kind, "owner_role": role})
            code, extract_status = _extract_code(proposal.model_dump(), kind)
            if extract_status.startswith("fallback"):
                fallback_reason = extract_status
                llm_generated = False
                logger.warning(
                    "component %s: replacing invalid/missing LLM code with DEFAULT_SOURCES (%s)",
                    kind,
                    extract_status,
                )
        except Exception as error:  # noqa: BLE001
            code = DEFAULT_SOURCES[kind]
            extract_status = "fallback_parse_error"
            fallback_reason = f"parse_error:{error}"
            llm_generated = False
            proposal = ComponentProposal(
                component=kind, owner_role=role, code=code, rationale="fallback_default"
            )
            logger.warning("component %s: parse failed; using DEFAULT_SOURCES (%s)", kind, error)
        check = validate_component_source(kind, code)
        if not check.get("ok"):
            logger.warning(
                "component %s: validation failed (%s); using DEFAULT_SOURCES",
                kind,
                check.get("detail"),
            )
            fallback_reason = f"validation:{check.get('detail')}"
            code = DEFAULT_SOURCES[kind]
            llm_generated = False
            check = validate_component_source(kind, code)
        sources[kind] = code
        owners[kind] = role
        attr = {
            "role": role,
            "component": kind,
            "model": model,
            "generated_code": generated_raw,
            "extract_status": extract_status,
            "validation_ok": bool(check.get("ok")),
            "validation_detail": check.get("detail"),
            "fallback_reason": fallback_reason,
            "fallback_used": bool(fallback_reason),
            "llm_generated": llm_generated and not fallback_reason,
            "executed_source": code,
            "executed_source_hash": _source_hash(code),
            "is_default_heuristic": code.strip() == DEFAULT_SOURCES[kind].strip(),
        }
        component_attribution.append(attr)
        provenance.append(
            {
                "role": role,
                "component": kind,
                "valid": bool(check.get("ok")),
                "detail": check.get("detail"),
                "proposal": proposal.model_dump(),
                "attribution": attr,
            }
        )

    bundle, errors = load_bundle(sources, owners)
    write_bundle(bundle, work / "bundle")

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

    decision_raw = _call_json(
        backend,
        role="critic",
        prompt=_prompt("critic") + f"\n\nFeedback:\n{feedback.model_dump_json()}",
        model=model,
    )
    llm_calls += 1
    llm_tokens += int(getattr(backend, "last_tokens", 0) or 0)
    try:
        decision = CandidateDecision.model_validate(decision_raw)
    except Exception:  # noqa: BLE001
        decision = CandidateDecision(
            verdict="ACCEPT" if report.feasible else "REVISE",
            reason="fallback",
            next_component="none",
        )

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
            llm_tokens += int(getattr(backend, "last_tokens", 0) or 0)
            code, extract_status = _extract_code(payload, kind)
            llm_generated = not extract_status.startswith("fallback")
            if validate_component_source(kind, code).get("ok") and llm_generated:
                sources[kind] = code
                owners[kind] = role
                component_attribution.append(
                    {
                        "role": role,
                        "component": kind,
                        "model": model,
                        "round": 2,
                        "extract_status": extract_status,
                        "llm_generated": True,
                        "executed_source_hash": _source_hash(code),
                        "fallback_used": False,
                        "is_default_heuristic": False,
                    }
                )
            else:
                logger.warning(
                    "revision for %s discarded (status=%s); keeping prior source",
                    kind,
                    extract_status,
                )
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

    final_verdict = decision.verdict
    if final_verdict == "ACCEPT" and not report.feasible:
        final_verdict = "REJECT"

    genuine_llm_components = sum(
        1 for a in component_attribution if a.get("llm_generated") and not a.get("is_default_heuristic")
    )

    result = {
        "experiment": "component_synthesis",
        "family": spec.family,
        "instance_id": spec.instance_id,
        "seed": seed,
        "model": model,
        "feasible": bool(report.feasible),
        "objective": report.objective,
        "objective_key": list(report.objective_key),
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "fault_family": feedback.fault_family,
        "detail": feedback.detail,
        "llm_calls": llm_calls,
        "llm_tokens": llm_tokens,
        "rounds": rounds,
        "critic_verdict": final_verdict,
        "load_errors": errors,
        "bundle_dir": str(work / "bundle"),
        "routes": [[s.node_id for s in route] for route in solution.routes],
        "wall_s": time.monotonic() - started,
        "provenance": provenance,
        "component_attribution": component_attribution,
        "genuine_llm_components": genuine_llm_components,
        "default_heuristic_count": sum(
            1 for a in component_attribution if a.get("is_default_heuristic")
        ),
        "plan": plan.model_dump(),
        "note": (
            "Human-authored classical backbone + LLM-generated scoring components. "
            "Evaluator alone decides feasibility. Default heuristics are never counted "
            "as successful LLM discoveries."
        ),
    }
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
