"""Versioned feature contract for generated heuristic scores.

Schema ``2026-10-18.v1`` records the units the solver actually passes.
Normalized ratios are computed for diagnostics. They are not substituted
into historical expressions, because those expressions were written against
the raw arguments below.
"""
from __future__ import annotations

FEATURE_SCHEMA_VERSION = "2026-10-18.v1"
FEATURE_SCHEMA_V2 = "2026-10-18.v2"
FEATURE_SCHEMA_V3 = "2026-10-19.v3"
FEATURE_SCHEMA_V4 = "2026-10-24.v4"
KNOWN_FEATURE_SCHEMAS = frozenset(
    {FEATURE_SCHEMA_VERSION, FEATURE_SCHEMA_V2, FEATURE_SCHEMA_V3, FEATURE_SCHEMA_V4}
)

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

# v2 is opt-in. Historical expressions stay on v1 physical battery_arrival.
STATION_FEATURES_V2: dict[str, dict[str, str]] = {
    "detour": {
        "unit": "distance",
        "scale": "raw station detour",
        "range": "[0, inf)",
    },
    "battery_arrival_ratio": {
        "unit": "1",
        "scale": "battery_at_station / battery_capacity",
        "range": "[0, 1]",
    },
    "energy_slack_ratio": {
        "unit": "1",
        "scale": "(battery_capacity - energy_to_next) / battery_capacity after the chosen charge",
        "range": "(-inf, 1]",
    },
    "route_duration_slack": {
        "unit": "1",
        "scale": "(max_travel_time - projected_completion) / max_travel_time",
        "range": "(-inf, 1]",
    },
    "travel_time_detour": {
        "unit": "time",
        "scale": "detour travel time minus the direct arc",
        "range": "(-inf, inf)",
    },
    "charge_time": {
        "unit": "time",
        "scale": "duration of the candidate charge",
        "range": "[0, inf)",
    },
    "station_technology": {
        "unit": "label",
        "scale": "station charge technology id, empty if none",
        "range": "text",
    },
    "incremental_objective_time": {
        "unit": "time",
        "scale": "added travel time plus charge time versus the direct arc",
        "range": "(-inf, inf)",
    },
}


def normalize_feature_schema(value: object, *, strict: bool = False) -> str:
    """Return a known schema id. Blank means v1. Unknown ids raise when strict."""
    text = str(value or "").strip()
    if not text:
        return FEATURE_SCHEMA_VERSION
    if text in KNOWN_FEATURE_SCHEMAS:
        return text
    if strict:
        raise ValueError(f"unknown station feature schema {text}")
    return FEATURE_SCHEMA_VERSION


def feature_schema_prompt() -> str:
    """Text embedded in station-generation prompts. v1 stays the default."""
    return (
        "The feature_schema field is stored on the component bundle and restored "
        "inside the solver subprocess. It is not inferred from the expression.\n"
        f"{FEATURE_SCHEMA_VERSION}: battery_arrival is physical energy, the same unit as "
        "battery capacity. On Montoya that capacity is 16000 Wh, not a fraction in [0, 1].\n"
        f"{FEATURE_SCHEMA_V2}: battery_arrival is battery_at_station / battery_capacity, "
        "clipped to [0, 1]. Declare v2 only when the expression was written for that ratio. "
        "A v1 expression must not be evaluated under v2.\n"
        f'Include "feature_schema":"{FEATURE_SCHEMA_VERSION}" or "{FEATURE_SCHEMA_V2}".'
    )


# v3 adds insertion features. It does not change the v1 station battery unit.
# Historical expressions stay on v1 and are not rewritten.
INSERTION_FEATURES_V3: dict[str, dict[str, str]] = {
    "delta_distance": {
        "unit": "distance",
        "scale": "inserted travel minus the direct arc",
        "range": "(-inf, inf)",
    },
    "due_time": {
        "unit": "time",
        "scale": "customer due time; 1000000 means no useful window",
        "range": "[0, 1000000]",
    },
    "ready_time": {"unit": "time", "scale": "customer ready time", "range": "[0, inf)"},
    "demand": {"unit": "load", "scale": "customer demand", "range": "[0, inf)"},
    "capacity_slack": {
        "unit": "load",
        "scale": "first vehicle type capacity minus current route load",
        "range": "(-inf, inf)",
    },
    "vehicle_fixed_cost": {
        "unit": "money",
        "scale": "fixed cost of the vehicle type being scored; 0 when the family has none",
        "range": "[0, inf)",
    },
    "marginal_energy": {
        "unit": "energy",
        "scale": "vehicle consumption rate times delta_distance; 0 when the rate is absent",
        "range": "(-inf, inf)",
    },
    "new_route_fixed_cost": {
        "unit": "money",
        "scale": "vehicle fixed cost when the route has no customers yet, otherwise 0",
        "range": "[0, inf)",
    },
}

