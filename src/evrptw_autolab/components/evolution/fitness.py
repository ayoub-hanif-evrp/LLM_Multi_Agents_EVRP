"""Panel-based ranking for evolved component bundles.

Never compress lexicographic objectives into a weighted scalar that can
prefer more vehicles with shorter distance. Comparisons use tuples /
lexicographic keys and feasibility-first panel logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evrptw_autolab.problem.v2.report import EvaluationReportV2


@dataclass(frozen=True, slots=True)
class InstanceEval:
    """One (instance, seed) evaluation of a candidate."""

    family: str
    instance_id: str
    seed: int
    feasible: bool
    objective_key: tuple[float, ...]
    runtime_s: float
    fault_family: str = ""
    fault_detail: str = ""
    vehicles: int = 0
    distance: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "instance_id": self.instance_id,
            "seed": self.seed,
            "feasible": self.feasible,
            "objective_key": list(self.objective_key),
            "runtime_s": self.runtime_s,
            "fault_family": self.fault_family,
            "fault_detail": self.fault_detail,
            "vehicles": self.vehicles,
            "distance": self.distance,
        }


@dataclass
class PanelEvaluation:
    """Comparable multi-instance evaluation for one candidate."""

    instances_tested: int = 0
    instances_feasible: int = 0
    feasibility_rate: float = 0.0
    fully_feasible_on_panel: bool = False
    total_runtime_s: float = 0.0
    validation_ok: bool = True
    per_instance: list[InstanceEval] = field(default_factory=list)
    per_variant: dict[str, dict[str, Any]] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "instances_tested": self.instances_tested,
            "instances_feasible": self.instances_feasible,
            "feasibility_rate": self.feasibility_rate,
            "fully_feasible_on_panel": self.fully_feasible_on_panel,
            "total_runtime_s": self.total_runtime_s,
            "validation_ok": self.validation_ok,
            "per_instance": [row.as_dict() for row in self.per_instance],
            "per_variant": self.per_variant,
        }


def instance_eval_from_report(
    *,
    family: str,
    instance_id: str,
    seed: int,
    report: EvaluationReportV2,
    runtime_s: float,
) -> InstanceEval:
    fault_family = report.first_fault.family if report.first_fault else ""
    fault_detail = report.first_fault.detail if report.first_fault else ""
    return InstanceEval(
        family=family,
        instance_id=instance_id,
        seed=seed,
        feasible=bool(report.feasible),
        objective_key=tuple(float(x) for x in report.objective_key),
        runtime_s=float(runtime_s),
        fault_family=fault_family,
        fault_detail=fault_detail,
        vehicles=int(report.vehicles),
        distance=float(report.total_distance),
    )


def build_panel_evaluation(rows: list[InstanceEval], *, validation_ok: bool = True) -> PanelEvaluation:
    by_family: dict[str, list[InstanceEval]] = {}
    for row in rows:
        by_family.setdefault(row.family, []).append(row)
    per_variant: dict[str, dict[str, Any]] = {}
    for family, group in sorted(by_family.items()):
        feasible = [r for r in group if r.feasible]
        per_variant[family] = {
            "instances_tested": len(group),
            "instances_feasible": len(feasible),
            "feasibility_rate": (len(feasible) / len(group)) if group else 0.0,
            "fully_feasible": len(feasible) == len(group) and bool(group),
            # Keep objective keys only for feasible instances; never mix infeasible scores.
            "feasible_objective_keys": [list(r.objective_key) for r in feasible],
        }
    n = len(rows)
    n_feas = sum(1 for r in rows if r.feasible)
    return PanelEvaluation(
        instances_tested=n,
        instances_feasible=n_feas,
        feasibility_rate=(n_feas / n) if n else 0.0,
        fully_feasible_on_panel=n > 0 and n_feas == n,
        total_runtime_s=sum(r.runtime_s for r in rows),
        validation_ok=validation_ok,
        per_instance=list(rows),
        per_variant=per_variant,
    )


def _lex_better(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """True if a is strictly better than b under lexicographic minimization."""
    return a < b


def compare_panel(a: PanelEvaluation, b: PanelEvaluation) -> int:
    """Return -1 if a ranks better, 1 if b ranks better, 0 if tied.

    Priority:
    1. component validation_ok
    2. instances_feasible (count)
    3. fully_feasible_on_panel
    4. per-instance lex objective among jointly feasible rows (fixed order)
    5. lower total runtime
    """
    if a.validation_ok != b.validation_ok:
        return -1 if a.validation_ok else 1
    if a.instances_feasible != b.instances_feasible:
        return -1 if a.instances_feasible > b.instances_feasible else 1
    if a.fully_feasible_on_panel != b.fully_feasible_on_panel:
        return -1 if a.fully_feasible_on_panel else 1

    a_map = {(r.family, r.instance_id, r.seed): r for r in a.per_instance}
    b_map = {(r.family, r.instance_id, r.seed): r for r in b.per_instance}
    keys = sorted(set(a_map) | set(b_map))
    for key in keys:
        ra = a_map.get(key)
        rb = b_map.get(key)
        if ra is None or rb is None:
            # Incomplete panel coverage ranks worse.
            if ra is None and rb is None:
                continue
            return 1 if ra is None else -1
        if ra.feasible and rb.feasible:
            if _lex_better(ra.objective_key, rb.objective_key):
                return -1
            if _lex_better(rb.objective_key, ra.objective_key):
                return 1
        elif ra.feasible != rb.feasible:
            return -1 if ra.feasible else 1

    if a.total_runtime_s + 1e-12 < b.total_runtime_s:
        return -1
    if b.total_runtime_s + 1e-12 < a.total_runtime_s:
        return 1
    return 0


def panel_is_better(a: PanelEvaluation, b: PanelEvaluation) -> bool:
    return compare_panel(a, b) < 0


def fitness_from_report(report: EvaluationReportV2, runtime_s: float) -> float:
    """Deprecated scalar helper kept for older call sites / smoke tests.

    Prefer ``compare_panel`` / ``PanelEvaluation``. This scalar is feasibility-first
    but must NOT be used to compare lexicographic multi-component objectives across
    candidates when a secondary objective could overturn vehicle count.
    """
    if not report.feasible:
        viol = len(report.violations) + sum(float(v.magnitude or 0.0) for v in report.violations)
        return -1_000_000.0 - 100.0 * viol - runtime_s
    # Encode only the primary lexicographic component at full weight; secondary
    # components must not overturn it. Remaining components use tiny epsilons for
    # tie-breaking only when the primary matches exactly in float space.
    if not report.objective_key:
        return 1_000_000.0 - float(report.objective or 0.0) - 0.01 * runtime_s
    primary = float(report.objective_key[0])
    score = 1_000_000.0 - primary
    # Secondary terms are bounded so they cannot overcome a primary difference of 1.
    remainder = 0.0
    scale = 1e-6
    for value in report.objective_key[1:]:
        remainder += float(value) * scale
        scale *= 1e-3
    # Clamp remainder into (-0.5, 0.5) so vehicle+1 can never lose to distance.
    remainder = max(-0.49, min(0.49, remainder))
    return score - remainder - 0.01 * runtime_s
