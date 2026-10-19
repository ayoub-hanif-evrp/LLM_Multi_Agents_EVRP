"""The four-arm pilot is specified and still unstarted."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.experiments.evolution_pilot import ARMS, pilot_protocol

ROOT = Path(__file__).resolve().parents[1]


def test_pilot_arms_share_one_budget_and_are_not_started() -> None:
    protocol = pilot_protocol()
    assert protocol["status"] == "not_started"
    assert protocol["arms"] == list(ARMS)
    assert protocol["sequential_ollama"] is True
    limits = {row["time_limit_s"] for row in protocol["instances"]}
    assert len(protocol["instances"]) == 5
    assert limits == {8.0, 10.0, 12.0, 15.0}
    passes = protocol["solver_passes"]
    assert passes["random_evolution"] == passes["single_agent"] == passes["five_agent"]
    assert passes["random_evolution"] == 4 * len(protocol["instances"])
    assert passes["classical"] == len(protocol["instances"])
    assert protocol["selection_rule"] == "conservative"
    assert protocol["cost"]["token_extrapolation"]["measured"] is False
    assert protocol["solver_wall_s_lower_bound"] > 0


def test_montoya_confirmation_rejects_merge_and_uniform_weights() -> None:
    path = ROOT / "results" / "v2" / "diagnostics" / "backbone_ablation" / "montoya_confirmation.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = {(row["seed"], row["variant"]): row for row in data["seeds_11_and_22"]}
    for seed in (11, 22):
        base = rows[(seed, "baseline")]
        assert base["feasible"] is True
        merged = rows[(seed, "no_route_merge")]
        assert merged["feasible"] is True
        assert merged["objective_key"][0] > base["objective_key"][0]
    uniform = rows[(11, "uniform_destroy")]
    assert uniform["objective_key"][0] > rows[(11, "baseline")]["objective_key"][0]
    fixed = data["seed7_fixed_route_targets"]
    assert fixed["full_target_feasible"] is True
    assert fixed["full_target_key"][0] > fixed["solved_key"][0]
    assert fixed["reoptimized_partial_key"] == fixed["solved_key"]
    path = ROOT / "results" / "v2" / "diagnostics" / "backbone_ablation" / "summary.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["adopted_variant"] == "baseline"
    for name, decision in summary["decisions"].items():
        assert decision["accepted"] is False or name in summary["accepted_variants"]
        if not decision["accepted"]:
            assert summary["adopted_variant"] != name
