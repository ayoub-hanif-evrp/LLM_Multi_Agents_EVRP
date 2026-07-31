"""Deterministic validation of Critic reports (Milestone 8)."""

from __future__ import annotations

from typing import Any

from evocharge.agents.critic import CriticReport
from evocharge.agents.validation import detect_prohibited_content

_COMPATIBLE: dict[str, set[str]] = {
    "INERT": {"reject", "revise_later", "insufficient_evidence"},
    "REDUNDANT": {"reject", "revise_later", "insufficient_evidence"},
    "VALID_BUT_HARMFUL": {"reject", "revise_later"},
    "VALID_BUT_UNSTABLE": {"revise_later", "insufficient_evidence", "reject"},
    "PROMISING": {"retain_for_evolution", "revise_later", "insufficient_evidence"},
    "INSUFFICIENT_EVIDENCE": {"insufficient_evidence", "revise_later", "reject"},
}


def validate_critic_report(
    report: CriticReport,
    *,
    evaluation: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if report.candidate_id != evaluation.get("candidate_id"):
        errors.append("candidate_id_mismatch")

    classification = evaluation.get("classification") or {}
    label = str(classification.get("label") or "")
    if label and report.recommended_status not in _COMPATIBLE.get(label, set()):
        errors.append(
            f"recommendation_incompatible_with_classification:{label}->{report.recommended_status}"
        )

    blob = " ".join(
        [
            report.evidence_summary,
            report.redundancy_assessment,
            " ".join(report.strengths),
            " ".join(report.weaknesses),
            " ".join(report.causal_interpretation),
        ]
    ).lower()

    prohibited = detect_prohibited_content(blob)
    errors.extend(prohibited)

    superiority = any(
        w in blob
        for w in (
            "superior to all",
            "state of the art",
            "best known",
            "dominates the baseline on all",
        )
    )
    deltas = evaluation.get("paired_distance_deltas_vs_baseline") or []
    if superiority and len(deltas) < 2:
        errors.append("superiority_claim_without_paired_evidence")

    # Inert plans must not be described as meaningful changes
    probes = (evaluation.get("behavioral") or {}).get("behavioral_probes") or []
    inert_count = sum(1 for p in probes if p.get("inert"))
    if inert_count >= max(1, len(probes) // 2):
        if any(
            phrase in blob
            for phrase in (
                "consistently changes routes",
                "meaningful route improvement",
                "always alters the solution",
            )
        ):
            errors.append("inert_plan_described_as_meaningful_change")

    if not (0.0 <= report.confidence <= 1.0):
        errors.append("confidence_out_of_range")

    # Numerical claims: deltas mentioned should not invent magnitudes absent from eval
    if "improvement of" in blob and not deltas:
        warnings.append("improvement_language_without_deltas")

    if evaluation.get("optimization_claim"):
        errors.append("evaluation_must_not_set_optimization_claim")

    accepted = not errors
    return {
        "accepted": accepted,
        "errors": errors,
        "warnings": warnings,
        "deterministic_classification_authoritative": True,
        "classification_label": label,
    }
