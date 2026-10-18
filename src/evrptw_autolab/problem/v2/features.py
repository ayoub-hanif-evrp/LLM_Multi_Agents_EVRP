"""Versioned feature contract for generated heuristic scores.

Schema ``2026-10-18.v1`` records the units the solver actually passes.
Normalized ratios are computed for diagnostics. They are not substituted
into historical expressions, because those expressions were written against
the raw arguments below.
"""
from __future__ import annotations

FEATURE_SCHEMA_VERSION = "2026-10-18.v1"

# battery_arrival is vehicle energy, the same unit as VehicleTypeV2.battery_capacity.
# On Montoya tc0c10s2cf1 that capacity is 16000 Wh, not a fraction in [0, 1].
STATION_FEATURES_V1: dict[str, dict[str, str]] = {
    "detour": {
        "unit": "distance",
        "scale": "raw travel distance of the station detour",
        "range": "[0, inf)",
        "passed_to_scorer": "true",
    },
    "battery_arrival": {
        "unit": "energy",
        "scale": "state of charge on arrival at the station, same unit as battery_capacity",
        "range": "physical energy, not [0, 1]",
        "passed_to_scorer": "true",
    },
    "station_rate": {
        "unit": "instance-specific",
        "scale": "node.recharging_rate as published",
        "range": "finite",
        "passed_to_scorer": "true",
    },
    "energy_slack_ratio": {
        "unit": "1",
        "scale": "battery_at_station / battery_capacity",
        "range": "[0, 1]",
        "passed_to_scorer": "false",
    },
    "route_time_slack_ratio": {
        "unit": "1",
        "scale": "(max_travel_time - projected_completion) / max_travel_time",
        "range": "(-inf, 1]",
        "passed_to_scorer": "false",
    },
}
