"""Deterministic discovery control. Agents cannot override the budget or the evaluator."""

from __future__ import annotations

import hashlib
import json
import random
import time
from typing import Any

from evrptw_autolab.discovery.messages import (
    Critique,
    Hypothesis,
    validate_hypothesis,
    validate_operator,
)
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2
from evrptw_autolab.transfer.counterexamples import refuse_non_development
from evrptw_autolab.transfer.hard_compatibility import compatibility_failures

KNOWN_OPERATOR_FEATURES = frozenset(
    {
        "delta_distance",
        "delta_travel_time",
        "route_load_slack_after_insertion",
        "route_customer_count",
        "new_vehicle_fixed_cost",
        "incremental_energy_cost",
        "battery_margin",
        "detour",
        "battery_arrival",
        "station_rate",
        "fixed_cost",
        "customer_count",
        "route_count",
        "route_utilization",
        "peak_load_ratio",
        "station_count",
        "battery_slack",
        "time_window_slack",
    }
)

MAX_DISCOVERY_CALLS = 20


class CallBudget:
    """Fail-closed call, token, and wall-clock budget shared by every agent role."""

    def __init__(
        self,
        limit: int,
        *,
        model: str = "controlled",
        max_tokens: int = 8_000,
        wall_s: float = 600.0,
    ) -> None:
        if limit < 1 or limit > MAX_DISCOVERY_CALLS:
            raise ValueError(f"call limit must be in 1..{MAX_DISCOVERY_CALLS}")
        self.limit = int(limit)
        self.model = str(model)
        self.max_tokens = int(max_tokens)
        self.wall_s = float(wall_s)
        self.used = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.started = time.monotonic()

    def charge(self, backend: Any, role: str, prompt: str) -> str:
        if self.used >= self.limit:
            raise RuntimeError("llm budget exhausted")
        if time.monotonic() - self.started > self.wall_s:
            raise RuntimeError("discovery wall clock exhausted")
        if self.prompt_tokens + self.completion_tokens >= self.max_tokens:
            raise RuntimeError("token budget exhausted")
        self.used += 1
        text = str(
            backend.complete(prompt=prompt, role=role, temperature=0.0, model=self.model)
        )
        usage = getattr(backend, "last_usage", None)
        if usage is not None:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        if self.prompt_tokens + self.completion_tokens > self.max_tokens:
            raise RuntimeError("token budget exhausted")
        return text


