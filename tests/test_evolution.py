"""Deterministic CV-MAPE evolution tests (FakeBackend only)."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.components.evolution import EvolutionConfig, run_evolution
from evrptw_autolab.components.evolution.archive import CandidateArchive
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.micro import micro_g1_one_customer, micro_g2_needs_charge


def _backend() -> FakeBackend:
    replies = {
        "architect": json.dumps(
            {
                "summary": "mutate insertion",
                "components": ["insertion_score"],
                "hypothesis": "due-aware insertion",
            }
        ),
        "routing": json.dumps(
            {
                "component": "insertion_score",
                "owner_role": "routing",
                "code": DEFAULT_SOURCES["insertion_score"],
                "rationale": "mutate",
                "mechanism": "delta",
            }
        ),
        "charging": json.dumps(
            {
                "component": "station_score",
                "owner_role": "charging",
                "code": DEFAULT_SOURCES["station_score"],
                "rationale": "mutate",
                "mechanism": "detour",
            }
        ),
        "search": json.dumps(
            {
                "component": "removal_priority",
                "owner_role": "search",
                "code": DEFAULT_SOURCES["removal_priority"],
                "rationale": "mutate",
                "mechanism": "due",
            }
        ),
        "critic": json.dumps(
            {
                "verdict": "ACCEPT",
                "reason": "panel ok",
                "next_component": "none",
                "fault_families": [],
                "hypothesis": "",
            }
        ),
    }
    return FakeBackend(replies, token_sequence=[10] * 40)


def test_evolution_runs_and_freezes_bundle(tmp_path: Path) -> None:
    specs = [
        load_schneider_v2(micro_g1_one_customer().metadata["source_path"]),
        load_schneider_v2(micro_g2_needs_charge().metadata["source_path"]),
    ]
    result = run_evolution(
        specs,
        _backend(),
        EvolutionConfig(
            archive_size=8,
            generations=2,
            seed=1,
            time_limit_s=2.0,
            alns_iterations=15,
            max_llm_calls=20,
            panel_seeds=[0],
            work_dir=tmp_path / "evo",
        ),
    )
    assert result["archive_size"] >= 1
    assert (tmp_path / "evo" / "archive.json").exists()
    assert "panel_instance_ids" in result
    assert result["llm_tokens"] >= 0
    # Resume must restore budget counters from checkpoint.
    archive = CandidateArchive.load(tmp_path / "evo" / "archive.json")
    assert archive.members
    prior_calls = archive.llm_calls
    result2 = run_evolution(
        specs,
        _backend(),
        EvolutionConfig(
            archive_size=8,
            generations=1,
            seed=1,
            time_limit_s=2.0,
            alns_iterations=10,
            max_llm_calls=prior_calls + 6,
            panel_seeds=[0],
            work_dir=tmp_path / "evo",
        ),
    )
    assert result2["llm_calls"] >= prior_calls


def test_evolution_no_critic_ablation(tmp_path: Path) -> None:
    specs = [load_schneider_v2(micro_g1_one_customer().metadata["source_path"])]
    result = run_evolution(
        specs,
        _backend(),
        EvolutionConfig(
            generations=1,
            seed=2,
            use_critic=False,
            use_cross_variant_memory=False,
            max_llm_calls=8,
            time_limit_s=1.5,
            alns_iterations=10,
            panel_seeds=[0],
            work_dir=tmp_path / "evo_nc",
        ),
    )
    assert result["use_critic"] is False
    assert result["use_cross_variant_memory"] is False


def test_default_only_child_not_counted_as_llm_discovery(tmp_path: Path) -> None:
    """If generation falls back to defaults, category must not be hybrid_llm."""
    # Backend returns invalid code so fallback triggers.
    bad = FakeBackend(
        {
            "architect": json.dumps({"summary": "x", "components": ["insertion_score"], "hypothesis": ""}),
            "routing": json.dumps({"code": "not a function"}),
            "charging": json.dumps({"code": "not a function"}),
            "search": json.dumps({"code": "not a function"}),
            "critic": json.dumps(
                {"verdict": "ACCEPT", "reason": "x", "next_component": "none", "fault_families": []}
            ),
        },
        token_sequence=[5] * 20,
    )
    specs = [load_schneider_v2(micro_g1_one_customer().metadata["source_path"])]
    result = run_evolution(
        specs,
        bad,
        EvolutionConfig(
            generations=1,
            seed=3,
            max_llm_calls=10,
            time_limit_s=1.5,
            alns_iterations=8,
            panel_seeds=[0],
            work_dir=tmp_path / "evo_fb",
        ),
    )
    archive = CandidateArchive.load(tmp_path / "evo_fb" / "archive.json")
    for member in archive.members:
        if member.generation >= 1:
            assert member.attribution_category != "hybrid_llm" or member.genuine_llm_components == 0
    assert "best_fully_feasible_on_panel" in result
