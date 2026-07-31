"""Handcrafted analogues for generated M7B candidates."""

from __future__ import annotations

ANALOGUE_MAP: dict[str, dict[str, str]] = {
    "destroy": {
        "handcrafted_destroy": "low_energy_slack_removal",
        "handcrafted_repair": "regret2_insertion",
        "note": "Closest destroy+regret pairing to H2 cascade destroy hypothesis.",
    },
    "charging": {
        "handcrafted_destroy": "charging_dependency_removal",
        "handcrafted_repair": "time_energy_aware_insertion",
        "note": "Closest charging-oriented handcrafted destroy.",
    },
    "composite": {
        "handcrafted_destroy": "route_removal",
        "handcrafted_repair": "regret2_insertion",
        "note": "Segment/route-oriented destroy as composite analogue.",
    },
}


def analogue_for_category(category: str) -> dict[str, str]:
    return dict(ANALOGUE_MAP.get(category) or ANALOGUE_MAP["destroy"])
