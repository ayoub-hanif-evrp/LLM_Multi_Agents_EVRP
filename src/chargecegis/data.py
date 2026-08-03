"""Schneider E-VRPTW discovery and Solomon-format loading."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from chargecegis.problem import Instance, Node, Vehicle

SCHNEIDER_ROOT = Path("dataset/schneider/raw_instances")
_PARAM = re.compile(r"^(?P<label>.+?)\s*/(?P<value>[^/]+)/\s*$")
_FAMILY = re.compile(r"^(RC|C|R)[12]", re.IGNORECASE)


def discover_instances(root: Path | str = SCHNEIDER_ROOT) -> tuple[Path, ...]:
    """Return the 92 benchmark files, never the bundled readme."""
    paths = tuple(sorted(
        (path for path in Path(root).glob("*.txt") if path.name.lower() != "readme.txt"),
        key=lambda path: path.name.lower(),
    ))
    if len(paths) != 92:
        raise ValueError(f"Expected exactly 92 Schneider instances under {root}, found {len(paths)}")
    return paths


def _parameters(lines: list[str]) -> dict[str, float]:
    aliases = {
        "q vehicle fuel tank capacity": "Q", "c vehicle load capacity": "C",
        "r fuel consumption rate": "r", "g inverse refueling rate": "g",
        "v average velocity": "v",
    }
    result: dict[str, float] = {}
    for line in lines:
        match = _PARAM.match(line.strip())
        if not match:
            continue
        label = match["label"].strip().lower()
        key = aliases.get(label)
        if key:
            result[key] = float(match["value"].strip())
    return result


def parse_solomon(text: str, *, source_path: Path | str | None = None) -> Instance:
    """Parse the Schneider Solomon text format, including its Q/C parameter block."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and lines[0].lower().startswith("stringid"):
        lines.pop(0)
    node_lines: list[str] = []
    param_lines: list[str] = []
    in_params = False
    for line in lines:
        if line.startswith("----"):
            break
        if _PARAM.match(line):
            in_params = True
        (param_lines if in_params else node_lines).append(line)
    params = _parameters(param_lines)
    missing = {"Q", "C", "r", "g", "v"} - params.keys()
    if missing:
        raise ValueError(f"Missing Schneider vehicle parameters: {sorted(missing)}")

    nodes: dict[str, Node] = {}
    depot_id: str | None = None
    customers: list[str] = []
    stations: list[str] = []
    kinds: dict[str, Literal["depot", "customer", "station"]] = {
        "d": "depot",
        "c": "customer",
        "f": "station",
    }
    for line in node_lines:
        fields = line.split()
        if len(fields) < 8 or fields[1].lower() not in kinds:
            raise ValueError(f"Malformed Schneider node line: {line}")
        node_id, raw_kind = fields[:2]
        x, y, demand, ready, due, service = map(float, fields[2:8])
        kind = kinds[raw_kind.lower()]
        nodes[node_id] = Node(node_id, kind, (x, y), demand, service, ready, due)
        if kind == "depot":
            if depot_id is not None:
                raise ValueError("Expected one depot")
            depot_id = node_id
        elif kind == "customer":
            customers.append(node_id)
        else:
            stations.append(node_id)
    if depot_id is None:
        raise ValueError("Missing depot")
    path = Path(source_path) if source_path else None
    instance_id = path.stem if path else "unknown"
    match = _FAMILY.match(instance_id)
    if not match:
        raise ValueError(f"Cannot infer Schneider family from {instance_id!r}")
    family = match.group(0).upper()
    scale = "small" if len(customers) <= 25 else "large"
    return Instance(
        instance_id, "Schneider_E-VRPTW", nodes, depot_id, tuple(customers), tuple(stations),
        Vehicle(params["C"], params["Q"], params["Q"], params["r"], params["v"], params["g"]),
        nodes[depot_id].due_time,
        {"family": family, "scale": scale, "source_path": str(path) if path else None,
         "raw_params": params},
    )


def load_instance(path: Path | str) -> Instance:
    path = Path(path)
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return parse_solomon(raw.decode(encoding), source_path=path)
        except UnicodeDecodeError:
            continue
    return parse_solomon(raw.decode("utf-8", errors="replace"), source_path=path)
