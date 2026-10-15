"""VoltForge 2.0 dataset audit + ProblemSpecV2 vertical slice."""
from __future__ import annotations

from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.problem.datasets.registry import DATASET_SPECS, audit_all, audit_dataset
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    RouteStopV2,
    SolutionV2,
    schneider_capabilities,
)


def test_five_dataset_specs_registered() -> None:
    ids = {s.family_id for s in DATASET_SPECS}
    assert ids == {"schneider", "montoya", "bezzi", "goeke", "hiermann"}


def test_dataset_audit_inventory_counts() -> None:
    audits = {a.family_id: a for a in audit_all()}
    assert audits["schneider"].folder_exists
    assert audits["schneider"].instance_file_count == 92
    assert audits["montoya"].instance_file_count == 120
    # Bezzi: only Instances/*.xml (Solutions excluded).
    assert audits["bezzi"].instance_file_count == 66
    assert audits["goeke"].instance_file_count == 92
    assert audits["goeke"].raw_file_count == 93
    assert audits["hiermann"].instance_file_count == 56
    assert audits["hiermann"].raw_file_count == 57
    for fam in ("schneider", "montoya", "bezzi", "goeke", "hiermann"):
        assert audits[fam].parse_status == "validated", audits[fam].parse_note
        assert audits[fam].instance_files
        assert audits[fam].instance_files[0].sha256
        assert audits[fam].loaded_count == audits[fam].instance_file_count


def test_schneider_audit_hashes_stable() -> None:
    a = audit_dataset(next(s for s in DATASET_SPECS if s.family_id == "schneider"))
    assert a.parse_status == "validated"
    assert len({f.sha256 for f in a.instance_files}) == len(a.instance_files)


def test_solution_v2_legacy_roundtrip() -> None:
    routes = [["D0", "C1", "D0"], ["D0", "C2", "D0"]]
    sol = SolutionV2.from_legacy_routes(routes, vehicle_type_id="EV")
    assert sol.to_legacy_routes() == routes
    assert all(isinstance(s, RouteStopV2) for route in sol.routes for s in route)


def test_schneider_capability_flags() -> None:
    caps = schneider_capabilities()
    assert isinstance(caps, CapabilityFlags)
    assert caps.time_windows and caps.battery and caps.full_recharge
    assert not caps.pickup_delivery
    assert not caps.nonlinear_charging


def test_ollama_extract_message_parts_rejects_thinking_only() -> None:
    content, thinking = OllamaBackend.extract_message_parts(
        {"message": {"content": "", "thinking": "plan the solver"}}
    )
    assert content == ""
    assert "plan" in thinking
