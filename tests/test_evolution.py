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
    }
    return FakeBackend(replies)


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
            max_llm_calls=12,
            work_dir=tmp_path / "evo",
        ),
    )
    assert result["archive_size"] >= 1
    assert (tmp_path / "evo" / "archive.json").exists()
    assert (tmp_path / "evo" / "frozen_bundle").exists()
    assert result["llm_calls"] >= 1
    # Resume must not crash and should load checkpoint.
    archive = CandidateArchive.load(tmp_path / "evo" / "archive.json")
    assert archive.members
    result2 = run_evolution(
        specs,
        _backend(),
        EvolutionConfig(
            archive_size=8,
            generations=1,
            seed=1,
            time_limit_s=2.0,
            alns_iterations=10,
            max_llm_calls=4,
            work_dir=tmp_path / "evo",
        ),
    )
    assert result2["checkpoint"]


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
            max_llm_calls=6,
            time_limit_s=1.5,
            alns_iterations=10,
            work_dir=tmp_path / "evo_nc",
        ),
    )
    assert result["use_critic"] is False
    assert result["use_cross_variant_memory"] is False
