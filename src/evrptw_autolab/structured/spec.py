"""Formal EVRPTW specification schema for structured synthesis.

Architect fills this once; then it is immutable for the run.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from evrptw_autolab.synthesis.contract import FAULT_ATLAS, PROBLEM_BRIEF


class FormalSpec(BaseModel):
    """Immutable contract the coding agents must satisfy."""

    OBJECTIVE: str = Field(
        default=(
            "Lexicographic laboratory ranking: feasibility, then fewer vehicles, "
            "then smaller total Euclidean distance. Unlimited fleet. Full recharge only."
        )
    )
    INPUT_FIELDS: list[str] = Field(
        default_factory=lambda: [
            "instance.depot_id (str)",
            "instance.customer_ids (tuple[str, ...])",
            "instance.station_ids (tuple[str, ...])",
            "instance.node_map[node_id] -> Node",
            "instance.vehicle (VehicleSpec: capacity, battery_capacity, consumption_rate, "
            "velocity, inverse_refuel_rate, start_soc)",
            "Node: id, kind, x, y, demand, ready_time, due_time, service_time",
        ]
    )
    OUTPUT_CONTRACT: str = Field(
        default=(
            "solve(instance, seed, time_limit_s) returns CandidateSolution or "
            "{'routes': list[list[str]], 'metadata': dict}. Zero LLM calls in solver.py."
        )
    )
    VISIT: str = Field(
        default="Every customer_id appears exactly once across all routes (no missing, no duplicates)."
    )
    DEPOT: str = Field(
        default=(
            "Each route is list[str] starting and ending at instance.depot_id. "
            "Depot may appear only as first and last stop (no internal depot visits)."
        )
    )
    CAPACITY: str = Field(
        default="Vehicle load never exceeds instance.vehicle.capacity along any route."
    )
    TIME_WINDOWS: str = Field(
        default=(
            "Service start at each customer must respect ready_time and due_time "
            "(waiting allowed before ready_time)."
        )
    )
    SERVICE_TIMES: str = Field(
        default="Service time at customers (and charging duration at stations) advances the clock."
    )
    BATTERY: str = Field(
        default=(
            "Battery never goes negative. Energy from travel uses consumption_rate * distance. "
            "start_soc is already energy at the depot (do not multiply by battery_capacity)."
        )
    )
    CHARGING: str = Field(
        default=(
            "Full recharge only. Station ids must appear as nodes in the returned route. "
            "propagate_route performs Schneider full recharge; full_recharge returns ChargeDecision, not float. "
            "Do not mutate StopState fields."
        )
    )
    TERMINATION: str = Field(
        default=(
            "Honor time_limit_s inside solve. Always return a routes structure even if incomplete. "
            "Loop-safe: no unbounded search without a time or iteration guard."
        )
    )
    notes: list[str] = Field(default_factory=list)
    fault_families: list[str] = Field(
        default_factory=lambda: list(FAULT_ATLAS["families"])
    )

    model_config = {"frozen": True}


def default_spec() -> FormalSpec:
    """Spec derived from the existing EVRPTW synthesis contract."""
    return FormalSpec(
        notes=[
            "String node ids only (never integer 0 as depot).",
            "Do not hard-code Schneider instance ids or BKS tables.",
            "Invent the algorithm; do not name published heuristics.",
            PROBLEM_BRIEF.strip().splitlines()[0],
        ]
    )


_REQUIRED_SUBSTRINGS: dict[str, tuple[str, ...]] = {
    "OBJECTIVE": ("feasib", "vehicle", "distance"),
    "OUTPUT_CONTRACT": ("routes", "solve"),
    "VISIT": ("customer", "once"),
    "DEPOT": ("depot",),
    "CAPACITY": ("capacity",),
    "TIME_WINDOWS": ("ready", "due"),
    "BATTERY": ("battery",),
    "CHARGING": ("recharge", "station"),
    "TERMINATION": ("time",),
}


def validate_spec(spec: FormalSpec | dict[str, Any]) -> list[str]:
    """Check spec against known contract facts. Returns a list of problems (empty = ok)."""
    if isinstance(spec, dict):
        try:
            model = FormalSpec.model_validate(spec)
        except Exception as error:  # noqa: BLE001
            return [f"schema: {error}"]
    else:
        model = spec
    problems: list[str] = []
    for field, needles in _REQUIRED_SUBSTRINGS.items():
        text = str(getattr(model, field, "") or "").lower()
        for needle in needles:
            if needle.lower() not in text:
                problems.append(f"{field}: missing contract fact '{needle}'")
                break
    if not model.INPUT_FIELDS:
        problems.append("INPUT_FIELDS: empty")
    families = {str(f).upper() for f in model.fault_families}
    for required in FAULT_ATLAS["families"]:
        if required not in families:
            problems.append(f"fault_families: missing {required}")
    return problems


def freeze_spec(raw: FormalSpec | dict[str, Any] | None) -> FormalSpec:
    """Validate and freeze; fall back to default_spec on failure."""
    if raw is None:
        return default_spec()
    try:
        model = raw if isinstance(raw, FormalSpec) else FormalSpec.model_validate(raw)
    except Exception:  # noqa: BLE001
        return default_spec()
    if validate_spec(model):
        # Merge defaults for missing facts rather than rejecting outright when close.
        base = default_spec().model_dump()
        merged = {**base, **model.model_dump()}
        try:
            candidate = FormalSpec.model_validate(merged)
        except Exception:  # noqa: BLE001
            return default_spec()
        if validate_spec(candidate):
            return default_spec()
        return candidate
    return model
