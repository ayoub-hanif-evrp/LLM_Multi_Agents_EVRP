"""Tiny private EVRPTW micro-instances for P1 build gates. Not Schneider cases."""
from __future__ import annotations

import tempfile
from pathlib import Path

from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.problem.types import EVRPTWInstance


def _write_solomon(path: Path, body: str) -> EVRPTWInstance:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != body:
        path.write_text(body, encoding="utf-8")
    inst = load_instance(path)
    meta = dict(inst.metadata)
    meta.update({"private": True, "lab_micro": True, "family": "MICRO"})
    return EVRPTWInstance(
        instance_id=inst.instance_id,
        nodes=inst.nodes,
        vehicle=inst.vehicle,
        depot_id=inst.depot_id,
        metadata=meta,
    )


def micro_g1_one_customer() -> EVRPTWInstance:
    """depot→C1→depot is feasible without charging (large battery)."""
    body = """\
StringID   Type       x          y          demand     ReadyTime  DueDate    ServiceTime
D0         d          0.0        0.0        0.0        0.0        1000.0     0.0
S0         f          5.0        0.0        0.0        0.0        1000.0     0.0
C1         c          1.0        0.0        1.0        0.0        1000.0     0.0

Q Vehicle fuel tank capacity /100.0/
C Vehicle load capacity /100.0/
r fuel consumption rate /1.0/
g inverse refueling rate /1.0/
v average Velocity /1.0/
"""
    root = Path(tempfile.gettempdir()) / "evrptw_autolab_micro"
    return _write_solomon(root / "micro_g1_one.txt", body)


def micro_g2_needs_charge() -> EVRPTWInstance:
    """Direct depot→C1→depot exceeds battery; a station visit makes it feasible."""
    # Distance depot→C1 = 60, C1→depot = 60 → 120 energy at rate 1.0 with Q=100.
    # Station near midpoint: depot→S0 (30) + S0→C1 (30) + C1→depot (60) with full recharge at S0.
    body = """\
StringID   Type       x          y          demand     ReadyTime  DueDate    ServiceTime
D0         d          0.0        0.0        0.0        0.0        10000.0    0.0
S0         f          30.0       0.0        0.0        0.0        10000.0    0.0
C1         c          60.0       0.0        1.0        0.0        10000.0    0.0

Q Vehicle fuel tank capacity /100.0/
C Vehicle load capacity /100.0/
r fuel consumption rate /1.0/
g inverse refueling rate /0.1/
v average Velocity /1.0/
"""
    root = Path(tempfile.gettempdir()) / "evrptw_autolab_micro"
    inst = _write_solomon(root / "micro_g2_charge.txt", body)
    meta = dict(inst.metadata)
    meta["requires_charge"] = True
    return EVRPTWInstance(
        instance_id="micro_g2_charge",
        nodes=inst.nodes,
        vehicle=inst.vehicle,
        depot_id=inst.depot_id,
        metadata=meta,
    )


def micro_g3_two_customers() -> EVRPTWInstance:
    """Two nearby customers; dedicated or joint routes both feasible without charging."""
    body = """\
StringID   Type       x          y          demand     ReadyTime  DueDate    ServiceTime
D0         d          0.0        0.0        0.0        0.0        1000.0     0.0
S0         f          5.0        0.0        0.0        0.0        1000.0     0.0
C1         c          1.0        0.0        1.0        0.0        1000.0     0.0
C2         c          0.0        1.0        1.0        0.0        1000.0     0.0

Q Vehicle fuel tank capacity /100.0/
C Vehicle load capacity /100.0/
r fuel consumption rate /1.0/
g inverse refueling rate /1.0/
v average Velocity /1.0/
"""
    root = Path(tempfile.gettempdir()) / "evrptw_autolab_micro"
    inst = _write_solomon(root / "micro_g3_two.txt", body)
    return EVRPTWInstance(
        instance_id="micro_g3_two",
        nodes=inst.nodes,
        vehicle=inst.vehicle,
        depot_id=inst.depot_id,
        metadata={**dict(inst.metadata), "private": True, "lab_micro": True, "family": "MICRO"},
    )
