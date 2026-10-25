"""Choose apply, abstain, or the classical fallback. Hard compatibility wins over the rule."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel

from evrptw_autolab.discovery.policy_language import PolicyError, evaluate_policy
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import CapabilityFlags
from evrptw_autolab.transfer.hard_compatibility import compatibility_failures

SelectionAction = Literal["apply", "classical_default", "abstain"]


class Selection(BaseModel):
    action: SelectionAction
    reason: str


def select_operator(
    operator: OperatorSpec,
    flags: CapabilityFlags,
    features: Mapping[str, float],
    *,
    rule: str | None = None,
) -> Selection:
    """A positive rule score applies the operator. Incompatibility always falls back."""
    failures = compatibility_failures(operator, flags)
    if failures:
        return Selection(action="classical_default", reason=failures[0])
    expression = rule if rule is not None else operator.applicability_rule or operator.candidate_scoring_policy
    if not expression:
        return Selection(action="classical_default", reason="no applicability rule")
    try:
        score = evaluate_policy(expression, features)
    except PolicyError as exc:
        return Selection(action="abstain", reason=str(exc))
    if score > 0.0:
        return Selection(action="apply", reason="applicability score positive")
    return Selection(action="classical_default", reason="applicability score non-positive")
