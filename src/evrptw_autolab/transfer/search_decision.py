"""Choose one screened repair. The classical row remains available for comparison."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from evrptw_autolab.discovery.policy_language import PolicyError, choose_minimum
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2
from evrptw_autolab.transfer.counterexamples import (
    Counterexample,
    objective_counterexample,
    refuse_non_development,
)
from evrptw_autolab.transfer.selective_controller import Selection, select_operator


@dataclass(frozen=True)
class ScreenedRepair:
    label: str
    features: dict[str, float]
    solution: SolutionV2
    objective: tuple[float, ...]
    feasible: bool
    acceptance: float


@dataclass(frozen=True)
class RepairDecision:
    action: str
    reason: str
    selected_label: str
    classical_label: str
    changed: bool
    solution: SolutionV2
    counterexample: Counterexample | None


def choose_screened_repair(
    spec: ProblemSpecV2,
    operator: OperatorSpec,
    rows: Sequence[ScreenedRepair],
    context: Mapping[str, float],
    *,
    seed: int,
    partition: str = "development",
    mine: bool = False,
) -> RepairDecision:
    """Apply a compatible scoring rule, or keep the screened classical row."""
    if not rows:
        raise ValueError("no screened repairs")
    if mine:
        refuse_non_development(partition)
    classical = min(rows, key=lambda row: (row.acceptance, row.label))
    selection = select_operator(operator, spec.capabilities, context, rule=operator.applicability_rule)
    chosen = classical
    if selection.action == "apply":
        scored = _scored_row(operator, rows)
        if isinstance(scored, Selection):
            selection = scored
        else:
            chosen = scored
    record = _regression(spec, operator, classical, chosen, selection.action, seed, partition) if mine else None
    if record is not None:
        chosen.solution.metadata.setdefault("counterexamples", []).append(record.model_dump())
    chosen.solution.metadata["search_decision"] = {
        "action": selection.action,
        "reason": selection.reason,
        "selected": chosen.label,
        "classical": classical.label,
        "changed": chosen.label != classical.label,
        "operator_id": operator.operator_id,
        "operator_version": operator.version,
    }
    return RepairDecision(
        action=selection.action,
        reason=selection.reason,
        selected_label=chosen.label,
        classical_label=classical.label,
        changed=chosen.label != classical.label,
        solution=chosen.solution,
        counterexample=record,
    )


def _scored_row(operator: OperatorSpec, rows: Sequence[ScreenedRepair]) -> ScreenedRepair | Selection:
    if not operator.candidate_scoring_policy:
        return Selection(action="classical_default", reason="no scoring policy")
    try:
        index = choose_minimum(operator.candidate_scoring_policy, [row.features for row in rows])
    except PolicyError as exc:
        return Selection(action="abstain", reason=str(exc))
    return rows[index]


def _regression(
    spec: ProblemSpecV2,
    operator: OperatorSpec,
    classical: ScreenedRepair,
    chosen: ScreenedRepair,
    action: str,
    seed: int,
    partition: str,
) -> Counterexample | None:
    if action != "apply":
        return None
    found = objective_counterexample(
        counterexample_id=f"{operator.operator_id}-{chosen.label}",
        operator_id=operator.operator_id,
        operator_version=operator.version,
        family=spec.family,
        seed=seed,
        baseline_feasible=classical.feasible,
        candidate_feasible=chosen.feasible,
        baseline_objective=classical.objective,
        candidate_objective=chosen.objective,
    )
    if found is None:
        return None
    found.reproduction_command = (
        f"repair {operator.operator_id}@{operator.version} seed={seed} partition={partition} label={chosen.label}"
    )
    return found