STATION_FEATURES_V3_EXTRA: dict[str, dict[str, str]] = {
    "charge_time": {
        "unit": "time",
        "scale": "duration of the candidate charge after the feasibility filter",
        "range": "[0, inf)",
    },
}


def insertion_feature_prompt() -> str:
    """Units for the v3 insertion signature. v1 expressions do not receive the new names."""
    lines = [
        "Insertion features are finite floats. A v1 expression receives only "
        "delta_distance, due_time, ready_time, demand, and capacity_slack.",
        f"{FEATURE_SCHEMA_V3} also receives vehicle_fixed_cost (money), "
        "marginal_energy (energy = consumption rate * delta_distance), and "
        "new_route_fixed_cost (money paid only when the route has no customers yet). "
        "A v3 removal expression also receives own_route_distance, the travel "
        "distance of the route that currently contains the customer. "
        "route_distance_share stays the historical constant.\n"
        f"{FEATURE_SCHEMA_V4} is a separate repair contract. Its insertion names are "
        "delta_distance and delta_travel_time, which change with the insertion position, "
        "plus route_load_slack_after_insertion, route_customer_count, and "
        "new_vehicle_fixed_cost from the candidate vehicle. Its removal names are due_time, "
        "marginal_removal_distance, time_window_width, and rng_value. "
        "v1, v2, and v3 expressions do not receive these names, and ALNS repair keeps "
        "the historical objective ranking unless the bundle schema is v4.",
        "charge_time (time) is available to a v3 station expression. It is not an insertion feature.",
    ]
    for name, spec in INSERTION_FEATURES_V3.items():
        lines.append(f"{name}: unit={spec['unit']}; {spec['scale']}.")
    return "\n".join(lines)


def battery_argument_for_schema(schema: str, battery_arrival: float, battery_capacity: float) -> float:
    """Map physical energy to the value a scorer of this schema expects.

    v1 and v3 return physical energy. v2 returns a ratio in [0, 1]. Callers must not
    apply v2 to an expression that was written against physical energy.
    """
    if schema == FEATURE_SCHEMA_V2:
        if battery_capacity <= 0.0:
            return 0.0
        ratio = float(battery_arrival) / float(battery_capacity)
        return max(0.0, min(1.0, ratio))
    if schema in {FEATURE_SCHEMA_VERSION, FEATURE_SCHEMA_V3}:
        return float(battery_arrival)
    raise ValueError(f"unknown station feature schema {schema}")


def station_feature_record(
    *,
    detour: float,
    battery_at_station: float,
    battery_capacity: float,
    energy_to_next: float,
    direct_travel_time: float,
    detour_travel_time: float,
    charge_time: float,
    projected_completion: float | None,
    max_travel_time: float | None,
    technology: str = "",
) -> dict[str, float | str | None]:
    """Explicit v2 features. None means the instance has no route-duration limit."""
    cap = float(battery_capacity)
    arrival_ratio = 0.0 if cap <= 0.0 else max(0.0, min(1.0, float(battery_at_station) / cap))
    slack_energy = cap - float(energy_to_next)
    energy_slack_ratio = 0.0 if cap <= 0.0 else slack_energy / cap
    duration_slack: float | None
    if max_travel_time is None or max_travel_time <= 0.0 or projected_completion is None:
        duration_slack = None
    else:
        duration_slack = (float(max_travel_time) - float(projected_completion)) / float(max_travel_time)
    travel_delta = float(detour_travel_time) - float(direct_travel_time)
    return {
        "schema": FEATURE_SCHEMA_V2,
        "detour": float(detour),
        "battery_arrival_ratio": arrival_ratio,
        "energy_slack_ratio": energy_slack_ratio,
        "route_duration_slack": duration_slack,
        "travel_time_detour": travel_delta,
        "charge_time": float(charge_time),
        "station_technology": technology,
        "incremental_objective_time": travel_delta + float(charge_time),
    }
