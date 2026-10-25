"""Deterministic discovery control. Agents cannot override the budget or the evaluator."""

from __future__ import annotations

import hashlib
import json
import random
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


class CallBudget:
    def __init__(self, limit: int) -> None:
        self.limit = int(limit)
        self.used = 0

    def charge(self, backend: Any, role: str, prompt: str) -> str:
        if self.used >= self.limit:
            raise RuntimeError("llm budget exhausted")
        self.used += 1
        return str(backend.complete(prompt=prompt, role=role, temperature=0.0, model="controlled"))


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
    failures = compatibility_failures(operator, flags)
    if failures:
        raise ValueError(failures[0])
    digest = operator_fingerprint(operator)
    if digest in seen:
        raise ValueError("duplicate operator")
    seen.add(digest)
    return digest


def run_scripted_cycle(*, max_calls: int = 4) -> dict[str, Any]:
    """Replay the tested fake-backend cycle. This does not call a live model."""
    import json

    from evrptw_autolab.discovery.schemas import OperatorSpec
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
    return run_cycle(backend, spec, solution, removed, partition="development", budget=CallBudget(max_calls))


def run_cycle(
    backend: Any,
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    *,
    partition: str,
    budget: CallBudget,
    seed: int = 1,
) -> dict[str, Any]:
    """One architect, one specialist, and a critic only when a counterexample exists."""
    refuse_non_development(partition)
    from evrptw_autolab.backbone.alns import repair_greedy

    hypothesis = Hypothesis.model_validate(json.loads(budget.charge(backend, "architect", "review evidence")))
    validate_hypothesis(hypothesis)
    proposed = OperatorSpec.model_validate(json.loads(budget.charge(backend, "routing_specialist", "propose operator")))
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
        critique = Critique.model_validate(json.loads(budget.charge(backend, "critic", "review counterexample")))
        if (
            not critique.evidence_too_weak
            and critique.applicability_should_change
            and critique.revised_applicability_rule
        ):
            operator = operator.model_copy(
                update={"applicability_rule": critique.revised_applicability_rule, "version": f"{operator.version}.1"}
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
        "decision": repaired.metadata.get("search_decision"),
        "counterexamples": records,
        "revised_counterexamples": list(repaired.metadata.get("counterexamples") or []),
    }
