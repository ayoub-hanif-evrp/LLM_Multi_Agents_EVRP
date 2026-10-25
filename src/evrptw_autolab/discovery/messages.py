"""Typed messages passed between discovery roles."""

from __future__ import annotations

from pydantic import BaseModel, Field

from evrptw_autolab.discovery.schemas import OperatorSpec

_GENERIC = frozenset({"use better optimization", "optimize better", "improve the solver"})


class Hypothesis(BaseModel):
    hypothesis: str
    target_bottleneck: str
    affected_capabilities: list[str] = Field(default_factory=list)
    proposed_operator_id: str
    expected_useful_conditions: str
    expected_failure_conditions: str
    measurable_prediction: str


class Critique(BaseModel):
    what_failed: str
    operator_should_change: bool
    applicability_should_change: bool
    evidence_too_weak: bool
    revised_applicability_rule: str | None = None


def validate_hypothesis(hypothesis: Hypothesis) -> None:
    text = hypothesis.hypothesis.strip().lower()
    if text in _GENERIC:
        raise ValueError("generic hypothesis")
    if not hypothesis.affected_capabilities or not hypothesis.measurable_prediction.strip():
        raise ValueError("hypothesis is not testable")


def validate_operator(operator: OperatorSpec) -> None:
    if not operator.operator_id.strip() or not operator.candidate_scoring_policy:
        raise ValueError("operator is incomplete")
    if operator.candidate_scoring_policy.strip() in {"0", "0.0"}:
        raise ValueError("no-op scoring policy")
