"""Typed interfaces for LLM-generated heuristic components.

These are small pure scoring functions plugged into the classical backbone.
Full monolithic solvers are out of scope here — see Track 1 synthesis.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ComponentKind = Literal["insertion_score", "station_score", "removal_priority"]

REQUIRED_CAPS = {
    "insertion_score": frozenset({"euclidean_distances"}),
    "station_score": frozenset({"battery"}),
    "removal_priority": frozenset(),
}

SIGNATURES: dict[ComponentKind, str] = {
    "insertion_score": (
        "def insertion_score(delta_distance: float, due_time: float, ready_time: float, "
        "demand: float, capacity_slack: float) -> float:\n"
        "    \"\"\"Lower is better. Pure function; no I/O.\"\"\"\n"
    ),
    "station_score": (
        "def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:\n"
        "    \"\"\"Lower is better when choosing a station to insert.\"\"\"\n"
    ),
    "removal_priority": (
        "def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:\n"
        "    \"\"\"Higher means remove sooner in destroy operators.\"\"\"\n"
    ),
}

DEFAULT_SOURCES: dict[ComponentKind, str] = {
    "insertion_score": '''\
def insertion_score(delta_distance: float, due_time: float, ready_time: float, demand: float, capacity_slack: float) -> float:
    """Lower is better."""
    urgency = 0.0 if due_time > 1e15 else (1.0 / max(due_time - ready_time, 1.0))
    slack_pen = 0.0 if capacity_slack >= demand else 1e6
    return float(delta_distance) + 0.01 * float(due_time) + urgency + slack_pen
''',
    "station_score": '''\
def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:
    """Lower is better."""
    urgency = 0.0 if battery_arrival > 0 else 1000.0
    return float(detour) + 0.1 * float(station_rate) + urgency
''',
    "removal_priority": '''\
def removal_priority(due_time: float, route_distance_share: float, rng_value: float) -> float:
    """Higher means remove sooner."""
    return float(due_time) + 10.0 * float(route_distance_share) + 0.01 * float(rng_value)
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
