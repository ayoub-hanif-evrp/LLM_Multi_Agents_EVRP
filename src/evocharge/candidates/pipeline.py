"""Candidate generation, verification, and artifact storage (Milestone 7)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from evocharge.agents.coding import (
    SAFE_PLAN_EXAMPLE,
    SAFE_SCORE_EXAMPLE,
    CodingAgentResponse,
    build_coding_request,
    run_coding_agent,
)
from evocharge.agents.model_config import AgentsConfig
from evocharge.agents.ollama_client import LLMBackend, MockBackend, OllamaBackend, ReplayBackend
from evocharge.agents.schemas import AlgorithmicHypothesis, ScientistReport
from evocharge.operators.generated_api import API_VERSION, OperatorPlan
from evocharge.operators.primitives import catalogue_hash, write_catalogue_json
from evocharge.reproducibility import hash_mapping, sha256_text, source_state
from evocharge.verification.dynamic import run_dynamic_verification
from evocharge.verification.sandbox import run_in_sandbox
from evocharge.verification.static import extract_code_from_response, verify_source

CandidateStatus = Literal[
    "GENERATED",
    "STATIC_REJECTED",
    "STATIC_ACCEPTED",
    "DYNAMIC_REJECTED",
    "DYNAMIC_ACCEPTED",
    "INTEGRATION_REJECTED",
    "VERIFIED_CANDIDATE",
]


def assess_plan_nontriviality(plan: OperatorPlan | dict[str, Any] | None) -> dict[str, Any]:
    """Research-gate metrics: applicable plans with evidence, or valid no-action."""
    if plan is None:
        return {
            "nontrivial": False,
            "n_actions": 0,
            "plan_primitives": [],
            "uses_route_or_charging_primitive": False,
            "valid_no_action": False,
            "reason": "missing_plan",
        }
    if isinstance(plan, dict):
        plan = OperatorPlan.model_validate(plan)
    primitives = [a.primitive_id for a in plan.actions]
    route_charge = {
        "plan_charging_reconstruction",
        "plan_customer_removal",
        "plan_segment_removal",
        "plan_route_removal",
        "plan_station_removal",
        "plan_station_replacement",
        "plan_segment_relocation",
        "plan_customer_swap",
        "plan_greedy_reinsertion",
        "plan_regret_reinsertion",
    }
    uses = any(p in route_charge for p in primitives)
    nonempty = len(plan.actions) > 0
    valid_no_action = (
        (not plan.applicable)
        and (not plan.actions)
        and bool(plan.no_action_reason)
    )
    has_evidence = bool(plan.selection_evidence) and bool(plan.selected_entities)
    nontrivial = bool(
        valid_no_action
        or (plan.applicable and nonempty and uses and has_evidence)
    )
    reason = "ok"
    if not nontrivial:
        if not plan.applicable and not plan.no_action_reason:
            reason = "invalid_no_action"
        elif plan.applicable and not nonempty:
            reason = "empty_plan"
        elif plan.applicable and nonempty and not has_evidence:
            reason = "missing_selection_evidence"
        elif plan.applicable and nonempty and not uses:
            reason = "no_route_or_charging_primitive"
        else:
            reason = "not_nontrivial"
    return {
        "nontrivial": nontrivial,
        "n_actions": len(plan.actions),
        "plan_primitives": primitives,
        "uses_route_or_charging_primitive": uses,
        "valid_no_action": valid_no_action,
        "has_selection_evidence": has_evidence,
        "applicable": plan.applicable,
        "reason": reason,
    }


class CandidateStore:
    def __init__(self, root: Path, candidate_id: str) -> None:
        self.root = Path(root)
        self.candidate_id = candidate_id
        self.dir = self.root / candidate_id
        if self.dir.exists():
            raise FileExistsError(f"Candidate already exists (no overwrite): {self.dir}")
        self.dir.mkdir(parents=True, exist_ok=False)

    def write_json(self, name: str, payload: dict[str, Any]) -> None:
        path = self.dir / name
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def write_text(self, name: str, text: str) -> None:
        (self.dir / name).write_text(text, encoding="utf-8")


def _backend_from_config(config: AgentsConfig, model: str | None) -> LLMBackend:
    kind = config.backend.lower()
    if kind == "mock":
        return MockBackend()
    if kind == "replay":
        if not config.replay_dir:
            raise ValueError("replay backend requires replay_dir")
        return ReplayBackend(Path(config.replay_dir))
    backend = OllamaBackend(config.ollama, model_override=model)
    return backend


def generate_candidate(
    *,
    project_root: Path,
    scientist_report: ScientistReport,
    hypothesis_id: str,
    config: AgentsConfig,
    backend: LLMBackend | None = None,
    model: str | None = None,
    operator_type: Literal["scoring", "plan_builder"] = "plan_builder",
    candidate_id: str | None = None,
    max_revisions: int = 2,
    artifacts_root: Path | None = None,
    require_nonempty_plan: bool | None = None,
    allow_noop_control: bool = False,
) -> dict[str, Any]:
    hyp = next(
        (h for h in scientist_report.hypotheses if h.hypothesis_id == hypothesis_id),
        None,
    )
    if hyp is None:
        raise ValueError(f"hypothesis_id not found: {hypothesis_id}")

    backend = backend or _backend_from_config(config, model)
    if model and isinstance(backend, OllamaBackend):
        backend.model = model

    if require_nonempty_plan is None:
        require_nonempty_plan = (
            isinstance(backend, OllamaBackend) and not allow_noop_control
        )

    cid = candidate_id or f"cand_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{hypothesis_id}"
    store = CandidateStore(
        Path(artifacts_root or (project_root / "artifacts" / "candidates")), cid
    )
    src_state = source_state(project_root)
    cat_hash = catalogue_hash()
    write_catalogue_json(store.dir / "primitive_catalogue.json")

    request = build_coding_request(hyp, operator_type=operator_type)
    store.write_json("request.json", request.model_dump())
    store.write_json("hypothesis.json", hyp.model_dump())
    store.write_json(
        "model.json",
        {
            "backend": config.backend,
            "model": getattr(backend, "model", config.ollama.model),
            "api_version": API_VERSION,
            "primitive_catalogue_hash": cat_hash,
        },
    )
    store.write_json(
        "lineage.json",
        {
            "scientist_report_hash": hash_mapping(scientist_report.model_dump()),
            "hypothesis_id": hypothesis_id,
            "parent_candidate": None,
            "primitive_catalogue_hash": cat_hash,
            "api_version": API_VERSION,
            "source_state": src_state.model_dump(),
            "prompt_hashes": [],
        },
    )

    feedback: list[str] = []
    status: CandidateStatus = "GENERATED"
    static_report: dict[str, Any] | None = None
    dynamic_report: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    source = ""
    revisions = 0

    while True:
        req = build_coding_request(
            hyp, operator_type=operator_type, revision_feedback=feedback
        )
        # Mock convenience: if MockBackend has no coder response, inject safe example
        if isinstance(backend, MockBackend) and "coder" not in backend.responses:
            meta = {
                "candidate_name": f"mock_{hypothesis_id}",
                "hypothesis_id": hypothesis_id,
                "operator_type": operator_type,
                "used_primitives": list(hyp.required_primitives)[:3],
                "preconditions": ["validator_available"],
                "postconditions": ["plan_or_scores_returned"],
                "invariants": list(hyp.invariants) or ["deterministic"],
                "expected_complexity": hyp.expected_complexity or "O(n)",
                "behavioral_description": hyp.proposed_mechanism,
                "test_intents": ["determinism", "sandbox"],
                "known_risks": ["may not improve objective"],
            }
            src = SAFE_PLAN_EXAMPLE if operator_type == "plan_builder" else SAFE_SCORE_EXAMPLE
            if operator_type == "plan_builder":
                from evocharge.operators.m9a_reference import REFERENCE_SOURCES

                key = {"H1": "h1", "H2": "h2", "H3": "h3"}.get(hypothesis_id)
                if key is None:
                    key = {
                        "composite": "h1",
                        "destroy": "h2",
                        "charging": "h3",
                    }.get(str(hyp.category), "h2")
                src = REFERENCE_SOURCES.get(key, SAFE_PLAN_EXAMPLE)
            backend.set_response(
                "coder",
                {"metadata": meta, "source_code": src},
            )

        result = run_coding_agent(
            backend, req, hyp, config, schema_retries_so_far=revisions
        )
        store.write_text("raw_response.txt", result.raw_text)
        store.write_json("call_record.json", result.call_record.model_dump())

        if result.parsed is None:
            if revisions < max_revisions:
                revisions += 1
                feedback = [result.schema_error or "invalid_json"]
                continue
            status = "STATIC_REJECTED"
            model_name = getattr(backend, "model", None)
            summary = _summary(cid, status, revisions, None, None, model=model_name)
            store.write_json("summary.json", summary)
            return summary

        try:
            parsed = CodingAgentResponse.model_validate(result.parsed)
        except ValidationError as exc:
            if revisions < max_revisions:
                revisions += 1
                feedback = [str(exc)]
                continue
            status = "STATIC_REJECTED"
            model_name = getattr(backend, "model", None)
            summary = _summary(cid, status, revisions, None, None, model=model_name)
            store.write_json("summary.json", summary)
            return summary

        metadata = parsed.metadata.model_dump()
        source = extract_code_from_response(parsed.source_code)
        store.write_json("metadata.json", metadata)
        store.write_text("source.py", source)
        store.write_json(
            "source_hash.json",
            {"sha256": sha256_text(source), "bytes": len(source.encode("utf-8"))},
        )

        static = verify_source(
            source,
            expected_type=operator_type,
            allowed_primitives=set(request.allowed_primitives) or None,
        )
        static_report = static.model_dump()
        store.write_json("static_verification.json", static_report)
        if not static.accepted:
            if revisions < max_revisions:
                revisions += 1
                feedback = static.errors
                status = "STATIC_REJECTED"
                continue
            status = "STATIC_REJECTED"
            summary = _summary(
                cid, status, revisions, static_report, None, model=getattr(backend, "model", None)
            )
            store.write_json("summary.json", summary)
            return summary

        status = "STATIC_ACCEPTED"
        dynamic = run_dynamic_verification(source, operator_type=operator_type)
        dynamic_report = dynamic.model_dump()
        store.write_json("dynamic_verification.json", dynamic_report)
        if not dynamic.accepted:
            if revisions < max_revisions:
                revisions += 1
                feedback = dynamic.errors
                status = "DYNAMIC_REJECTED"
                continue
            status = "DYNAMIC_REJECTED"
            summary = _summary(
                cid,
                status,
                revisions,
                static_report,
                dynamic_report,
                model=getattr(backend, "model", None),
            )
            store.write_json("summary.json", summary)
            return summary

        nontrivial: dict[str, Any] = {
            "nontrivial": operator_type != "plan_builder",
            "reason": "scoring_operator",
        }
        if operator_type == "plan_builder":
            sand = run_in_sandbox(source, operator_type="plan_builder", seed=7)
            nontrivial = assess_plan_nontriviality(sand.get("plan") if sand.get("ok") else None)
            store.write_json("nontriviality.json", nontrivial)
            if require_nonempty_plan and not nontrivial.get("nontrivial"):
                if revisions < max_revisions:
                    revisions += 1
                    feedback = [
                        "nonempty_operator_plan_required: include at least one "
                        "plan_* route/charging action from allowed_primitives"
                    ]
                    continue
                status = "DYNAMIC_REJECTED"
                dynamic_report = {
                    **dynamic_report,
                    "nontriviality": nontrivial,
                    "errors": list(dynamic_report.get("errors") or [])
                    + ["trivial_or_empty_plan"],
                }
                store.write_json("dynamic_verification.json", dynamic_report)
                summary = _summary(
                    cid,
                    status,
                    revisions,
                    static_report,
                    dynamic_report,
                    model=getattr(backend, "model", None),
                    metadata=metadata,
                    nontriviality=nontrivial,
                )
                store.write_json("summary.json", summary)
                return summary

        status = "DYNAMIC_ACCEPTED"
        summary = _summary(
            cid,
            status,
            revisions,
            static_report,
            dynamic_report,
            model=getattr(backend, "model", None),
            metadata=metadata,
            nontriviality=nontrivial,
            schema_retries=int(
                getattr(result.call_record, "schema_retries", revisions) or revisions
            ),
        )
        store.write_json("summary.json", summary)
        store.write_json(
            "integration_results.json",
            {
                "status": "not_run",
                "note": "Use evocharge candidate integration-test for VERIFIED_CANDIDATE",
            },
        )
        return summary


def _summary(
    cid: str,
    status: str,
    revisions: int,
    static_report: dict[str, Any] | None,
    dynamic_report: dict[str, Any] | None,
    *,
    model: str | None,
    metadata: dict[str, Any] | None = None,
    nontriviality: dict[str, Any] | None = None,
    schema_retries: int | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": cid,
        "status": status,
        "revisions": revisions,
        "schema_retries": schema_retries if schema_retries is not None else revisions,
        "model": model,
        "static_accepted": bool(static_report and static_report.get("accepted")),
        "dynamic_accepted": bool(dynamic_report and dynamic_report.get("accepted")),
        "metadata": metadata,
        "nontriviality": nontriviality,
        "code_generated": True,
        "auto_promoted": False,
        "optimization_claim": False,
    }

def load_hypothesis_from_scientist_report(
    path: Path, hypothesis_id: str
) -> tuple[ScientistReport, AlgorithmicHypothesis]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    report = ScientistReport.model_validate(raw)
    hyp = next((h for h in report.hypotheses if h.hypothesis_id == hypothesis_id), None)
    if hyp is None:
        raise ValueError(f"hypothesis_id not found: {hypothesis_id}")
    return report, hyp
