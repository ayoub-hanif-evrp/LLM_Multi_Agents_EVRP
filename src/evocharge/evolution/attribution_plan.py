"""LLM attribution ModificationPlan (Milestone 10A) and validation."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from evocharge.operators.primitives import PRIMITIVE_IDS

CreationModeLLM = Literal[
    "mutation",
    "crossover",
    "evidence_guided_revision",
    "novel_invention",
]


class AttributionModificationPlan(BaseModel):
    """Structured plan the LLM must emit before coding (M10A)."""

    creation_mode: CreationModeLLM
    parent_ids: list[str] = Field(default_factory=list)
    target_weakness: str
    proposed_change: str
    primitives_added: list[str] = Field(default_factory=list)
    primitives_removed: list[str] = Field(default_factory=list)
    preconditions_added: list[str] = Field(default_factory=list)
    expected_behavioral_difference: str
    invariants_to_preserve: list[str] = Field(default_factory=list)
    falsification_condition: str


def attribution_plan_json_schema() -> dict[str, Any]:
    return AttributionModificationPlan.model_json_schema()


_ENTITY_LIT = re.compile(r"\b[CS]\d+\b")
_SLICE = re.compile(r"\[\s*0\s*:\s*1\s*\]")
_NUMERIC_ONLY = re.compile(
    r"^(only\s+)?(change|adjust|tune|set)\s+(k|threshold|constant|numeric)",
    re.I,
)


def validate_attribution_plan(plan: AttributionModificationPlan) -> dict[str, Any]:
    """Reject weak / contaminated plans before coding."""
    errors: list[str] = []
    warnings: list[str] = []
    blob = " ".join(
        [
            plan.target_weakness,
            plan.proposed_change,
            plan.expected_behavioral_difference,
            plan.falsification_condition,
            " ".join(plan.preconditions_added),
        ]
    )
    if _ENTITY_LIT.search(blob):
        errors.append("hardcoded_node_identity_in_plan")
    if _SLICE.search(blob):
        errors.append("fixed_route_position_in_plan")
    if _NUMERIC_ONLY.search(plan.proposed_change.strip()):
        errors.append("numeric_constant_only_change")
    if "rename" in plan.proposed_change.lower() and "logic" in plan.proposed_change.lower():
        errors.append("rename_only_change")
    if not plan.expected_behavioral_difference.strip():
        errors.append("missing_expected_behavioral_difference")
    if not plan.target_weakness.strip():
        errors.append("missing_target_weakness")
    if not plan.parent_ids:
        warnings.append("empty_parent_ids")
    if not plan.invariants_to_preserve:
        warnings.append("empty_invariants")
    for pid in plan.primitives_added + plan.primitives_removed:
        if pid and pid not in PRIMITIVE_IDS:
            errors.append(f"unknown_primitive:{pid}")
    # Require some non-trivial change signal
    if (
        not plan.primitives_added
        and not plan.primitives_removed
        and not plan.preconditions_added
        and len(plan.proposed_change) < 24
    ):
        errors.append("insufficient_change_specification")
    return {
        "accepted": not errors,
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
    }
