"""Parsers for all five VoltForge 2.0 benchmark families."""
from __future__ import annotations

from pathlib import Path

import pytest

from evrptw_autolab.problem.datasets.bezzi import discover_bezzi, load_bezzi
from evrptw_autolab.problem.datasets.goeke import discover_goeke, load_goeke
from evrptw_autolab.problem.datasets.hiermann import discover_hiermann, load_hiermann
from evrptw_autolab.problem.datasets.montoya import discover_montoya, load_montoya
from evrptw_autolab.problem.datasets.registry import audit_all
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.schneider import SCHNEIDER_ROOT, discover_instances

ROOT = Path(__file__).resolve().parents[1]


def test_load_all_montoya() -> None:
    paths = discover_montoya(ROOT / "dataset" / "montoya-et-al-2017")
    assert len(paths) == 120
    # Full load of all instances (XML is small).
    for path in paths:
        spec = load_montoya(path)
        assert spec.family == "montoya"
        assert spec.capabilities.nonlinear_charging
        assert spec.capabilities.partial_recharge
        assert not spec.capabilities.time_windows
        assert len(spec.depot_ids) == 1
        assert any(n.kind == "customer" for n in spec.nodes)
        assert "charging_functions" in spec.vehicle_types[0].metadata


def test_montoya_preserves_multi_tech_curve() -> None:
    path = ROOT / "dataset" / "montoya-et-al-2017" / "tc0c160s16cf2.xml"
    spec = load_montoya(path)
    funcs = spec.metadata["charging_functions"]
    assert {"slow", "normal", "fast"} <= set(funcs)
    for breakpoints in funcs.values():
        assert len(breakpoints) >= 2
        batteries = [bp["battery_level"] for bp in breakpoints]
        assert batteries == sorted(batteries)


def test_load_all_bezzi_instances_not_solutions() -> None:
    paths = discover_bezzi(ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT")
    assert len(paths) == 66
    assert all("Instances" in p.parts for p in paths)
    assert all("Solutions" not in p.parts for p in paths)
    for path in paths:
        spec = load_bezzi(path)
        assert spec.family == "bezzi"
        assert spec.capabilities.multiple_charge_technologies
        assert spec.capabilities.matrix_distances
        assert "travel_time_matrix" in spec.metadata
        assert "energy_matrix" in spec.metadata
        assert any(n.kind == "customer" for n in spec.nodes)


def test_bezzi_refuses_solution_xml() -> None:
    sol = next((ROOT / "dataset" / "Bezzi & Ceselli EVRP-MRT").glob("**/Solutions/*.xml"))
    with pytest.raises(ValueError, match="solution"):
        load_bezzi(sol)


def test_load_all_goeke() -> None:
    paths = discover_goeke(ROOT / "dataset" / "goeke-2018")
    assert len(paths) == 92
    for path in paths:
        spec = load_goeke(path)
        assert spec.family == "goeke"
        assert spec.capabilities.pickup_delivery
        assert spec.requests
        for req in spec.requests:
            assert req.pickup_id in spec.node_map
            assert req.delivery_id in spec.node_map
            assert spec.node_map[req.pickup_id].kind == "pickup"
            assert spec.node_map[req.delivery_id].kind == "delivery"


def test_goeke_precedence_pair_example() -> None:
    spec = load_goeke(ROOT / "dataset" / "goeke-2018" / "c101C6.txt")
    pairs = {(r.pickup_id, r.delivery_id) for r in spec.requests}
    assert ("C12", "C30") in pairs
    assert ("C64", "C85") in pairs


def test_load_all_hiermann() -> None:
    paths = discover_hiermann(ROOT / "dataset" / "hiermann-et-al-2017-set-1")
    assert len(paths) == 56
    for path in paths:
        spec = load_hiermann(path)
        assert spec.family == "hiermann"
        assert spec.capabilities.heterogeneous_fleet
        assert spec.capabilities.conventional_vehicles
        assert spec.capabilities.hybrid_vehicles
        props = {v.metadata.get("propulsion") for v in spec.vehicle_types}
        assert {"ICEV", "PHEV", "BEV"} <= props
        assert "fossil-fuel" in spec.metadata["energy_prices"]


def test_schneider_v2_adapter() -> None:
    path = discover_instances(ROOT / SCHNEIDER_ROOT)[0]
    spec = load_schneider_v2(path)
    assert spec.family == "schneider"
    assert spec.capabilities.full_recharge
    assert spec.capabilities.time_windows


def test_audit_all_families_validated() -> None:
    audits = {a.family_id: a for a in audit_all(dataset_root=ROOT / "dataset")}
    for fam in ("schneider", "montoya", "bezzi", "goeke", "hiermann"):
        assert audits[fam].parse_status == "validated", (
            fam,
            audits[fam].parse_note,
            audits[fam].warnings[:3],
        )
    assert audits["schneider"].loaded_count == 92
    assert audits["montoya"].loaded_count == 120
    assert audits["bezzi"].loaded_count == 66
    assert audits["goeke"].loaded_count == 92
    assert audits["hiermann"].loaded_count == 56
