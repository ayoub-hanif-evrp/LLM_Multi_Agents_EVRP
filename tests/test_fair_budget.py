"""Search arms share a declared evaluation budget. Fake evolution cannot exceed it."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.components.evolution import EvolutionConfig, run_evolution
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.experiments.bundle_selection import conservative_decision, robust_decision
from evrptw_autolab.experiments.evolution_pilot import pilot_protocol
from evrptw_autolab.experiments.fair_budget import SEARCH_CANDIDATES, solver_passes
from evrptw_autolab.experiments.readiness import engineering_checks
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.micro import micro_g1_one_customer


def _pairs(wins: int, losses: int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    rows.extend(
        {"baseline_feasible": True, "candidate_feasible": True, "paired_outcome": "candidate"}
        for _ in range(wins)
    )
    rows.extend(
        {"baseline_feasible": True, "candidate_feasible": True, "paired_outcome": "baseline"}
        for _ in range(losses)
    )
    return rows


def test_search_arms_have_the_same_candidate_budget() -> None:
    protocol = pilot_protocol()
    passes = solver_passes(len(protocol["instances"]))
    assert passes["single_agent"] == passes["five_agent"] == passes["random_evolution"]
    assert passes["classical"] * SEARCH_CANDIDATES == passes["five_agent"]
    assert protocol["solver_passes"] == passes


def test_recorded_removal_fails_both_declared_rules() -> None:
    recorded = _pairs(2, 4)
    assert conservative_decision(recorded)["accepted"] is False
    assert robust_decision(recorded)["accepted"] is False
    assert robust_decision(recorded)["reason"] == "loss_fraction_above_one_third"


def test_robust_rule_allows_a_minority_of_losses_and_conservative_does_not() -> None:
    mixed = _pairs(4, 2)
    assert conservative_decision(mixed)["accepted"] is False
    assert conservative_decision(mixed)["reason"] == "objective_regression"
    robust = robust_decision(mixed)
    assert robust["accepted"] is True
    assert robust["reason"] == "accepted_on_aggregate"


def test_panel_evaluation_cap_stops_extra_evolution(tmp_path: Path) -> None:
    spec = load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
    replies = {
        "architect": json.dumps({"summary": "cap", "components": ["insertion_score"], "hypothesis": "none"}),
        "routing": json.dumps(
            {
                "component": "insertion_score",
                "owner_role": "routing",
                "code": DEFAULT_SOURCES["insertion_score"],
                "rationale": "r",
                "mechanism": "m",
            }
        ),
        "charging": json.dumps(
            {
                "component": "station_score",
                "owner_role": "charging",
                "code": DEFAULT_SOURCES["station_score"],
                "rationale": "r",
                "mechanism": "m",
            }
        ),
        "search": json.dumps(
            {
                "component": "removal_priority",
                "owner_role": "search",
                "code": DEFAULT_SOURCES["removal_priority"],
                "rationale": "r",
                "mechanism": "m",
            }
        ),
        "critic": json.dumps(
            {"verdict": "ACCEPT", "reason": "cap", "next_component": "none", "hypothesis": ""}
        ),
    }
    result = run_evolution(
        [spec],
        FakeBackend(replies, token_sequence=[8] * 20),
        EvolutionConfig(
            generations=4,
            seed=1,
            time_limit_s=1.0,
            alns_iterations=5,
            max_llm_calls=20,
            max_panel_evaluations=2,
            panel_seeds=[0],
            work_dir=tmp_path / "cap",
        ),
    )
    assert result["panel_evaluations"] == 2
    assert result["max_panel_evaluations"] == 2


def test_engineering_checks_accept_the_frozen_gate() -> None:
    report = engineering_checks()
    assert report["ok"] is True
    assert report["failures"] == []
