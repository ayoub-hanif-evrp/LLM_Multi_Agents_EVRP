"""A worse native objective is a counterexample. An improvement is not."""

import pytest

from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.micro import micro_g3_two_customers
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2
from evrptw_autolab.transfer.counterexamples import (
    differential_counterexample,
    minimize_failing_case,
    objective_counterexample,
    refuse_non_development,
    replay_matches,
)


def test_a_worse_objective_is_recorded() -> None:
    found = objective_counterexample(
        counterexample_id="cx-1",
        operator_id="pair_relocate",
        operator_version="1",
        family="goeke",
        seed=7,
        baseline_feasible=True,
        candidate_feasible=True,
        baseline_objective=(3.0, 10.0),
        candidate_objective=(3.0, 12.0),
    )
    assert found is not None
    assert found.counterexample_type == "objective_regression"


def test_an_improvement_is_not_a_counterexample() -> None:
    found = objective_counterexample(
        counterexample_id="cx-2",
        operator_id="pair_relocate",
        operator_version="1",
        family="goeke",
        seed=7,
        baseline_feasible=True,
        candidate_feasible=True,
        baseline_objective=(3.0, 10.0),
        candidate_objective=(2.0, 40.0),
    )
    assert found is None


def test_minimization_keeps_the_smallest_failing_set() -> None:
    def fails(items: list[str]) -> bool:
        return "battery" in items and "window" in items

    reduced = minimize_failing_case(["depot", "battery", "window", "station"], fails)
    assert reduced == ["battery", "window"]


def _micro_pair() -> tuple[ProblemSpecV2, SolutionV2, SolutionV2]:
    spec = load_schneider_v2(micro_g3_two_customers().metadata["source_path"])
    depot = spec.depot_ids[0]

    def route(*customers: str) -> list[RouteStopV2]:
        return [RouteStopV2(depot, event="depot"), *[RouteStopV2(customer, event="visit") for customer in customers], RouteStopV2(depot, event="depot")]

    joint = SolutionV2(routes=[route("C1", "C2")], vehicle_assignments=["EV"])
    split = SolutionV2(routes=[route("C1"), route("C2")], vehicle_assignments=["EV", "EV"])
    return spec, joint, split


def test_splitting_one_feasible_route_is_an_objective_counterexample() -> None:
    spec, joint, split = _micro_pair()
    found = differential_counterexample(
        spec,
        joint,
        split,
        counterexample_id="cx-split",
        operator_id="extra_vehicle",
        operator_version="1",
        seed=1,
    )
    assert found is not None
    assert found.counterexample_type == "objective_regression"
    assert found.candidate_native_objective[0] > found.baseline_native_objective[0]
    assert replay_matches(spec, joint, split, found, seed=1)


def test_held_out_and_confirmation_partitions_are_refused() -> None:
    for partition in ("heldout", "confirmation"):
        with pytest.raises(RuntimeError, match="refused"):
            refuse_non_development(partition)
