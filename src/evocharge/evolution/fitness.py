"""Fitness extraction and Pareto archive (Milestone 9B)."""

from __future__ import annotations

from typing import Any

from evocharge.evolution.offspring import source_fingerprint
from evocharge.evolution.schemas import CandidateRecord, FitnessVector


def fitness_from_evaluation(
    *,
    evaluation: dict[str, Any],
    source: str,
    is_noop: bool,
    archive_fps: list[dict[str, Any]],
) -> FitnessVector:
    outcomes = evaluation.get("outcome_counts") or {}
    n = max(1, sum(int(v) for v in outcomes.values()) or 1)
    harmful = 0  # reserved; paired degradation tracked separately when present
    effective = int(outcomes.get("APPLIED_AND_EFFECTIVE", 0))
    inert = int(outcomes.get("APPLIED_BUT_INERT", 0))
    rejected = int(outcomes.get("APPLICABLE_BUT_REJECTED", 0))
    not_app = int(outcomes.get("NOT_APPLICABLE", 0))

    fp = source_fingerprint(source)
    # Novelty: fraction of fingerprint keys differing from nearest archive member
    novelty = 1.0
    if archive_fps:
        best_sim = 0.0
        for other in archive_fps:
            keys = set(fp) | set(other)
            if not keys:
                continue
            agree = sum(1 for k in keys if fp.get(k) == other.get(k))
            best_sim = max(best_sim, agree / len(keys))
        novelty = max(0.0, 1.0 - best_sim)

    # Penalize noop usefulness
    effective_rate = effective / n
    if is_noop:
        effective_rate = 0.0
        novelty = min(novelty, 0.1)

    complexity = float(fp.get("n_lines") or 0) / 100.0
    redundancy = 1.0 if "handcrafted_analogue" in source or "analogue_" in source else 0.0

    # Prefer paired ALNS distance improvement when evaluation provides it
    # (negative distance delta vs baseline => improvement).
    paired_deltas = evaluation.get("paired_distance_deltas_vs_baseline") or []
    if not paired_deltas and evaluation.get("analysis"):
        mean_d = (evaluation.get("analysis") or {}).get("mean_paired_distance_delta_vs_baseline")
        if mean_d is not None:
            paired_deltas = [float(mean_d)]
    if paired_deltas:
        # Convert "lower distance is better" into a [0,1]-ish improvement score
        mean_delta = sum(float(d) for d in paired_deltas) / len(paired_deltas)
        paired_obj = max(0.0, min(1.0, -mean_delta / 100.0))
        if mean_delta > 1e-9:
            harmful = max(harmful, sum(1 for d in paired_deltas if float(d) > 1e-9))
    else:
        paired_obj = 0.0

    return FitnessVector(
        feasibility_preservation_rate=1.0 - (rejected / n),
        applicability_rate=1.0 - (not_app / n),
        valid_no_action_rate=not_app / n,
        effective_behavioral_change_rate=effective_rate,
        paired_objective_improvement=paired_obj,
        degradation_rate=harmful / n,
        runtime_overhead=0.0,
        operator_stability=1.0 - (inert / n),
        selection_diversity=float(evaluation.get("selection_diversity") or 0) / 10.0,
        novelty=novelty,
        redundancy_with_handcrafted=redundancy,
        source_complexity=complexity,
        score_notes=[
            f"effective={effective}",
            f"inert={inert}",
            f"not_applicable={not_app}",
            f"paired_obj={paired_obj:.4f}",
        ],
    )


def _maximize_vector(fit: FitnessVector) -> list[float]:
    """Objectives to maximize (Pareto)."""
    return [
        fit.feasibility_preservation_rate,
        fit.paired_objective_improvement,
        fit.effective_behavioral_change_rate,
        fit.novelty,
        1.0 - min(1.0, fit.source_complexity),
        1.0 - fit.degradation_rate,
        1.0 - fit.redundancy_with_handcrafted,
        fit.operator_stability,
        fit.effective_behavioral_change_rate * fit.feasibility_preservation_rate,
    ]


def dominates(a: FitnessVector, b: FitnessVector) -> bool:
    av = _maximize_vector(a)
    bv = _maximize_vector(b)
    ge = all(x >= y - 1e-12 for x, y in zip(av, bv, strict=True))
    gt = any(x > y + 1e-12 for x, y in zip(av, bv, strict=True))
    return ge and gt


def update_pareto_archive(
    archive: list[CandidateRecord],
    candidate: CandidateRecord,
) -> list[CandidateRecord]:
    if candidate.is_noop:
        # Never archive noop as useful
        return archive
    # Remove dominated members; skip if dominated
    if any(dominates(m.fitness, candidate.fitness) for m in archive):
        return archive
    kept = [m for m in archive if not dominates(candidate.fitness, m.fitness)]
    cand = candidate.model_copy(deep=True)
    cand.archived = True
    kept.append(cand)
    return kept


def penalize_or_drop(candidate: CandidateRecord) -> str | None:
    """Return rejection reason if candidate should be removed from population."""
    fit = candidate.fitness
    if candidate.is_noop:
        return None  # keep as control, never select as useful
    if fit.effective_behavioral_change_rate <= 1e-12 and fit.valid_no_action_rate >= 0.99:
        # Always no-action without being the noop control — weak
        return "consistently_not_applicable"
    if (
        fit.effective_behavioral_change_rate <= 1e-12
        and fit.applicability_rate >= 0.5
        and fit.operator_stability < 0.3
    ):
        return "consistently_inert"
    if fit.degradation_rate >= 0.5:
        return "consistently_harmful"
    if fit.source_complexity > 1.5:
        return "unnecessarily_complex"
    if (
        fit.redundancy_with_handcrafted >= 0.99
        and candidate.creation_mode != "handcrafted_analogue"
    ):
        return "equivalent_handcrafted"
    return None
