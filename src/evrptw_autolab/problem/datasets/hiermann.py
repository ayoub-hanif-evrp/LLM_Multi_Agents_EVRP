"""Hiermann et al. heterogeneous electric fleet with time windows (set 1).

Does not collapse the fleet to homogeneous all-electric vehicles.
"""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.problem.datasets.common import require_unique_ids, sha256_file
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    VehicleTypeV2,
)

HIERMANN_ROOT = Path("dataset/hiermann-et-al-2017-set-1")


def hiermann_capabilities() -> CapabilityFlags:
    return CapabilityFlags(
        time_windows=True,
        capacity=True,
        battery=True,
        full_recharge=True,
        partial_recharge=True,
        heterogeneous_fleet=True,
        conventional_vehicles=True,
        hybrid_vehicles=True,
        euclidean_distances=True,
        station_revisits_allowed=True,
    )


def discover_hiermann(root: Path | str | None = None) -> tuple[Path, ...]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[4] / HIERMANN_ROOT
    return tuple(
        sorted(
            (
                p
                for p in base.glob("*.txt")
                if p.name.lower() not in {"readme.txt", "manifest.txt", "license.txt"}
            ),
            key=lambda p: p.name.lower(),
        )
    )


def load_hiermann(path: Path | str) -> ProblemSpecV2:
    path = Path(path)
    raw_lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in raw_lines if ln]
    if not lines:
        raise ValueError(f"{path}: empty file")

    # Sections: nodes header, vehicle header ("id name type ..."), costOf header.
    node_start = 0
    if lines[0].lower().startswith("stringid"):
        node_start = 1

    vehicle_header_idx = None
    cost_header_idx = None
    for i, line in enumerate(lines):
        low = line.lower()
        if low.startswith("id name type"):
            vehicle_header_idx = i
        elif low.startswith("costof"):
            cost_header_idx = i
    if vehicle_header_idx is None:
        raise ValueError(f"{path}: missing vehicle type table")
    if cost_header_idx is None:
        raise ValueError(f"{path}: missing costOf table")

    node_lines = lines[node_start:vehicle_header_idx]
    vehicle_lines = lines[vehicle_header_idx + 1 : cost_header_idx]
    cost_lines = lines[cost_header_idx + 1 :]

    nodes: list[NodeV2] = []
    depot_ids: list[str] = []
    for line in node_lines:
        fields = line.split()
        if len(fields) < 9:
            raise ValueError(f"{path}: malformed node line: {line}")
        node_id, raw_kind = fields[0], fields[1].lower()
        x, y, demand, ready, due, service, recharge = map(float, fields[2:9])
        if raw_kind == "d":
            kind = "depot"
            depot_ids.append(node_id)
        elif raw_kind == "f":
            kind = "station"
        elif raw_kind == "c":
            kind = "customer"
        else:
            raise ValueError(f"{path}: unknown kind {raw_kind}")
        nodes.append(
            NodeV2(
                id=node_id,
                kind=kind,  # type: ignore[arg-type]
                x=x,
                y=y,
                demand=demand,
                ready_time=ready,
                due_time=due,
                service_time=service,
                recharging_rate=recharge if kind == "station" else None,
            )
        )
    require_unique_ids([n.id for n in nodes], label="node")
    if len(depot_ids) != 1:
        raise ValueError(f"{path}: expected one depot, found {depot_ids}")
    if not any(n.kind == "customer" for n in nodes):
        raise ValueError(f"{path}: no customers")

    vehicles: list[VehicleTypeV2] = []
    for line in vehicle_lines:
        fields = line.split()
        if len(fields) < 7:
            raise ValueError(f"{path}: malformed vehicle line: {line}")
        type_id = fields[0]
        # name may contain '|' without spaces: Small|ICEV
        name = fields[1]
        vtype = fields[2].upper()
        capacity, fuel, battery, energy, cost = map(float, fields[3:8])
        is_icev = vtype == "ICEV"
        is_phev = vtype == "PHEV"
        is_bev = vtype == "BEV"
        if not (is_icev or is_phev or is_bev):
            raise ValueError(f"{path}: unknown vehicle propulsion {vtype}")
        vehicles.append(
            VehicleTypeV2(
                type_id=type_id,
                capacity=capacity,
                battery_capacity=None if is_icev else battery,
                consumption_rate=None if is_icev else energy,
                velocity=None,  # not stated in file; do not invent
                is_electric=is_bev or is_phev,
                is_conventional=is_icev,
                is_hybrid=is_phev,
                fixed_cost=cost,
                metadata={
                    "name": name,
                    "propulsion": vtype,
                    "fuel_consumption_rate": fuel,
                    "battery_capacity_raw": battery,
                    "energy_consumption_rate": energy,
                    "travel_time_model": "unspecified_in_file",
                },
            )
        )
    if not vehicles:
        raise ValueError(f"{path}: empty vehicle table")

    energy_prices: dict[str, float] = {}
    for line in cost_lines:
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"{path}: malformed costOf line: {line}")
        energy_prices[parts[0]] = float(parts[1])
    if "fossil-fuel" not in energy_prices or "electricity" not in energy_prices:
        raise ValueError(f"{path}: costOf must include fossil-fuel and electricity")

    return ProblemSpecV2(
        instance_id=path.stem,
        family="hiermann",
        capabilities=hiermann_capabilities(),
        nodes=tuple(nodes),
        vehicle_types=tuple(vehicles),
        depot_ids=tuple(depot_ids),
        fleet_availability={v.type_id: 10**9 for v in vehicles},
        objective="minimize_fleet_and_energy_cost",
        metadata={
            "source_path": str(path),
            "source_sha256": sha256_file(path),
            "publication": "Hiermann et al. H2E-FTW set 1",
            "energy_prices": energy_prices,
            "note": (
                "Velocity / travel-time scaling is not present in the raw file; "
                "evaluator must apply the paper's documented distance-time convention "
                "explicitly rather than inventing a speed."
            ),
        },
    )
