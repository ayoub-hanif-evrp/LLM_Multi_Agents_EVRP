"""Clean-lab autonomy invariants.

Governing rule: the fixed laboratory may expose failures; it must never convert
a failed candidate into a better EVRPTW candidate by injecting solver code.
"""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.synthesis import bootstrap, compile_repair, contract, integration

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "evrptw_autolab"


def test_no_hidden_stitch() -> None:
    assert not hasattr(integration, "stitch_helpers")


def test_contract_has_no_construction_recipe() -> None:
    blob = (contract.INSTANCE_API + contract.PROBLEM_BRIEF + str(contract.FAULT_ATLAS)).lower()
    assert "one customer per" not in blob
    assert "dedicated" not in blob
    assert "repair_energy" not in blob


def test_repair_prompts_have_no_hidden_solver() -> None:
    text = Path(compile_repair.__file__).read_text(encoding="utf-8").lower()
    assert "dedicated-route" not in text
    assert "one route [depot_id, customer_id, depot_id]" not in text
    assert "tries one then two station" not in text
    assert "force_executable_entry" not in text
    assert "salvage_solver_interface" not in text
    assert "entry_recovery" not in text


def test_bootstrap_does_not_import_recovery() -> None:
    text = Path(bootstrap.__file__).read_text(encoding="utf-8")
    assert "entry_recovery" not in text
    assert "force_executable_entry" not in text
    assert "EXECUTABLE_ENTRY" not in text


def test_synthesis_tree_has_no_entry_recovery_module() -> None:
    assert not (SRC / "synthesis" / "entry_recovery.py").exists()


def test_orchestration_does_not_import_recovery() -> None:
    for path in (SRC / "orchestration").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "entry_recovery" not in text
        assert "force_executable_entry" not in text


def test_handcrafted_baseline_lives_outside_synthesis() -> None:
    baseline = ROOT / "baselines" / "handcrafted_recovery_baseline.py"
    assert baseline.exists()
    text = baseline.read_text(encoding="utf-8")
    assert "NOT part of the synthesis loop" in text or "never be imported" in text.lower()


def test_architect_coerce_does_not_default_target_to_search() -> None:
    from evrptw_autolab.agents.base import coerce_schema_payload

    data = coerce_schema_payload("ArchitectPlan", {"hypothesis": "try something"})
    assert "target" not in data
    assert "agents_to_activate" not in data
