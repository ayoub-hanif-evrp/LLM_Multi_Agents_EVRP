"""Goeke PDPTW-EV Solomon-like text instances with pickup/delivery pairing."""
from __future__ import annotations

import re
from pathlib import Path

from evrptw_autolab.problem.datasets.common import require_unique_ids, sha256_file
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RequestV2,
    VehicleTypeV2,
)

GOEKE_ROOT = Path("dataset/goeke-2018")
_PARAM = re.compile(r"^(?P<label>[^:]+)\s*:\s*(?P<value>.+)\s*$")


def goeke_capabilities() -> CapabilityFlags:
    return CapabilityFlags(
        time_windows=True,
        capacity=True,
        battery=True,
        full_recharge=True,
        partial_recharge=True,
        pickup_delivery=True,
        euclidean_distances=True,
        station_revisits_allowed=True,
    )


def discover_goeke(root: Path | str | None = None) -> tuple[Path, ...]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[4] / GOEKE_ROOT
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


def _parse_params(lines: list[str]) -> dict[str, float]:
    aliases = {
        "vehicle battery capacity": "battery",
        "vehicle freight capacity": "capacity",
        "battery consumption rate": "consumption",
        "inverse recharging rate": "inverse_refuel",
        "average velocity": "velocity",
    }
    out: dict[str, float] = {}
    for line in lines:
        match = _PARAM.match(line.strip())
        if not match:
            continue
        key = aliases.get(match["label"].strip().lower())
        if key:
            out[key] = float(match["value"].strip())
    return out


def load_goeke(path: Path | str) -> ProblemSpecV2:
    path = Path(path)
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if lines and lines[0].lower().startswith("stringid"):
        lines = lines[1:]

    node_lines: list[str] = []
    param_lines: list[str] = []
    in_params = False
    for line in lines:
        if _PARAM.match(line):
            in_params = True
        if in_params:
            param_lines.append(line)
        else:
            node_lines.append(line)

    params = _parse_params(param_lines)
    required = {"battery", "capacity", "consumption", "inverse_refuel", "velocity"}
    missing = required - params.keys()
    if missing:
        raise ValueError(f"{path}: missing vehicle params {sorted(missing)}")

    nodes: list[NodeV2] = []
    depot_ids: list[str] = []
    for line in node_lines:
        fields = line.split()
        if len(fields) < 9:
            raise ValueError(f"{path}: malformed node line: {line}")
        node_id, raw_kind = fields[0], fields[1].lower()
        x, y, demand, ready, due, service = map(float, fields[2:8])
        partner_raw = fields[8]
        partner = None if partner_raw in {"0", "0.0"} else partner_raw
        if raw_kind == "d":
            kind = "depot"
            depot_ids.append(node_id)
        elif raw_kind == "f":
            kind = "station"
        elif raw_kind == "cp":
            kind = "pickup"
        elif raw_kind == "cd":
            kind = "delivery"
        else:
            raise ValueError(f"{path}: unknown node type {raw_kind!r}")
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
                partner_id=partner,
            )
        )
    require_unique_ids([n.id for n in nodes], label="node")
    if len(depot_ids) != 1:
        raise ValueError(f"{path}: expected one depot, found {depot_ids}")

    pickups = {n.id: n for n in nodes if n.kind == "pickup"}
    deliveries = {n.id: n for n in nodes if n.kind == "delivery"}
    if len(pickups) != len(deliveries):
        raise ValueError(
            f"{path}: pickup/delivery count mismatch {len(pickups)} vs {len(deliveries)}"
        )

    requests: list[RequestV2] = []
    seen_pairs: set[tuple[str, str]] = set()
    for pid, pnode in pickups.items():
        did = pnode.partner_id
        if did is None or did not in deliveries:
            raise ValueError(f"{path}: pickup {pid} missing delivery partner")
        dnode = deliveries[did]
        if dnode.partner_id != pid:
            raise ValueError(f"{path}: asymmetric partners {pid}<->{did}")
        if pnode.demand <= 0:
            raise ValueError(f"{path}: pickup {pid} demand must be positive")
        if abs(pnode.demand + dnode.demand) > 1e-9:
            raise ValueError(f"{path}: demand not conserved for pair {pid}/{did}")
        pair = (pid, did)
        if pair in seen_pairs:
            raise ValueError(f"{path}: duplicate pair {pair}")
        seen_pairs.add(pair)
        requests.append(
            RequestV2(
                request_id=f"{pid}->{did}",
                pickup_id=pid,
                delivery_id=did,
                demand=pnode.demand,
                same_vehicle=True,
            )
        )

    vehicle = VehicleTypeV2(
        type_id="EV",
        capacity=params["capacity"],
        battery_capacity=params["battery"],
        consumption_rate=params["consumption"],
        velocity=params["velocity"],
        is_electric=True,
        metadata={"inverse_refuel_rate": params["inverse_refuel"]},
    )

    return ProblemSpecV2(
        instance_id=path.stem,
        family="goeke",
        capabilities=goeke_capabilities(),
        nodes=tuple(nodes),
        vehicle_types=(vehicle,),
        depot_ids=tuple(depot_ids),
        requests=tuple(requests),
        fleet_availability={"EV": 10**9},
        # Goeke (EJOR 2019): minimize fleet size, then travel distance.
        # The string matches evaluator objective_key (vehicles, distance).
        objective="minimize_vehicles_then_distance",
        metadata={
            "source_path": str(path),
            "source_sha256": sha256_file(path),
            "publication": "Goeke PDPTW-EV",
            "inverse_refuel_rate": params["inverse_refuel"],
        },
    )
