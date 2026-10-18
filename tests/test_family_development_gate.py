"""Development-budget feasibility and objective gate. The smoke test stays separate."""
from __future__ import annotations

from evrptw_autolab.experiments.family_gate import (
    gate_panel,
    judge_gate,
    load_baseline,
    measure_gate,
    objective_regressed,
)


def test_gate_panel_is_one_distinct_instance_per_family() -> None:
    panel = gate_panel()
    families = [item.family for item in panel]
    assert families == ["schneider", "montoya", "bezzi", "goeke", "hiermann"]
    assert len({item.instance_id for item in panel}) == 5
    assert "tc0c10s3cf1" not in {item.instance_id for item in panel}


def test_objective_regression_is_lexicographic() -> None:
    assert objective_regressed([2.0, 10.0], [3.0, 1.0])
    assert not objective_regressed([2.0, 10.0], [2.0, 9.0])
    assert not objective_regressed([2.0], [2.0])
    assert objective_regressed([1.0], [1.0, 2.0])


def test_judge_rejects_feasibility_loss_and_worse_objective() -> None:
    frozen = [
        {"instance_id": "a", "feasible": True, "objective_key": [10.0]},
        {"instance_id": "b", "feasible": True, "objective_key": [2.0, 5.0]},
    ]
    measured = [
        {"instance_id": "a", "feasible": False, "objective_key": [1.0], "solution_feasible": False},
        {
            "instance_id": "b",
            "feasible": True,
            "objective_key": [2.0, 6.0],
            "solution_feasible": True,
        },
    ]
    verdict = judge_gate(measured, frozen)
    reasons = {item["reason"] for item in verdict["failures"]}
    assert reasons == {"feasibility_regression", "objective_regression"}
    assert not verdict["ok"]


def test_judge_allows_a_better_feasible_objective_and_ignores_infeasible_nominals() -> None:
    frozen = [
        {"instance_id": "a", "feasible": True, "objective_key": [10.0]},
        {"instance_id": "b", "feasible": False, "objective_key": [1.0]},
    ]
    measured = [
        {"instance_id": "a", "feasible": True, "objective_key": [9.0], "solution_feasible": True},
        {"instance_id": "b", "feasible": False, "objective_key": [0.1], "solution_feasible": False},
    ]
    assert judge_gate(measured, frozen)["ok"]


def test_development_gate_matches_frozen_baseline() -> None:
    frozen = load_baseline()
    measured = measure_gate()
    verdict = judge_gate(measured, frozen["rows"])
    assert verdict["ok"], verdict
