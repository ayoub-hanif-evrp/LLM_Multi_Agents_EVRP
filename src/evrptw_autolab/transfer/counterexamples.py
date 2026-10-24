"""Records of operator failures. Development evidence only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field

from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2

DEVELOPMENT_PARTITIONS = frozenset({"development", "discovery"})

CounterexampleType = Literal[
    "physical_incompatibility",
    "infeasible_candidate",
    "objective_regression",
    "runtime",
]


class Counterexample(BaseModel):
    counterexample_id: str
    operator_id: str
    operator_version: str
    family: str
    seed: int
    counterexample_type: CounterexampleType
    baseline_feasible: bool
    candidate_feasible: bool
    baseline_native_objective: list[float] = Field(default_factory=list)
    candidate_native_objective: list[float] = Field(default_factory=list)
    reproduction_command: str = ""


def objective_counterexample(
    *,
    counterexample_id: str,
    operator_id: str,
    operator_version: str,
    family: str,
    seed: int,
    baseline_feasible: bool,
    candidate_feasible: bool,
    baseline_objective: tuple[float, ...] | list[float],
    candidate_objective: tuple[float, ...] | list[float],
) -> Counterexample | None:
    """Record a worse native objective or a feasibility loss. A strict improvement returns None."""
    if baseline_feasible and not candidate_feasible:
        kind: CounterexampleType = "infeasible_candidate"
    elif baseline_feasible and candidate_feasible and tuple(candidate_objective) > tuple(baseline_objective):
        kind = "objective_regression"
    else:
        return None
    return Counterexample(
        counterexample_id=counterexample_id,
        operator_id=operator_id,
        operator_version=operator_version,
        family=family,
        seed=seed,
        counterexample_type=kind,
        baseline_feasible=baseline_feasible,
        candidate_feasible=candidate_feasible,
        baseline_native_objective=[float(value) for value in baseline_objective],
        candidate_native_objective=[float(value) for value in candidate_objective],
    )


def refuse_non_development(partition: str) -> None:
    """Counterexample mining is refused outside the development partition."""
    if partition not in DEVELOPMENT_PARTITIONS:
        raise RuntimeError(f"counterexample mining refused on partition {partition}")


def differential_counterexample(
    spec: ProblemSpecV2,
    baseline: SolutionV2,
    candidate: SolutionV2,
    *,
    counterexample_id: str,
    operator_id: str,
    operator_version: str,
    seed: int,
    partition: str = "development",
) -> Counterexample | None:
    """Evaluate both solutions with the trusted evaluator and record a regression."""
    refuse_non_development(partition)
    baseline_report = evaluate(spec, baseline)
    candidate_report = evaluate(spec, candidate)
    found = objective_counterexample(
        counterexample_id=counterexample_id,
        operator_id=operator_id,
        operator_version=operator_version,
        family=spec.family,
        seed=seed,
        baseline_feasible=bool(baseline_report.feasible),
        candidate_feasible=bool(candidate_report.feasible),
        baseline_objective=baseline_report.objective_key,
        candidate_objective=candidate_report.objective_key,
    )
    if found is None:
        return None
    found.reproduction_command = (
        f"evaluate_solution_v2 family={spec.family} instance={spec.instance_id} seed={seed}"
    )
    return found


def replay_matches(
    spec: ProblemSpecV2,
    baseline: SolutionV2,
    candidate: SolutionV2,
    record: Counterexample | None,
    *,
    seed: int,
) -> bool:
    """Re-evaluate the same solutions and require the same regression outcome."""
    again = differential_counterexample(
        spec,
        baseline,
        candidate,
        counterexample_id="replay",
        operator_id="replay",
        operator_version="1",
        seed=seed,
    )
    if record is None or again is None:
        return record is None and again is None
    return (
        again.counterexample_type == record.counterexample_type
        and again.baseline_native_objective == record.baseline_native_objective
        and again.candidate_native_objective == record.candidate_native_objective
        and again.baseline_feasible == record.baseline_feasible
        and again.candidate_feasible == record.candidate_feasible
    )


def minimize_failing_case(items: list[str], fails: Callable[[list[str]], bool]) -> list[str]:
    """Drop elements while the failure predicate remains true."""
    current = list(items)
    for item in list(current):
        trial = [value for value in current if value != item]
        if trial and fails(trial):
            current = trial
    return current
