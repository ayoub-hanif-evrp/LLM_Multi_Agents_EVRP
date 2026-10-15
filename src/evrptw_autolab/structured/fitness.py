"""Lexicographic fitness for structured synthesis candidates.

Ordering (higher is better):
  executable → routing → charging → multi → g4_count →
  -violations → -capacity → -battery → -lateness;
  after 4/4 Schneider: -vehicles → -distance.

Reuses evaluate_through / panel helpers from synthesis.from_scratch and
evolution.evaluate without changing Experiment A behavior.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from evrptw_autolab.evolution.evaluate import (
    all_c5_instances,
    code_hash,
    known_ids_for_panel,
    panel_instances,
)
from evrptw_autolab.sandbox.limits import RunLimits, limits_from_config
from evrptw_autolab.synthesis.from_scratch import STAGES, evaluate_through, precheck_source

__all__ = [
    "STAGES",
    "code_hash",
    "evaluate_candidate",
    "fitness_key",
    "known_ids_for_panel",
    "panel_instances",
    "all_c5_instances",
    "precheck_source",
]


def fitness_key(info: dict[str, Any]) -> tuple:
    """Lexicographic key; larger tuples are better."""
    gates = int(info.get("gates_passed") or 0)
    executable = 1 if gates >= 1 else 0
    routing = 1 if gates >= 2 else 0
    charging = 1 if gates >= 3 else 0
    multi = 1 if gates >= 4 else 0

    g4 = int(info.get("instances_feasible") or info.get("g4_passed_here") or 0)
    if gates >= 5 and bool(info.get("ok")):
        g4 = max(g4, int(info.get("g4_total") or 4) or 4)

    diagnostic = dict(info.get("diagnostic") or {})
    violations = (
        len(diagnostic.get("customers_missing") or [])
        + len(diagnostic.get("customers_duplicated") or [])
        + int(diagnostic.get("depot_violations") or 0)
    )
    capacity = float(diagnostic.get("capacity_excess") or 0.0)
    battery = float(diagnostic.get("battery_deficit") or 0.0)
    lateness = float(diagnostic.get("lateness") or 0.0)

    fully = bool(info.get("ok")) and gates >= 5 and g4 >= 4
    if fully:
        vehicles = info.get("vehicles")
        distance = info.get("distance")
        v = int(vehicles) if vehicles is not None else 10**9
        d = float(distance) if distance is not None else 1e18
        return (
            executable,
            routing,
            charging,
            multi,
            g4,
            -violations,
            -capacity,
            -battery,
            -lateness,
            -v,
            -d,
        )
    return (
        executable,
        routing,
        charging,
        multi,
        g4,
        -violations,
        -capacity,
        -battery,
        -lateness,
        0,
        0.0,
    )


def evaluate_candidate(
    solver_dir: Path,
    *,
    stage: str = "schneider_c5",
    limits: RunLimits | None = None,
    panel: list[Any] | None = None,
    known_ids: set[str] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Precheck + evaluate_through; attach fitness_key."""
    limits = limits or limits_from_config()
    text = source if source is not None else (solver_dir / "solver.py").read_text(encoding="utf-8")
    ids = known_ids if known_ids is not None else set()
    blocked = precheck_source(text, ids) if ids else None
    if blocked is not None:
        info = dict(blocked)
        info["fitness"] = fitness_key(info)
        return info
    panel_list = panel if panel is not None else []
    info = evaluate_through(solver_dir, stage, limits=limits, panel=panel_list)
    info["fitness"] = fitness_key(info)
    return info
