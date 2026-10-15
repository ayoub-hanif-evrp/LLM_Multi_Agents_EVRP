"""Travel distance / time / energy between nodes for ProblemSpecV2."""
from __future__ import annotations

from math import hypot

from evrptw_autolab.problem.v2.types import NodeV2, ProblemSpecV2, VehicleTypeV2

EPSILON = 1e-6


def euclidean(left: NodeV2, right: NodeV2) -> float:
    return hypot(left.x - right.x, left.y - right.y)


def travel_distance(spec: ProblemSpecV2, left: NodeV2, right: NodeV2) -> float:
    if left.id == right.id:
        return 0.0
    if spec.capabilities.matrix_distances:
        matrix = spec.metadata.get("travel_time_matrix") or {}
        # Bezzi stores travel_time as the arc metric used for routing duration;
        # when no separate distance matrix exists, use travel_time as distance proxy
        # only if euclidean_distances is false — objective may still use it.
        dist_matrix = spec.metadata.get("distance_matrix")
        if dist_matrix is not None:
            try:
                return float(dist_matrix[left.id][right.id])
            except (KeyError, TypeError) as error:
                raise ValueError(f"missing distance matrix arc {left.id}->{right.id}") from error
        # Fall through: some datasets only publish travel_time/energy; distance := travel_time.
        try:
            return float(matrix[left.id][right.id])
        except (KeyError, TypeError) as error:
            raise ValueError(f"missing travel matrix arc {left.id}->{right.id}") from error
    if not spec.capabilities.euclidean_distances:
        raise ValueError(f"{spec.family}: no distance model configured")
    return euclidean(left, right)


def travel_time(
    spec: ProblemSpecV2,
    left: NodeV2,
    right: NodeV2,
    vehicle: VehicleTypeV2,
) -> float:
    if left.id == right.id:
        return 0.0
    if spec.capabilities.matrix_distances:
        matrix = spec.metadata.get("travel_time_matrix") or {}
        try:
            return float(matrix[left.id][right.id])
        except (KeyError, TypeError) as error:
            raise ValueError(f"missing travel_time arc {left.id}->{right.id}") from error
    dist = travel_distance(spec, left, right)
    if vehicle.velocity is None or vehicle.velocity <= 0:
        # Documented Hiermann case: do not invent speed; treat distance units as time
        # only when metadata explicitly allows it.
        if spec.metadata.get("travel_time_model") == "distance_equals_time":
            return dist
        if spec.family == "hiermann" and spec.metadata.get("travel_time_model") == "unspecified_in_file":
            # Conservative research default used only when tests set override;
            # otherwise require explicit convention.
            raise ValueError(
                "hiermann travel time undefined: set metadata travel_time_model="
                "'distance_equals_time' or provide vehicle.velocity"
            )
        raise ValueError(f"vehicle {vehicle.type_id} missing positive velocity")
    return dist / float(vehicle.velocity)


def energy_required(
    spec: ProblemSpecV2,
    left: NodeV2,
    right: NodeV2,
    vehicle: VehicleTypeV2,
) -> float:
    if left.id == right.id:
        return 0.0
    if vehicle.is_conventional and not vehicle.is_hybrid and not vehicle.is_electric:
        return 0.0
    if spec.capabilities.matrix_distances:
        matrix = spec.metadata.get("energy_matrix") or {}
        try:
            return float(matrix[left.id][right.id])
        except (KeyError, TypeError) as error:
            raise ValueError(f"missing energy matrix arc {left.id}->{right.id}") from error
    if vehicle.consumption_rate is None:
        raise ValueError(f"vehicle {vehicle.type_id} missing consumption_rate")
    return travel_distance(spec, left, right) * float(vehicle.consumption_rate)
