"""Shared Solomon-style EVRPTW text parser (used by Schneider primary dataset)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from evocharge.domain.instance import Instance
from evocharge.domain.node import Node, NodeKind
from evocharge.domain.vehicle import Vehicle

_NODE_TYPE_MAP: dict[str, NodeKind] = {
    "d": "depot",
    "c": "customer",
    "f": "station",
}

_PARAM_RE = re.compile(
    r"^(?P<label>.+?)\s*/(?P<value>[^/]+)/\s*$"
)
_FILENAME_RE = re.compile(
    r"solomon_dataset_(?P<id>\d+)_(?P<family>C|R|RC)_(?P<tw>narrow|wide)_(?P<ts>\d+)\.txt$",
    re.IGNORECASE,
)


def parse_filename_metadata(path: Path | str) -> dict[str, Any]:
    name = Path(path).name
    match = _FILENAME_RE.search(name)
    if not match:
        return {"filename": name}
    return {
        "filename": name,
        "file_instance_id": match.group("id"),
        "instance_type": match.group("family").upper(),
        "tw_regime": match.group("tw").lower(),
        "timestamp": match.group("ts"),
        "family_key": f"{match.group('family').upper()}_{match.group('tw').lower()}",
    }


def _parse_float(value: str) -> float:
    return float(value.strip())


def _parse_param_block(lines: list[str]) -> dict[str, float]:
    params: dict[str, float] = {}
    aliases = {
        "q vehicle fuel tank capacity": "Q",
        "c vehicle load capacity": "C",
        "r fuel consumption rate": "r",
        "g inverse refueling rate": "g",
        "v average velocity": "v",
        "gv charging speed": "gv",
    }
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("-"):
            continue
        match = _PARAM_RE.match(stripped)
        if not match:
            continue
        label = match.group("label").strip().lower()
        key = aliases.get(label)
        if key is None:
            # Also accept short keys like "Q Vehicle..."
            for _alias_key, short in aliases.items():
                if label.startswith(short.lower()) or short.lower() in label:
                    key = short
                    break
        if key is None:
            continue
        params[key] = _parse_float(match.group("value"))
    return params


def _parse_metadata_footer(lines: list[str]) -> dict[str, Any]:
    meta: dict[str, Any] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        match = _PARAM_RE.match(stripped)
        if not match:
            continue
        key = match.group("label").strip()
        raw = match.group("value").strip()
        if raw.startswith("[") and raw.endswith("]"):
            inner = raw[1:-1].strip()
            if not inner:
                meta[key] = []
            else:
                parts = [p.strip() for p in inner.split(",")]
                try:
                    meta[key] = [float(p) for p in parts]
                except ValueError:
                    meta[key] = parts
        else:
            try:
                if "." in raw:
                    meta[key] = float(raw)
                else:
                    meta[key] = int(raw)
            except ValueError:
                meta[key] = raw
    return meta


def parse_evrptwd_solomon_text(
    text: str,
    source_path: Path | str | None = None,
    *,
    dataset_name: str = "Schneider_E-VRPTW",
) -> Instance:
    lines = text.splitlines()
    if not lines:
        raise ValueError("Empty instance file")

    # Skip header
    start = 0
    if lines[0].lower().startswith("stringid"):
        start = 1

    node_lines: list[str] = []
    param_lines: list[str] = []
    meta_lines: list[str] = []
    section = "nodes"
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("----"):
            section = "meta"
            continue
        if section == "nodes":
            # Parameter lines start with Q/C/r/g/v/gv labels
            if _PARAM_RE.match(stripped) and (
                stripped[0].lower() in {"q", "c", "r", "g", "v"}
                or stripped.lower().startswith("gv")
            ):
                section = "params"
                param_lines.append(stripped)
            else:
                node_lines.append(stripped)
        elif section == "params":
            if stripped.startswith("----"):
                section = "meta"
            else:
                param_lines.append(stripped)
        else:
            meta_lines.append(stripped)

    params = _parse_param_block(param_lines)
    required = ["Q", "C", "r", "v"]
    missing = [k for k in required if k not in params]
    if missing:
        raise ValueError(f"Missing vehicle parameters: {missing}")

    nodes: dict[str, Node] = {}
    depot_ids: list[str] = []
    customer_ids: list[str] = []
    station_ids: list[str] = []

    for line in node_lines:
        parts = line.split()
        if len(parts) < 8:
            raise ValueError(f"Malformed node line: {line}")
        string_id, type_code = parts[0], parts[1].lower()
        kind = _NODE_TYPE_MAP.get(type_code)
        if kind is None:
            raise ValueError(f"Unknown node type {type_code!r} in {line}")
        x, y, demand, ready, due, service = map(float, parts[2:8])
        node = Node(
            id=string_id,
            kind=kind,
            coordinates=(x, y),
            demand=demand,
            service_duration=service,
            ready_time=ready,
            due_time=due,
            metadata={"raw_type": type_code},
        )
        nodes[string_id] = node
        if kind == "depot":
            depot_ids.append(string_id)
        elif kind == "customer":
            customer_ids.append(string_id)
        else:
            station_ids.append(string_id)

    if len(depot_ids) != 1:
        raise ValueError(f"Expected exactly one depot, found {depot_ids}")

    file_meta = parse_filename_metadata(source_path) if source_path else {}
    footer = _parse_metadata_footer(meta_lines)
    instance_id = str(
        footer.get("instance_id")
        or file_meta.get("file_instance_id")
        or (Path(source_path).stem if source_path else "unknown")
    )

    # Align family keys from filename / footer
    instance_type = str(
        footer.get("instance_type") or file_meta.get("instance_type") or "UNKNOWN"
    ).upper()
    tw_regime = str(file_meta.get("tw_regime") or "unknown").lower()
    # Infer tw from filename already; footer may not include narrow/wide
    family_key = file_meta.get("family_key") or f"{instance_type}_{tw_regime}"

    vehicle = Vehicle(
        freight_capacity=params["C"],
        battery_capacity=params["Q"],
        initial_soc=params["Q"],
        terminal_soc_min=0.0,
        consumption_rate=params["r"],
        velocity=params["v"],
        inverse_refuel_rate=params.get("g"),
        charging_speed=params.get("gv"),
        metadata={"raw_params": params},
    )

    horizon = float(
        footer.get("instance_endTime (hour)")
        or nodes[depot_ids[0]].due_time
    )

    metadata: dict[str, Any] = {
        **file_meta,
        "footer": footer,
        "instance_type": instance_type,
        "tw_regime": tw_regime,
        "family_key": family_key,
        "source_path": str(source_path) if source_path else None,
        "raw_params": params,
    }

    return Instance(
        instance_id=instance_id,
        dataset_name=dataset_name,
        nodes=nodes,
        depot_id=depot_ids[0],
        customer_ids=tuple(customer_ids),
        station_ids=tuple(station_ids),
        vehicle=vehicle,
        horizon=horizon,
        metadata=metadata,
    )


def parse_evrptwd_solomon_file(path: Path | str) -> Instance:
    """Legacy alias; prefer ``parse_schneider_file`` for the primary dataset."""
    path = Path(path)
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return parse_evrptwd_solomon_text(text, source_path=path)
