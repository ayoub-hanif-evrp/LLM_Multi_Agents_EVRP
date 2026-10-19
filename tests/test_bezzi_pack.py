"""Bezzi 10-N10 is fleet-feasible once short routes are packed explicitly."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.backbone.bezzi_pack import pack_bezzi_fleet
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi

ROOT = Path(__file__).resolve().parents[1]
INSTANCE = (
    ROOT
    / "dataset"
    / "Bezzi & Ceselli EVRP-MRT"
    / "Dataset_B"
    / "Instances"
    / "10-N10.xml"
)


def test_bezzi_10n10_pack_covers_every_customer() -> None:
    spec = load_bezzi(INSTANCE)
    packed = pack_bezzi_fleet(spec)
    assert packed is not None
    report = evaluate(spec, packed)
    assert report.feasible, report.explanation
    limit = spec.fleet_availability[spec.vehicle_types[0].type_id]
    assert len(packed.routes) <= limit
    served = {
        stop.node_id
        for route in packed.routes
        for stop in route
        if spec.node_map[stop.node_id].kind == "customer"
    }
    assert served == {node.id for node in spec.nodes if node.kind == "customer"}
    assert report.objective is not None and report.objective > 0.0
