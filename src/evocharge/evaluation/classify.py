"""Deterministic candidate classification (Milestone 8)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from evocharge.evaluation.behavioral import BehavioralEffect, is_behaviorally_inert

CandidateClass = Literal[
    "INERT",
    "REDUNDANT",
    "VALID_BUT_HARMFUL",
    "VALID_BUT_UNSTABLE",
    "PROMISING",
    "INSUFFICIENT_EVIDENCE",
]


CLASS_DEFINITIONS: dict[str, str] = {
    "INERT": (
        "Frequently returns nonempty plans but rarely changes the executed solution "
        "(customer/station/charging/route assignment)."
    ),
    "REDUNDANT": (
        "Paired behavior closely matches a handcrafted analogue "
        "(similar move rates and objective deltas)."
    ),
    "VALID_BUT_HARMFUL": (
        "Preserves feasibility on average but shows consistent paired objective degradation "
        "or elevated infeasible-plan rates."
    ),
    "VALID_BUT_UNSTABLE": (
        "Feasibility usually preserved but seed variance is high or effects flip sign often."
    ),
    "PROMISING": (
        "Preserves feasibility and shows consistent positive paired effects "
        "and/or useful behavioral novelty vs analogues."
    ),
    "INSUFFICIENT_EVIDENCE": (
        "Too few successful applications, fixtures, or paired seeds to classify confidently."
    ),
}


class CandidateClassification(BaseModel):
    candidate_id: str
    label: CandidateClass
    definition: str
    rationale: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    promoted: bool = False


def classify_candidate(
    *,
    candidate_id: str,
    behavioral_effects: list[BehavioralEffect],
    paired_delta_primary: list[float] | None = None,
    analogue_similarity: float | None = None,
    feasible_run_rate: float | None = None,
    min_effects: int = 3,
) -> CandidateClassification:
    """Authoritative deterministic classification (Critic may not override)."""
    rationale: list[str] = []
    n = len(behavioral_effects)
    if n < min_effects:
        return CandidateClassification(
            candidate_id=candidate_id,
            label="INSUFFICIENT_EVIDENCE",
            definition=CLASS_DEFINITIONS["INSUFFICIENT_EVIDENCE"],
            rationale=[f"only_{n}_behavioral_probes_need_{min_effects}"],
            metrics={"n_effects": n},
        )

    nonempty = sum(1 for e in behavioral_effects if e.plan_nonempty)
    applied = sum(1 for e in behavioral_effects if e.plan_applied)
    inert = sum(1 for e in behavioral_effects if e.plan_nonempty and is_behaviorally_inert(e))
    changed = sum(
        1
        for e in behavioral_effects
        if e.customer_sequence_changed
        or e.station_sequence_changed
        or e.charging_decision_changed
    )
    feas = sum(1 for e in behavioral_effects if e.feasibility_preserved)
    feas_rate = feas / n
    change_rate = changed / max(1, nonempty)
    inert_rate = inert / max(1, nonempty)

    metrics: dict[str, Any] = {
        "n_effects": n,
        "nonempty_rate": nonempty / n,
        "applied_rate": applied / n,
        "inert_rate_among_nonempty": inert_rate,
        "behavioral_change_rate_among_nonempty": change_rate,
        "feasibility_preserved_rate": feas_rate,
        "analogue_similarity": analogue_similarity,
        "mean_paired_delta_primary": (
            sum(paired_delta_primary) / len(paired_delta_primary)
            if paired_delta_primary
            else None
        ),
        "feasible_run_rate": feasible_run_rate,
    }

    if nonempty == 0:
        return CandidateClassification(
            candidate_id=candidate_id,
            label="INSUFFICIENT_EVIDENCE",
            definition=CLASS_DEFINITIONS["INSUFFICIENT_EVIDENCE"],
            rationale=["no_nonempty_plans"],
            metrics=metrics,
        )

    if inert_rate >= 0.7 or change_rate <= 0.2:
        rationale.append(f"inert_rate={inert_rate:.2f}")
        rationale.append(f"change_rate={change_rate:.2f}")
        return CandidateClassification(
            candidate_id=candidate_id,
            label="INERT",
            definition=CLASS_DEFINITIONS["INERT"],
            rationale=rationale,
            metrics=metrics,
        )

    if analogue_similarity is not None and analogue_similarity >= 0.85:
        rationale.append(f"analogue_similarity={analogue_similarity:.2f}")
        return CandidateClassification(
            candidate_id=candidate_id,
            label="REDUNDANT",
            definition=CLASS_DEFINITIONS["REDUNDANT"],
            rationale=rationale,
            metrics=metrics,
        )

    if feas_rate < 0.9:
        rationale.append(f"feasibility_preserved_rate={feas_rate:.2f}")
        return CandidateClassification(
            candidate_id=candidate_id,
            label="VALID_BUT_UNSTABLE",
            definition=CLASS_DEFINITIONS["VALID_BUT_UNSTABLE"],
            rationale=rationale,
            metrics=metrics,
        )

    if paired_delta_primary:
        mean_delta = sum(paired_delta_primary) / len(paired_delta_primary)
        pos = sum(1 for d in paired_delta_primary if d < -1e-9)
        neg = sum(1 for d in paired_delta_primary if d > 1e-9)
        if mean_delta > 1e-6 and neg >= max(2, len(paired_delta_primary) // 2):
            rationale.append(f"mean_primary_delta={mean_delta:.4f}_degradation")
            return CandidateClassification(
                candidate_id=candidate_id,
                label="VALID_BUT_HARMFUL",
                definition=CLASS_DEFINITIONS["VALID_BUT_HARMFUL"],
                rationale=rationale,
                metrics=metrics,
            )
        if mean_delta < -1e-6 and pos >= max(2, len(paired_delta_primary) // 2):
            rationale.append(f"mean_primary_delta={mean_delta:.4f}_improvement")
            rationale.append(f"behavioral_change_rate={change_rate:.2f}")
            return CandidateClassification(
                candidate_id=candidate_id,
                label="PROMISING",
                definition=CLASS_DEFINITIONS["PROMISING"],
                rationale=rationale,
                metrics=metrics,
            )
        if change_rate >= 0.4 and abs(mean_delta) <= 1e-6:
            rationale.append("behavior_changes_but_no_consistent_objective_gain")
            return CandidateClassification(
                candidate_id=candidate_id,
                label="INSUFFICIENT_EVIDENCE",
                definition=CLASS_DEFINITIONS["INSUFFICIENT_EVIDENCE"],
                rationale=rationale,
                metrics=metrics,
            )

    if change_rate >= 0.4 and feas_rate >= 0.9:
        rationale.append("feasibility_ok_and_behavior_changes_without_enough_paired_gain")
        return CandidateClassification(
            candidate_id=candidate_id,
            label="INSUFFICIENT_EVIDENCE",
            definition=CLASS_DEFINITIONS["INSUFFICIENT_EVIDENCE"],
            rationale=rationale,
            metrics=metrics,
        )

    return CandidateClassification(
        candidate_id=candidate_id,
        label="INSUFFICIENT_EVIDENCE",
        definition=CLASS_DEFINITIONS["INSUFFICIENT_EVIDENCE"],
        rationale=rationale or ["default_insufficient"],
        metrics=metrics,
    )
