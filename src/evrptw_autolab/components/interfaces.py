"""Typed interfaces for LLM-generated heuristic components.

These are small pure scoring functions plugged into the classical backbone.
Full monolithic solvers are out of scope here — see Track 1 synthesis.

Feature contract
----------------
All numeric features passed into scorers are **finite**. Variants without
customer time windows (Montoya, Bezzi) expose:

- ``has_time_windows`` capability on the problem, and
- finite sentinel dues via ``FINITE_DUE_SENTINEL`` (1e6) instead of ``inf``.

Callers in ``construct`` / ``alns`` / ``energy_repair`` must normalize before
invoking a scorer. Generated code must not assume every instance has tight
windows; use ``due_time >= FINITE_DUE_SENTINEL`` as “no useful due”.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ComponentKind = Literal["insertion_score", "station_score", "removal_priority"]

# Finite stand-in for missing / infinite due times (never pass math.inf to scorers).
FINITE_DUE_SENTINEL = 1.0e6

REQUIRED_CAPS = {
    "insertion_score": frozenset({"euclidean_distances"}),
    "station_score": frozenset({"battery"}),
    "removal_priority": frozenset(),
}

SIGNATURES: dict[ComponentKind, str] = {
    "insertion_score": (
        "def insertion_score(delta_distance: float, due_time: float, ready_time: float, "
        "demand: float, capacity_slack: float) -> float:\n"
        "    \"\"\"Lower is better. due_time is finite (1e6 means no useful window).\"\"\"\n"
    ),
    "station_score": (
        "def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:\n"
        "    \"\"\"Lower is better when choosing a station to insert.\"\"\"\n"
    ),
    "removal_priority": (
        "def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:\n"
        "    \"\"\"Higher means remove sooner. due_time is finite (1e6 = no window).\"\"\"\n"
    ),
}

DEFAULT_SOURCES: dict[ComponentKind, str] = {
    "insertion_score": '''\
def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:
    """Lower is better. Single arithmetic return for the bounded interpreter."""
    return delta_distance + (0.0 if due_time >= 1000000.0 else (0.01 * due_time + 1.0 / max(due_time - ready_time, 1.0))) + (0.0 if capacity_slack >= demand else 1000000.0)
''',
    "station_score": '''\
def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:
    """Lower is better. Prefer reachable stations with short detour."""
    return detour + 0.1 * station_rate + (0.0 if battery_arrival > 0.0 else 1000.0)
''',
    "removal_priority": '''\
def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:
    """Higher means remove sooner. Ignore sentinel dues (1e6)."""
    return (0.0 if due_time >= 1000000.0 else due_time) + 10.0 * route_distance_share + 0.01 * rng_value
''',
}


@dataclass(frozen=True, slots=True)
class CapabilitySignature:
    """Compatibility gate for cross-variant transfer."""

    requires: frozenset[str]
    forbids: frozenset[str] = frozenset()
    component: ComponentKind = "insertion_score"

    def compatible_with(self, flags: object) -> bool:
        for name in self.requires:
            if not bool(getattr(flags, name, False)):
                return False
        for name in self.forbids:
            if bool(getattr(flags, name, False)):
                return False
        return True


def signature_for(kind: ComponentKind) -> CapabilitySignature:
    return CapabilitySignature(requires=REQUIRED_CAPS[kind], component=kind)


def normalize_due_time(due: float) -> float:
    """Map inf/NaN dues to a finite sentinel for scorer arithmetic."""
    value = float(due)
    if value != value or value == float("inf") or value == float("-inf"):
        return FINITE_DUE_SENTINEL
    return value
