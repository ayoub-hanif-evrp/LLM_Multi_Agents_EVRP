"""Bezzi & Ceselli EVRP-MRT (multiple recharging technologies).

Loads instance XML only. Published solution XML under Solutions/ is never used
to construct algorithms — it may be read later for reporting only.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from evrptw_autolab.problem.datasets.common import (
    float_child,
    require_unique_ids,
    sha256_file,
    text_child,
)
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    VehicleTypeV2,
)

BEZZI_ROOT = Path("dataset/Bezzi & Ceselli EVRP-MRT")
_KIND = {0: "depot", 1: "customer", 2: "station"}


def bezzi_capabilities() -> CapabilityFlags:
    return CapabilityFlags(
        time_windows=False,  # not present in raw instance XML inspected
        capacity=True,
        battery=True,
        partial_recharge=True,
        multiple_charge_technologies=True,
        matrix_distances=True,
        euclidean_distances=False,
        max_route_duration=True,
        station_revisits_allowed=True,
    )


def discover_bezzi(root: Path | str | None = None) -> tuple[Path, ...]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[4] / BEZZI_ROOT
    # Never treat Solutions/*.xml as instances.
    return tuple(sorted(base.glob("**/Instances/*.xml"), key=lambda p: str(p).lower()))


def load_bezzi(path: Path | str) -> ProblemSpecV2:
    path = Path(path)
    if "Solutions" in path.parts:
        raise ValueError(f"refusing to load published solution as instance: {path}")
    tree = ET.parse(path)
    root = tree.getroot()
    info = root.find("info")
    name = text_child(info, "name") if info is not None else path.stem
    instance_id = path.stem if path.stem else (name or "bezzi")

    network = root.find("network")
    if network is None:
        raise ValueError(f"{path}: missing <network>")

    nodes: list[NodeV2] = []
    depot_ids: list[str] = []
    for node_el in network.findall("./nodes/node"):
        nid = str(node_el.get("id"))
        type_code = int(node_el.get("type", "-1"))
        if type_code not in _KIND:
            raise ValueError(f"{path}: unsupported node type {type_code}")
        kind_name = _KIND[type_code]
        x = float_child(node_el, "cx")
        y = float_child(node_el, "cy")
        station_techs: tuple[str, ...] = ()
        custom = node_el.find("custom")
        if custom is not None:
            has_tech = text_child(custom, "has_tech")
            if has_tech is not None:
                station_techs = (has_tech,)
        if kind_name == "depot":
            node_kind: Literal["depot", "customer", "station"] = "depot"
        elif kind_name == "customer":
            node_kind = "customer"
        else:
            node_kind = "station"
        nodes.append(
            NodeV2(
                id=nid,
                kind=node_kind,
                x=x,
                y=y,
                charge_technologies=station_techs,
                metadata={"has_tech": station_techs[0]} if station_techs else {},
            )
        )
        if node_kind == "depot":
            depot_ids.append(nid)
    require_unique_ids([n.id for n in nodes], label="node")
    if not depot_ids:
        raise ValueError(f"{path}: missing depot")

    # Explicit arc attributes (do not invent Euclidean substitution).
    travel: dict[str, dict[str, float]] = {}
    energy: dict[str, dict[str, float]] = {}
    links = network.find("links")
    if links is None or len(list(links.findall("link"))) == 0:
        raise ValueError(f"{path}: missing explicit <links> matrix")
    for link in links.findall("link"):
        head = str(link.get("head"))
        tail = str(link.get("tail"))
        travel.setdefault(head, {})[tail] = float_child(link, "travel_time")
        energy.setdefault(head, {})[tail] = float_child(link, "energy_consumption")

    fleet = root.find("fleet")
    if fleet is None:
        raise ValueError(f"{path}: missing <fleet>")
    profiles = fleet.findall("vehicle_profile")
    if not profiles:
        raise ValueError(f"{path}: no vehicle_profile")
    vehicle_types: list[VehicleTypeV2] = []
    availability: dict[str, int] = {}
    for profile in profiles:
        type_id = f"type_{profile.get('type', '0')}"
        number = int(profile.get("number") or 1)
        capacity = float_child(profile, "capacity")
        max_travel = float_child(profile, "max_travel_time")
        dep = text_child(profile, "departure_node")
        arr = text_child(profile, "arrival_node")
        custom = profile.find("custom")
        if custom is None:
            raise ValueError(f"{path}: vehicle missing custom battery/techs")
        battery = float_child(custom, "battery_capacity")
        tech_params: dict[str, dict[str, float]] = {}
        for func in custom.findall("./charging_techs/function"):
            tech = str(func.get("has_tech"))
            tech_params[tech] = {
                "gamma": float_child(func, "gamma"),
                "rho": float_child(func, "rho"),
            }
        if not tech_params:
            raise ValueError(f"{path}: vehicle has no charging_techs")
        vehicle_types.append(
            VehicleTypeV2(
                type_id=type_id,
                capacity=capacity,
                battery_capacity=battery,
                consumption_rate=None,  # energy from matrix, not rate*distance
                velocity=None,
                is_electric=True,
                metadata={
                    "max_travel_time": max_travel,
                    "departure_node": dep,
                    "arrival_node": arr,
                    "charging_techs": tech_params,
                },
            )
        )
        availability[type_id] = number

    # Attach request quantities / service times to customer (and station/depot) nodes.
    qty: dict[str, float] = {}
    service: dict[str, float] = {}
    requests_el = root.find("requests")
    if requests_el is not None:
        for req in requests_el.findall("request"):
            node_id = str(req.get("node"))
            qty[node_id] = float_child(req, "quantity")
            service[node_id] = float_child(req, "service_time")

    updated: list[NodeV2] = []
    for node in nodes:
        updated.append(
            NodeV2(
                id=node.id,
                kind=node.kind,
                x=node.x,
                y=node.y,
                demand=qty.get(node.id, 0.0),
                service_time=service.get(node.id, 0.0),
                partner_id=node.partner_id,
                charge_technologies=node.charge_technologies,
                recharging_rate=node.recharging_rate,
                metadata=dict(node.metadata),
            )
        )

    customers = [n for n in updated if n.kind == "customer"]
    if not customers:
        raise ValueError(f"{path}: no customers")

    return ProblemSpecV2(
        instance_id=instance_id,
        family="bezzi",
        capabilities=bezzi_capabilities(),
        nodes=tuple(updated),
        vehicle_types=tuple(vehicle_types),
        depot_ids=tuple(depot_ids),
        fleet_availability=availability,
        objective="minimize_original_cost",
        metadata={
            "source_path": str(path),
            "source_sha256": sha256_file(path),
            "publication": "Bezzi & Ceselli EVRP-MRT",
            "travel_time_matrix": travel,
            "energy_matrix": energy,
            "dataset_subset": next((p for p in path.parts if p.startswith("Dataset_")), None),
            "solutions_excluded": True,
        },
    )
