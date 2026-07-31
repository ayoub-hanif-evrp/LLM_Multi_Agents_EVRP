"""Failure taxonomy classifiers for EVRPTW search evidence."""

from __future__ import annotations

from typing import Any

from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.domain.violations import FeasibilityReport


FAILURE_MODES = [
    "time_window_cascade",
    "battery_deficit",
    "charging_time_induced_lateness",
    "unreachable_charging_transition",
    "excessive_charging_detour",
    "redundant_charging_stop",
    "high_station_dependency",
    "route_fragmentation",
    "fleet_count_stagnation",
    "charging_repair_timeout",
    "operator_runtime_explosion",
    "repeated_unsuccessful_customer_insertion",
]


def classify_feasibility_report(report: FeasibilityReport) -> list[str]:
    modes: list[str] = []
    if report.time_window_violations:
        modes.append("time_window_cascade")
    if report.battery_violations:
        modes.append("battery_deficit")
    if report.unreachable_arcs:
        modes.append("unreachable_charging_transition")
    return modes


def classify_route_features(features: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    if float(features.get("charging_detour_ratio") or 0.0) > 0.25:
        modes.append("excessive_charging_detour")
    if int(features.get("charging_stops") or 0) >= 3 and float(
        features.get("station_dependency") or 0.0
    ) > 0.8:
        modes.append("high_station_dependency")
    if int(features.get("charging_stops") or 0) >= 2 and float(
        features.get("charging_duration") or 0.0
    ) > 0.5 * float(features.get("duration") or 1.0):
        modes.append("charging_time_induced_lateness")
    if int(features.get("n_customers") or 0) <= 1:
        modes.append("route_fragmentation")
    # Redundant stop heuristic: charging stop with near-zero charged energy already filtered;
    # mark high stop count with tiny detour as potentially redundant.
    if int(features.get("charging_stops") or 0) >= 2 and float(
        features.get("charging_detour_ratio") or 0.0
    ) < 0.02:
        modes.append("redundant_charging_stop")
    return modes


def classify_search_diagnostics(search: dict[str, Any]) -> list[str]:
    modes: list[str] = []
    if int(search.get("stagnation_iterations") or 0) >= 10:
        modes.append("fleet_count_stagnation")
    rej = search.get("rejection_histogram") or {}
    if int(rej.get("charging_repair_timeout") or 0) > 0:
        modes.append("charging_repair_timeout")
    if int(rej.get("no_feasible_insertion") or 0) >= 5:
        modes.append("repeated_unsuccessful_customer_insertion")
    profile = search.get("profile") or {}
    times = profile.get("times_seconds") or {}
    op_time = float(times.get("operators") or 0.0)
    total = sum(float(v) for v in times.values()) or 1.0
    if op_time / total > 0.85 and op_time > 5.0:
        modes.append("operator_runtime_explosion")
    return modes


def classify_all(
    *,
    report: FeasibilityReport | None,
    route_feature_list: list[dict[str, Any]],
    search: dict[str, Any],
) -> list[str]:
    modes: list[str] = []
    if report is not None:
        modes.extend(classify_feasibility_report(report))
    for feat in route_feature_list:
        modes.extend(classify_route_features(feat))
    modes.extend(classify_search_diagnostics(search))
    # Stable unique order
    seen: set[str] = set()
    ordered: list[str] = []
    for m in modes:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered
