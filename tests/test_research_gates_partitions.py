"""Gates, partitions, and classical scoring contract tests."""

from __future__ import annotations

import pytest

from evrptw_autolab.backbone.alns import (
    RESEARCH_CLASSICAL_REPAIR_SCORING,
    classical_repair_rank_score,
)
from evrptw_autolab.research.gates import paired_gate
from evrptw_autolab.research.partitions import (
    assert_allowed_for_development,
    partition_of_instance_id,
    write_default_exposure_registry,
)


def test_feasibility_regression_outranks_mixed() -> None:
    gate = paired_gate(["improved", "feasibility_regression", "tie"], policy_origin="llm")
    assert gate["quality_gate"] == "feasibility_regression"
    assert gate["llm_discovery_signal"] == "no_go"


def test_beneficial_requires_zero_losses() -> None:
    assert paired_gate(["improved", "improved", "tie"])["quality_gate"] == "beneficial"
    assert paired_gate(["improved", "objective_regression"])["quality_gate"] == "mixed"


def test_handcrafted_beneficial_is_not_llm_go() -> None:
    gate = paired_gate(["improved", "tie"], policy_origin="handcrafted")
    assert gate["quality_gate"] == "beneficial"
    assert gate["llm_discovery_signal"] == "not_applicable"


def test_research_classical_default_is_b1() -> None:
    assert RESEARCH_CLASSICAL_REPAIR_SCORING == "marginal_delta_distance"
    assert classical_repair_rank_score(
        RESEARCH_CLASSICAL_REPAIR_SCORING, total_route_distance=99.0, delta_distance=3.0
    ) == 3.0


def test_partition_validator_blocks_confirmation() -> None:
    assert partition_of_instance_id("c101C5") == "discovery"
    assert partition_of_instance_id("rc105C5") == "confirmation"
    with pytest.raises(PermissionError):
        assert_allowed_for_development(["c101C5", "rc105C5"])


def test_exposure_registry_written() -> None:
    path = write_default_exposure_registry()
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "rc105C5" in text
    assert "RC2" in text
