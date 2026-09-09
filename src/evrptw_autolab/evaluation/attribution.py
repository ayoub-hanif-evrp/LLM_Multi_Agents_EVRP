"""Matched parent/child deltas under identical budgets."""
from __future__ import annotations

from evrptw_autolab.evaluation.ranking import rank_key
from evrptw_autolab.problem.types import EvaluationReport


def matched_delta(parent: EvaluationReport, child: EvaluationReport) -> dict[str, float | int | bool]:
    return {
        "child_better": rank_key(child) < rank_key(parent),
        "feasible_parent": int(parent.feasible),
        "feasible_child": int(child.feasible),
        "vehicles_delta": child.vehicles - parent.vehicles,
        "distance_delta": child.total_distance - parent.total_distance,
        "runtime_delta_s": child.runtime_s - parent.runtime_s,
        "parent_fault": (parent.first_fault or {}).get("family", ""),
        "child_fault": (child.first_fault or {}).get("family", ""),
    }


def role_outcomes(
    activated: list[str],
    *,
    parent: EvaluationReport,
    child: EvaluationReport,
    architect_target: str = "",
    fault_repaired: bool = False,
) -> dict[str, object]:
    """Credit assignment for the frozen five roles. Does not drop any agent."""
    delta = matched_delta(parent, child)
    fleet_drop = int(parent.feasible and child.feasible and child.vehicles < parent.vehicles)
    battery_parent = (parent.first_fault or {}).get("family") in {"BATTERY", "WINDOW", "CHARGE_POLICY"}
    battery_child = (child.first_fault or {}).get("family") in {"BATTERY", "WINDOW", "CHARGE_POLICY"}
    return {
        "activated": list(activated),
        "architect_target": architect_target,
        "routing_fleet_reduction": bool(fleet_drop and "routing" in activated),
        "charging_battery_invalid_reduced": bool(
            "charging" in activated and battery_parent and not battery_child
        ),
        "search_improved": bool("search" in activated and delta["child_better"]),
        "critic_fault_repaired_next": bool(fault_repaired),
        "vehicles_delta": delta["vehicles_delta"],
        "child_better": delta["child_better"],
    }
