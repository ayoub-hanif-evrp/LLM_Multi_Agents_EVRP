"""Montoya et al. E-VRP with nonlinear charging functions (XML).

Preserves piecewise-linear charging breakpoints. Does not replace nonlinear
charging with constant-rate charging.
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

MONTOYA_ROOT = Path("dataset/montoya-et-al-2017")

# Montoya node type codes (dataset readme).
_KIND = {0: "depot", 1: "customer", 2: "station"}


def montoya_capabilities() -> CapabilityFlags:
    return CapabilityFlags(
        capacity=False,  # no freight capacity in these instances
        battery=True,
        partial_recharge=True,
        nonlinear_charging=True,
        euclidean_distances=True,
        max_route_duration=True,
        station_revisits_allowed=True,
        time_windows=False,
    )


def discover_montoya(root: Path | str | None = None) -> tuple[Path, ...]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[4] / MONTOYA_ROOT
    return tuple(sorted(base.glob("*.xml"), key=lambda p: p.name.lower()))


def load_montoya(path: Path | str) -> ProblemSpecV2:
    path = Path(path)
    tree = ET.parse(path)
    root = tree.getroot()
    info = root.find("info")
    name = text_child(info, "name") if info is not None else path.stem
    instance_id = name or path.stem

    network = root.find("network")
    if network is None:
        raise ValueError(f"{path}: missing <network>")
    decimals_raw = text_child(network, "decimals", "14")
    decimals = int(decimals_raw) if decimals_raw else 14

    nodes: list[NodeV2] = []
    depot_ids: list[str] = []
    for node_el in network.findall("./nodes/node"):
        nid = str(node_el.get("id"))
        type_code = int(node_el.get("type", "-1"))
        if type_code not in _KIND:
            raise ValueError(f"{path}: unsupported node type {type_code} for id={nid}")
        kind_name = _KIND[type_code]
        x = float_child(node_el, "cx")
        y = float_child(node_el, "cy")
        cs_type = None
        custom = node_el.find("custom")
        if custom is not None:
            cs_type = text_child(custom, "cs_type")
        techs = (cs_type,) if cs_type else ()
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
                charge_technologies=techs,
                metadata={"cs_type": cs_type} if cs_type else {},
            )
        )
        if node_kind == "depot":
            depot_ids.append(nid)
    require_unique_ids([n.id for n in nodes], label="node")
    if len(depot_ids) != 1:
        raise ValueError(f"{path}: expected exactly one depot, found {depot_ids}")

    fleet = root.find("fleet")
    if fleet is None:
        raise ValueError(f"{path}: missing <fleet>")
    profiles = fleet.findall("vehicle_profile")
    if len(profiles) != 1:
        raise ValueError(f"{path}: expected one vehicle_profile, found {len(profiles)}")
    profile = profiles[0]
    speed = float_child(profile, "speed_factor")
    max_travel = float_child(profile, "max_travel_time")
    custom = profile.find("custom")
    if custom is None:
        raise ValueError(f"{path}: missing vehicle custom energy block")
    consumption = float_child(custom, "consumption_rate")
    battery = float_child(custom, "battery_capacity")
    charging_functions: dict[str, list[dict[str, float]]] = {}
    for func in custom.findall("./charging_functions/function"):
        cs_type = str(func.get("cs_type") or "")
        if not cs_type:
            raise ValueError(f"{path}: charging function missing cs_type")
        breakpoints: list[dict[str, float]] = []
        for bp in func.findall("breakpoint"):
            breakpoints.append(
                {
                    "battery_level": float_child(bp, "battery_level"),
                    "charging_time": float_child(bp, "charging_time"),
                }
            )
        if len(breakpoints) < 2:
            raise ValueError(f"{path}: charging function {cs_type} needs >=2 breakpoints")
        # Monotonicity: battery and time nondecreasing.
        for i in range(1, len(breakpoints)):
            if breakpoints[i]["battery_level"] < breakpoints[i - 1]["battery_level"]:
                raise ValueError(f"{path}: non-monotone battery in {cs_type}")
            if breakpoints[i]["charging_time"] < breakpoints[i - 1]["charging_time"]:
                raise ValueError(f"{path}: non-monotone time in {cs_type}")
        charging_functions[cs_type] = breakpoints

    vehicle = VehicleTypeV2(
        type_id="EV0",
        capacity=0.0,
        battery_capacity=battery,
        consumption_rate=consumption,
        velocity=speed,
        is_electric=True,
        metadata={
            "max_travel_time": max_travel,
            "charging_functions": charging_functions,
            "units": {"distance": "km", "speed": "km/h", "energy": "Wh", "time": "h"},
        },
    )

    service_by_node: dict[str, float] = {}
    requests_el = root.find("requests")
    if requests_el is not None:
        for req in requests_el.findall("request"):
            node_id = str(req.get("node"))
            service_by_node[node_id] = float_child(req, "service_time")
    updated: list[NodeV2] = []
    for node in nodes:
        if node.id in service_by_node:
            updated.append(
                NodeV2(
                    id=node.id,
                    kind=node.kind,
                    x=node.x,
                    y=node.y,
                    demand=node.demand,
                    ready_time=node.ready_time,
                    due_time=node.due_time,
                    service_time=service_by_node[node.id],
                    partner_id=node.partner_id,
                    charge_technologies=node.charge_technologies,
                    recharging_rate=node.recharging_rate,
                    metadata=dict(node.metadata),
                )
            )
        else:
            updated.append(node)

    # Station types referenced by nodes must have charging functions.
    for node in updated:
        if node.kind == "station":
            for tech in node.charge_technologies:
                if tech not in charging_functions:
                    raise ValueError(f"{path}: station {node.id} cs_type={tech} has no charging function")

    return ProblemSpecV2(
        instance_id=instance_id,
        family="montoya",
        capabilities=montoya_capabilities(),
        nodes=tuple(updated),
        vehicle_types=(vehicle,),
        depot_ids=tuple(depot_ids),
        fleet_availability={"EV0": 10**9},
        objective="minimize_total_time",
        metadata={
            "source_path": str(path),
            "source_sha256": sha256_file(path),
            "euclidean_decimals": decimals,
            "publication": "Montoya et al. 2017 E-VRP-NL",
            "max_travel_time": max_travel,
            "charging_functions": charging_functions,
        },
    )
