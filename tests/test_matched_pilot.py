"""The matched pilot gives every search arm the same number of solver evaluations."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.experiments.fair_budget import solver_passes
from evrptw_autolab.experiments.matched_pilot import MatchedPilotConfig, run_matched_pilot


def test_fake_matched_pilot_uses_the_declared_budget(tmp_path: Path) -> None:
    payload = run_matched_pilot(
        MatchedPilotConfig(
            fake=True,
            micro=True,
            seed=0,
            candidates=4,
            time_limit_s=1.0,
            alns_iterations=5,
            out_dir=tmp_path / "matched",
        )
    )
    assert payload["solver_solves"] == solver_passes(1, candidates=4)
    assert payload["solver_solves"]["single_agent"] == payload["solver_solves"]["five_agent"]
    assert payload["solver_solves"]["random_evolution"] == payload["solver_solves"]["five_agent"]
    assert payload["llm_calls"]["classical"] == 0
    assert payload["llm_calls"]["random_evolution"] == 0
    assert payload["llm_calls"]["five_agent"] > payload["llm_calls"]["single_agent"]
    assert payload["fake"] is True
    assert (tmp_path / "matched" / "matched_pilot.json").exists()
    for selection in payload["selections"].values():
        assert selection["rule"] == "conservative"