def operator_fingerprint(operator: OperatorSpec) -> str:
    blob = "|".join(
        [
            operator.operator_family,
            operator.implementation_reference,
            operator.candidate_scoring_policy or "",
            operator.applicability_rule or "",
            ",".join(operator.required_capabilities),
            ",".join(operator.forbidden_capabilities),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def admit(operator: OperatorSpec, seen: set[str], flags: Any) -> str:
    validate_operator(operator)
    failures = compatibility_failures(
        operator, flags, available_features=set(KNOWN_OPERATOR_FEATURES)
    )
    if failures:
        raise ValueError(failures[0])
    digest = operator_fingerprint(operator)
    if digest in seen:
        raise ValueError("duplicate operator")
    seen.add(digest)
    return digest


def run_scripted_cycle(*, max_calls: int = 4) -> dict[str, Any]:
    """Replay the tested fake-backend cycle. This does not call a live model."""
    from evrptw_autolab.llm.registry import FakeBackend
    from evrptw_autolab.research.panel import development_case

    proposal = OperatorSpec(
        operator_id="long_detour",
        version="1",
        source_agent="scripted",
        description="Prefer the longer detour.",
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        applicability_rule="1",
        candidate_scoring_policy="-1 * delta_distance",
        fallback_operator="classical_default",
    )
    backend = FakeBackend(
        {
            "architect": json.dumps(
                {
                    "hypothesis": "Negative distance weight lengthens the insertion when utilization is low.",
                    "target_bottleneck": "insertion ranking",
                    "affected_capabilities": ["time_windows"],
                    "proposed_operator_id": "long_detour",
                    "expected_useful_conditions": "high route utilization",
                    "expected_failure_conditions": "low route utilization",
                    "measurable_prediction": "the native objective increases on this repair",
                }
            ),
            "routing_specialist": proposal.model_dump_json(),
            "critic": json.dumps(
                {
                    "what_failed": "the longer detour raised the native objective",
                    "operator_should_change": False,
                    "applicability_should_change": True,
                    "evidence_too_weak": False,
                    "revised_applicability_rule": "route_utilization - 0.9",
                }
            ),
        }
    )
    spec, solution, removed = development_case()
    return run_cycle(
        backend,
        spec,
        solution,
        removed,
        partition="development",
        budget=CallBudget(max_calls, model="controlled"),
    )


def run_live_cycle(
    *,
    model_id: str = "qwen25_coder_14b",
    max_calls: int = 4,
    wall_s: float = 600.0,
    max_tokens: int = 8_000,
) -> dict[str, Any]:
    """One live Ollama discovery cycle on the development repair. Caps are fail-closed."""
    from evrptw_autolab.llm.registry import availability, make_backend, resolve_profile
    from evrptw_autolab.research.panel import development_case

    profile = resolve_profile(model_id)
    status = availability(profile)
    if status != "installed":
        raise RuntimeError(f"model {model_id} is not installed: {status}")
    backend = make_backend(profile)
    spec, solution, removed = development_case()
    budget = CallBudget(
        max_calls,
        model=profile.model,
        max_tokens=max_tokens,
        wall_s=wall_s,
    )
    try:
        result = run_cycle(
            backend,
            spec,
            solution,
            removed,
            partition="development",
            budget=budget,
            architect_prompt=_architect_prompt(),
            specialist_prompt=_specialist_prompt(),
            critic_prompt=_critic_prompt(),
        )
    except Exception as exc:  # noqa: BLE001 — preserve spent budget in the gate artifact
        return {
            "backend": "ollama",
            "model_id": model_id,
            "model": profile.model,
            "llm_calls": budget.used,
            "prompt_tokens": budget.prompt_tokens,
            "completion_tokens": budget.completion_tokens,
            "error": f"{type(exc).__name__}: {exc}",
            "operator": None,
            "decision": {},
            "counterexamples": [],
        }
    result["backend"] = "ollama"
    result["model_id"] = model_id
    result["model"] = profile.model
    result["prompt_tokens"] = budget.prompt_tokens
    result["completion_tokens"] = budget.completion_tokens
    return result


def _parse_json_object(text: str) -> dict[str, Any]:
    """Parse one JSON object from a model reply. Fence wrappers are stripped once."""
    blob = text.strip()
    if blob.startswith("```"):
        lines = blob.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        blob = "\n".join(lines).strip()
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        start = blob.find("{")
        end = blob.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(blob[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("model reply is not a JSON object")
    return payload


def run_cycle(
    backend: Any,
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    *,
    partition: str,
    budget: CallBudget,
    seed: int = 1,
    architect_prompt: str = "review evidence",
    specialist_prompt: str = "propose operator",
    critic_prompt: str = "review counterexample",
) -> dict[str, Any]:
    """One architect, one specialist, and a critic only when a counterexample exists."""
    refuse_non_development(partition)
    from evrptw_autolab.backbone.alns import repair_greedy

    hypothesis = Hypothesis.model_validate(_parse_json_object(budget.charge(backend, "architect", architect_prompt)))
    validate_hypothesis(hypothesis)
    proposed_payload = _parse_json_object(budget.charge(backend, "routing_specialist", specialist_prompt))
    if "operator_spec" in proposed_payload and isinstance(proposed_payload["operator_spec"], dict):
        proposed_payload = proposed_payload["operator_spec"]
    elif "operator" in proposed_payload and isinstance(proposed_payload["operator"], dict):
        proposed_payload = proposed_payload["operator"]
    proposed = OperatorSpec.model_validate(proposed_payload)
    seen: set[str] = set()
    digest = admit(proposed, seen, spec.capabilities)
    operator = proposed.model_copy(update={"source_hash": digest, "mine_counterexamples": True})
    repaired = repair_greedy(
        spec,
        solution,
        removed,
        random.Random(seed),
        operator,
        partition=partition,
    )
    records = list(repaired.metadata.get("counterexamples") or [])
    critique: Critique | None = None
    if records:
        critique = Critique.model_validate(_parse_json_object(budget.charge(backend, "critic", critic_prompt)))
        if (
            not critique.evidence_too_weak
            and critique.applicability_should_change
            and critique.revised_applicability_rule
        ):
            operator = operator.model_copy(
                update={
                    "applicability_rule": critique.revised_applicability_rule,
                    "version": f"{operator.version}.1",
                }
            )
            repaired = repair_greedy(
                spec,
                solution,
                removed,
                random.Random(seed),
                operator,
                partition=partition,
            )
    return {
        "hypothesis": hypothesis.model_dump(),
        "operator": operator.model_dump(),
        "critique": None if critique is None else critique.model_dump(),
        "roles": list(getattr(backend, "calls", [])),
        "llm_calls": budget.used,
        "prompt_tokens": budget.prompt_tokens,
        "completion_tokens": budget.completion_tokens,
        "decision": repaired.metadata.get("search_decision"),
        "counterexamples": records,
        "revised_counterexamples": list(repaired.metadata.get("counterexamples") or []),
        "backend": getattr(backend, "provider", "unknown"),
    }


def _architect_prompt() -> str:
    return (
        "Return JSON only with keys hypothesis, target_bottleneck, affected_capabilities, "
        "proposed_operator_id, expected_useful_conditions, expected_failure_conditions, "
        "measurable_prediction. expected_useful_conditions and expected_failure_conditions "
        "must be single strings, not arrays. Propose one testable EVRP repair scoring "
        "hypothesis about insertion ranking. Do not say 'use better optimization'."
    )


def _specialist_prompt() -> str:
    return (
        "Return one flat JSON object only (no wrapper key) with fields operator_id, version, "
        "source_agent, description, operator_family=repair, implementation_reference=repair_greedy, "
        "required_capabilities, forbidden_capabilities, required_features, hard_preconditions, "
        "candidate_scoring_policy, applicability_rule, fallback_operator=classical_default. "
        "required_capabilities may only use names from: time_windows, capacity, battery, "
        "full_recharge, partial_recharge, nonlinear_charging, multiple_charge_technologies, "
        "pickup_delivery, heterogeneous_fleet, conventional_vehicles, hybrid_vehicles, "
        "matrix_distances, euclidean_distances, max_route_duration, station_revisits_allowed. "
        "Prefer required_capabilities=['time_windows']. "
        "candidate_scoring_policy must be a restricted arithmetic expression over "
        "delta_distance, incremental_energy_cost, battery_margin, route_customer_count, "
        "delta_travel_time. Lower scores are preferred."
    )


def _critic_prompt() -> str:
    return (
        "Return JSON only with what_failed, operator_should_change, applicability_should_change, "
        "evidence_too_weak, revised_applicability_rule. Revise the applicability rule only when "
        "a measured regression justifies it."
    )
