"""Typed messages passed between discovery roles."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from evrptw_autolab.discovery.schemas import OperatorSpec

_GENERIC = frozenset({"use better optimization", "optimize better", "improve the solver"})


def _as_text(value: Any) -> str:
    """Accept a string or join a list of strings. Other shapes stay invalid."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "; ".join(item.strip() for item in value if item.strip())
    raise TypeError("expected string")


class Hypothesis(BaseModel):
    hypothesis: str
    target_bottleneck: str
    affected_capabilities: list[str] = Field(default_factory=list)
    proposed_operator_id: str
    expected_useful_conditions: str
    expected_failure_conditions: str
    measurable_prediction: str

    @field_validator(
        "hypothesis",
        "target_bottleneck",
        "proposed_operator_id",
        "expected_useful_conditions",
        "expected_failure_conditions",
        "measurable_prediction",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _as_text(value)

    @field_validator("affected_capabilities", mode="before")
    @classmethod
    def _coerce_capabilities(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            parts = [part.strip() for part in value.replace(";", ",").split(",")]
            return [part for part in parts if part]
        if isinstance(value, list):
            return [_as_text(item) for item in value]
        raise TypeError("expected capability list")


class Critique(BaseModel):
    what_failed: str
    operator_should_change: bool
    applicability_should_change: bool
    evidence_too_weak: bool
    revised_applicability_rule: str | None = None

    @field_validator("what_failed", "revised_applicability_rule", mode="before")
    @classmethod
    def _coerce_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        return _as_text(value)


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
