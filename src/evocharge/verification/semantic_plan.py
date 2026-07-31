"""Semantic validation of OperatorPlan contract (Milestone 9A)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from evocharge.operators.generated_api import OperatorPlan


class SemanticPlanReport(BaseModel):
    accepted: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    outcome: str = "UNKNOWN"
    # NOT_APPLICABLE | APPLICABLE_BUT_REJECTED | APPLIED_PENDING | ...


def validate_plan_semantics(plan: OperatorPlan) -> SemanticPlanReport:
    """Reject nonempty plans without selection evidence; allow valid no-action."""
    errors: list[str] = []
    warnings: list[str] = []

    # Milestone 7/8 plans remain executable without M9A evidence fields.
    if str(plan.plan_version).startswith("1.0"):
        return SemanticPlanReport(
            accepted=True,
            errors=[],
            warnings=["legacy_plan_version_1_0"],
            outcome="LEGACY",
        )

    if not plan.applicable:
        if plan.actions:
            errors.append("no_action_must_have_empty_actions")
        if not plan.no_action_reason:
            errors.append("no_action_reason_required")
        if not plan.preconditions_checked:
            warnings.append("preconditions_checked_empty")
        outcome = "NOT_APPLICABLE" if not errors else "APPLICABLE_BUT_REJECTED"
        return SemanticPlanReport(
            accepted=not errors, errors=errors, warnings=warnings, outcome=outcome
        )

    if not plan.actions:
        errors.append("applicable_plan_requires_actions")
    if not plan.selected_entities:
        errors.append("applicable_plan_requires_selected_entities")
    if not plan.selection_evidence:
        errors.append("applicable_plan_requires_selection_evidence")
    if not plan.preconditions_checked:
        warnings.append("preconditions_checked_empty")
    if not plan.expected_behavioral_effect:
        warnings.append("expected_behavioral_effect_empty")

    selected_ids = {e.entity_id for e in plan.selected_entities}
    evidence_ids = {e.entity_id for e in plan.selection_evidence}
    if selected_ids and evidence_ids and not selected_ids.issubset(evidence_ids):
        warnings.append("selection_evidence_incomplete_coverage")

    if errors:
        return SemanticPlanReport(
            accepted=False,
            errors=errors,
            warnings=warnings,
            outcome="APPLICABLE_BUT_REJECTED",
        )
    return SemanticPlanReport(
        accepted=True,
        errors=[],
        warnings=warnings,
        outcome="APPLIED_PENDING",
    )


def classify_invocation_outcome(
    *,
    semantic: SemanticPlanReport,
    plan_applied: bool,
    behaviorally_changed: bool,
) -> str:
    if semantic.outcome == "NOT_APPLICABLE":
        return "NOT_APPLICABLE"
    if not semantic.accepted:
        return "APPLICABLE_BUT_REJECTED"
    if not plan_applied:
        return "APPLICABLE_BUT_REJECTED"
    if behaviorally_changed:
        return "APPLIED_AND_EFFECTIVE"
    return "APPLIED_BUT_INERT"


def semantic_summary(report: SemanticPlanReport) -> dict[str, Any]:
    return report.model_dump()
