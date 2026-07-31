"""LLM-guided offspring generation for Milestone 10A attribution."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evocharge.agents.coding import (
    SAFE_PLAN_EXAMPLE,
    CodingAgentResponse,
    build_coding_request,
    run_coding_agent,
)
from evocharge.agents.model_config import AgentsConfig, OllamaConfig
from evocharge.agents.ollama_client import LLMBackend, MockBackend, OllamaBackend, ReplayBackend
from evocharge.agents.prompt_loader import load_prompt, prompt_hash, render_task
from evocharge.agents.schemas import AlgorithmicHypothesis
from evocharge.evolution.attribution_plan import (
    AttributionModificationPlan,
    attribution_plan_json_schema,
    validate_attribution_plan,
)
from evocharge.evolution.offspring import make_offspring
from evocharge.evolution.schemas import CandidateRecord, ModificationPlan
from evocharge.operators.primitives import PRIMITIVE_IDS
from evocharge.verification.hardcoded import detect_hardcoded_identities
from evocharge.verification.static import extract_code_from_response, verify_source


def _backend(cfg: AgentsConfig, *, model: str, backend: str) -> Any:
    if backend == "mock":
        return MockBackend()
    if backend == "replay":
        return ReplayBackend(Path(cfg.replay_dir or "artifacts/replays"))
    return OllamaBackend(cfg.ollama, model_override=model)


def _mock_plan(mode: str, parent_ids: list[str]) -> dict[str, Any]:
    return {
        "creation_mode": mode if mode != "semantic_crossover" else "crossover",
        "parent_ids": parent_ids,
        "target_weakness": "APPLIED_BUT_INERT_on_some_fixtures",
        "proposed_change": (
            "Change route scan order and broaden energy-critical ranking; "
            "keep query-based selection without hardcoded IDs."
        ),
        "primitives_added": ["query_energy_slack"],
        "primitives_removed": [],
        "preconditions_added": ["has_customers_on_selected_route"],
        "expected_behavioral_difference": (
            "customer_sequence_changed on more than one development instance"
        ),
        "invariants_to_preserve": [
            "API_1.1.0",
            "no_hardcoded_ids",
            "feasibility_via_validator",
        ],
        "falsification_condition": (
            "No customer_sequence_changed on any of four short-fidelity instances"
        ),
    }


def propose_modification_plan(
    backend: LLMBackend,
    *,
    creation_mode: str,
    parents: list[CandidateRecord],
    config: AgentsConfig,
) -> tuple[AttributionModificationPlan | None, dict[str, Any]]:
    """Ask LLM (or mock) for an AttributionModificationPlan."""
    t0 = time.perf_counter()
    parent_ids = [p.candidate_id for p in parents]
    parents_json = json.dumps(
        [
            {
                "candidate_id": p.candidate_id,
                "creation_mode": p.creation_mode,
                "n_changed_instances": p.n_changed_instances,
                "outcome_counts": p.outcome_counts,
                "fitness_effective": p.fitness.effective_behavioral_change_rate,
                "rejection_reason": p.rejection_reason,
            }
            for p in parents
        ],
        indent=2,
        sort_keys=True,
    )
    mode = creation_mode
    if mode == "semantic_crossover":
        mode = "crossover"
    if isinstance(backend, MockBackend):
        backend.set_response("evolution_planner", _mock_plan(mode, parent_ids))
    system = load_prompt("evolution_plan_system.md")
    task = load_prompt("evolution_plan_task.md")
    user = render_task(
        task,
        creation_mode=mode,
        parents_json=parents_json,
        allowed_primitives_json=json.dumps(sorted(PRIMITIVE_IDS)[:40]),
    )
    result = backend.generate_structured(
        role="evolution_planner",
        system_prompt=system,
        user_prompt=user,
        json_schema=attribution_plan_json_schema(),
        temperature=0.3,
        prompt_template_hashes=[
            prompt_hash("evolution_plan_system.md"),
            prompt_hash("evolution_plan_task.md"),
        ],
        input_artifact_hashes=[p.source_hash for p in parents if p.source_hash],
    )
    latency = time.perf_counter() - t0
    meta = {
        "latency_seconds": latency,
        "raw_text": (result.raw_text or "")[:4000],
        "schema_error": result.schema_error,
        "call_record": result.call_record.model_dump() if result.call_record else None,
    }
    if result.parsed is None:
        return None, meta
    try:
        plan = AttributionModificationPlan.model_validate(result.parsed)
    except Exception as exc:  # noqa: BLE001
        meta["parse_error"] = str(exc)
        return None, meta
    validation = validate_attribution_plan(plan)
    meta["plan_validation"] = validation
    if not validation["accepted"]:
        return None, meta
    return plan, meta


def _hypothesis_from_plan(plan: AttributionModificationPlan) -> AlgorithmicHypothesis:
    prims = [p for p in plan.primitives_added if p in PRIMITIVE_IDS]
    if not prims:
        prims = ["rank_customers_by_energy_criticality", "plan_customer_removal"]
    return AlgorithmicHypothesis(
        hypothesis_id=f"m10a_{plan.creation_mode}",
        name=f"m10a_{plan.creation_mode}",
        category="destroy" if "removal" in " ".join(prims) else "composite",
        target_mechanisms=[plan.creation_mode],
        research_question=plan.target_weakness,
        causal_rationale=plan.proposed_change,
        proposed_mechanism=plan.proposed_change,
        required_primitives=prims,
        decision_conditions=list(plan.preconditions_added),
        invariants=list(plan.invariants_to_preserve) or ["API_1.1.0", "no_hardcoded_ids"],
        expected_benefit=plan.expected_behavioral_difference,
        expected_complexity="O(n^2)",
        transfer_rationale="development_instances_only_m10a",
        evaluation_plan=["short_fidelity_dev_set"],
        potential_failure_modes=["inert_action", "gate_reject"],
        distinction_from_existing_hypotheses=plan.proposed_change[:200],
        falsification_condition=plan.falsification_condition,
        confidence=0.5,
    )


def implement_plan_as_source(
    plan: AttributionModificationPlan,
    *,
    rng_seed: int,
) -> tuple[str, ModificationPlan]:
    """Typed fallback implementer (non-LLM coding stage)."""
    import random

    mode_map = {
        "mutation": "mutation",
        "crossover": "semantic_crossover",
        "evidence_guided_revision": "evidence_guided_revision",
        "novel_invention": "novel_invention",
    }
    mode = mode_map.get(plan.creation_mode, "mutation")
    src, legacy, suffix = make_offspring(
        mode=mode,  # type: ignore[arg-type]
        rng=random.Random(rng_seed),
        parent_ids=list(plan.parent_ids),
        generation=1,
    )
    note = f"m10a_llm_plan:{plan.creation_mode}:{plan.proposed_change[:40]}"
    if "notes=[" in src:
        src = src.replace("notes=[", f'notes=["{note}", ', 1)
    legacy.rationale = f"LLM plan implemented via typed offspring: {plan.proposed_change}"
    legacy.weakness_addressed = plan.target_weakness
    legacy.changes = list(legacy.changes) + [
        f"llm_expected:{plan.expected_behavioral_difference}"
    ]
    _ = suffix
    return src, legacy


def _source_ok(source: str) -> bool:
    if detect_hardcoded_identities(source):
        return False
    return bool(verify_source(source, expected_type="plan_builder").accepted)


def implement_plan_via_coding_agent(
    backend: LLMBackend,
    plan: AttributionModificationPlan,
    config: AgentsConfig,
    *,
    max_revisions: int = 1,
) -> tuple[str | None, dict[str, Any]]:
    """LLM coding stage implementing a validated AttributionModificationPlan."""
    t0 = time.perf_counter()
    hyp = _hypothesis_from_plan(plan)
    request = build_coding_request(hyp, operator_type="plan_builder")
    meta: dict[str, Any] = {"attempts": [], "coding_latency_seconds": 0.0}
    feedback: list[str] = [
        f"Implement ModificationPlan: {plan.model_dump_json()}",
        "No hardcoded node IDs; use state queries; return OperatorPlan with evidence.",
    ]
    if isinstance(backend, MockBackend):
        backend.set_response(
            "coder",
            {
                "metadata": {
                    "candidate_name": "m10a_mock",
                    "hypothesis_id": hyp.hypothesis_id,
                    "operator_type": "plan_builder",
                    "used_primitives": hyp.required_primitives,
                    "preconditions": plan.preconditions_added,
                    "postconditions": [],
                    "invariants": plan.invariants_to_preserve,
                    "expected_complexity": "O(n^2)",
                    "behavioral_description": plan.expected_behavioral_difference,
                    "test_intents": ["metamorphic"],
                    "known_risks": [],
                },
                "source_code": SAFE_PLAN_EXAMPLE,
            },
        )

    source: str | None = None
    for attempt in range(1 + max_revisions):
        result = run_coding_agent(
            backend,
            request.model_copy(update={"revision_feedback": feedback}),
            hyp,
            config,
            schema_retries_so_far=attempt,
        )
        attempt_meta = {
            "attempt": attempt,
            "schema_error": result.schema_error,
            "raw_text": (result.raw_text or "")[:3000],
        }
        meta["attempts"].append(attempt_meta)
        if result.parsed is None:
            feedback.append(f"schema_error:{result.schema_error}")
            continue
        try:
            parsed = CodingAgentResponse.model_validate(result.parsed)
            src = extract_code_from_response(parsed.source_code) or parsed.source_code
        except Exception as exc:  # noqa: BLE001
            feedback.append(f"parse_error:{exc}")
            continue
        if not _source_ok(src):
            feedback.append("static_or_hardcoded_reject; fix API 1.1.0 compliance")
            continue
        source = src
        break
    meta["coding_latency_seconds"] = time.perf_counter() - t0
    return source, meta


def llm_offspring_source(
    *,
    backend_name: str,
    model: str,
    creation_mode: str,
    parents: list[CandidateRecord],
    rng_seed: int,
    config: AgentsConfig | None = None,
    artifacts_dir: Path | None = None,
    use_llm_coding: bool | None = None,
) -> dict[str, Any]:
    """Full LLM attribution offspring: plan → validate → code → artifacts.

    Live ollama/replay: LLM coding agent implements the plan (causal LLM contribution).
    Mock: uses SAFE_PLAN_EXAMPLE via coding mock, or typed implement if coding fails.
    """
    cfg = config or AgentsConfig(
        backend=backend_name if backend_name != "structured" else "mock",
        ollama=OllamaConfig(
            model=model,
            # qwen2.5-coder:7b can OOM / 500 at 8192 on some hosts; keep 4k for 7B class.
            num_ctx=4096 if "7b" in model.lower() else 8192,
            request_timeout_seconds=600.0,
        ),
    )
    if backend_name == "ollama":
        be = _backend(cfg, model=model, backend="ollama")
    elif backend_name == "replay":
        be = _backend(cfg, model=model, backend="replay")
    else:
        be = _backend(cfg, model=model, backend="mock")

    if use_llm_coding is None:
        use_llm_coding = backend_name in {"ollama", "replay", "mock"}

    plan, plan_meta = propose_modification_plan(
        be, creation_mode=creation_mode, parents=parents, config=cfg
    )
    out: dict[str, Any] = {
        "plan_accepted": plan is not None,
        "plan_meta": plan_meta,
        "plan": plan.model_dump() if plan else None,
        "llm_latency_seconds": float(plan_meta.get("latency_seconds") or 0.0),
        "coding_latency_seconds": 0.0,
        "source": None,
        "modification_plan": None,
        "implementation": None,
    }
    if artifacts_dir is not None:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "plan_raw.json").write_text(
            json.dumps(plan_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if plan is None:
        out["error"] = "plan_rejected_or_invalid"
        return out
    if artifacts_dir is not None:
        (artifacts_dir / "modification_plan.json").write_text(
            plan.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    source: str | None = None
    legacy: ModificationPlan | None = None
    if use_llm_coding:
        source, coding_meta = implement_plan_via_coding_agent(be, plan, cfg)
        out["coding_meta"] = coding_meta
        out["coding_latency_seconds"] = float(coding_meta.get("coding_latency_seconds") or 0.0)
        out["llm_latency_seconds"] += out["coding_latency_seconds"]
        if artifacts_dir is not None:
            (artifacts_dir / "coding_raw.json").write_text(
                json.dumps(coding_meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        if source:
            out["implementation"] = "llm_coding_agent"
            legacy = ModificationPlan(
                mode="mutation" if plan.creation_mode != "crossover" else "semantic_crossover",
                rationale=plan.proposed_change,
                parent_ids=list(plan.parent_ids),
                changes=[plan.expected_behavioral_difference],
                weakness_addressed=plan.target_weakness,
            )

    if source is None:
        source, legacy = implement_plan_as_source(plan, rng_seed=rng_seed)
        out["implementation"] = "typed_fallback"
        out["error"] = out.get("error") or "coding_failed_typed_fallback"

    out["source"] = source
    out["modification_plan"] = legacy.model_dump() if legacy else None
    out["attribution_plan"] = plan.model_dump()
    out["plan_accepted"] = True
    return out
