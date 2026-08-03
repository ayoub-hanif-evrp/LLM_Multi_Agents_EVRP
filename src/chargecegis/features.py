"""Move-specific, development-normalized EVRPTW feature calculations."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, cast

from .construction import _route_is_locally_feasible
from .moves import Move, MoveType, RemovalUnit, apply_move
from .problem import Instance, Route, Solution
from .propagation import arc_metrics, propagate_route

FEATURE_NAMES = [
    "delta_distance_estimate", "delta_charging_distance", "delta_charging_time",
    "delta_station_count", "minimum_energy_slack_before", "minimum_energy_slack_after",
    "minimum_time_slack_before", "minimum_time_slack_after", "segment_distance_contribution",
    "segment_customer_count", "segment_demand", "route_load_utilization",
    "alternative_station_count", "station_detour_contribution", "station_time_contribution",
    "customer_relatedness", "estimated_repair_cost", "historical_move_acceptance_rate",
    "historical_move_improvement_rate", "move_type_segment_relocation",
    "move_type_tail_exchange", "move_type_station_replacement", "move_type_station_removal",
]

_MAX_ALTERNATIVE_STATION_PROBES = 25


def _is_customer(instance: Instance, node_id: str) -> bool:
    return node_id in instance.customer_ids


def _schedule_values(solution: Solution, attr: str, route_indices: set[int] | None = None) -> float:
    """Min of ``attr`` over schedule stops, restricted to ``route_indices`` when given.

    Falls back to the whole solution if the restriction yields no stops at all (defensive; keeps
    the feature well-defined even for degenerate before/after pairs).
    """
    routes = solution.routes if route_indices is None else [
        r for i, r in enumerate(solution.routes) if i in route_indices
    ]
    values = [float(getattr(stop, attr)) for r in routes for stop in r.schedule]
    if not values and route_indices is not None:
        values = [float(getattr(stop, attr)) for r in solution.routes for stop in r.schedule]
    return min(values) if values else 0.0


def _diff_indices(reference: Solution, other: Solution) -> set[int]:
    """Indices of ``reference.routes`` whose node sequence differs from ``other`` at that index.

    Position-aligned diff: cheap and good enough as a locality signal for ranking features (routes
    that are untouched by a move/repair keep the same index and content in the vast majority of
    cases). Falls back to "every route" if nothing differs, so downstream min-reductions never
    silently degrade to an empty set.
    """
    other_ids = [r.node_ids for r in other.routes]
    changed = {i for i, r in enumerate(reference.routes) if i >= len(other_ids) or r.node_ids != other_ids[i]}
    return changed or set(range(len(reference.routes)))


def _distance(instance: Instance, solution: Solution) -> float:
    return sum(arc_metrics(instance, a, b).distance for route in solution.routes
               for a, b in zip(route.node_ids, route.node_ids[1:]))


def _station_metrics(instance: Instance, solution: Solution) -> tuple[float, float, int]:
    detour = charge_time = 0.0
    count = 0
    for route in solution.routes:
        for i, stop in enumerate(route.schedule):
            if stop.node_id not in instance.station_ids:
                continue
            count += 1
            charge_time += stop.charging_duration
            if 0 < i < len(route.node_ids) - 1:
                p, s, q = route.node_ids[i - 1:i + 2]
                detour += (arc_metrics(instance, p, s).distance + arc_metrics(instance, s, q).distance
                           - arc_metrics(instance, p, q).distance)
    return detour, charge_time, count


def _route_utilization(instance: Instance, route: Route) -> float:
    load = max((s.cumulative_load for s in route.schedule), default=0.0)
    return load / max(float(instance.vehicle.freight_capacity), 1e-12)


def _segment_marginal_distance(instance: Instance, route: Route, start: int, end: int) -> float:
    """True marginal distance of node_ids[start:end+1] on ``route``: detour minus the bypass."""
    ids = route.node_ids
    if start <= 0 or end + 1 >= len(ids):
        return 0.0
    pred, succ = ids[start - 1], ids[end + 1]
    total = arc_metrics(instance, pred, ids[start]).distance
    for a, b in zip(ids[start:end], ids[start + 1:end + 1]):
        total += arc_metrics(instance, a, b).distance
    total += arc_metrics(instance, ids[end], succ).distance
    total -= arc_metrics(instance, pred, succ).distance
    return total


def _alternative_station_count(instance: Instance, route: Route, position: int, current: str) -> float:
    """Count stations that could replace ``current`` at ``position`` and keep the route feasible."""
    node_ids = route.node_ids
    if not (0 <= position < len(node_ids)) or node_ids[position] != current:
        return 0.0
    count = 0
    for candidate in instance.station_ids[:_MAX_ALTERNATIVE_STATION_PROBES]:
        if candidate == current:
            continue
        trial_ids = node_ids[:position] + (candidate,) + node_ids[position + 1:]
        try:
            trial_route = propagate_route(instance, trial_ids, vehicle_index=route.vehicle_index)
        except (KeyError, ValueError):
            continue
        if _route_is_locally_feasible(instance, trial_route):
            count += 1
    return float(count)


def _station_metrics_at(instance: Instance, route: Route, station_id: str, hint_position: int) -> tuple[float, float] | None:
    """Local detour and charging duration of ``station_id`` on ``route`` (position-hinted lookup)."""
    node_ids = route.node_ids
    positions = [hint_position] if 0 <= hint_position < len(node_ids) and node_ids[hint_position] == station_id else []
    if not positions:
        positions = [i for i, nid in enumerate(node_ids) if nid == station_id]
    for position in positions:
        if 0 < position < len(node_ids) - 1:
            p, q = node_ids[position - 1], node_ids[position + 1]
            detour = (arc_metrics(instance, p, station_id).distance + arc_metrics(instance, station_id, q).distance
                      - arc_metrics(instance, p, q).distance)
            charge_time = route.schedule[position].charging_duration if position < len(route.schedule) else 0.0
            return detour, charge_time
    return None


def compute_features_for_solutions(
    instance: Instance,
    before: Solution,
    after: Solution | None,
    move_or_meta: Move | RemovalUnit,
    history: dict | None = None,
) -> dict[str, float]:
    """Compute the feature catalogue for a before/after solution pair.

    Accepts either a coupled :class:`~chargecegis.moves.Move` (segment relocation, tail exchange,
    station replacement/removal) or a :class:`~chargecegis.moves.RemovalUnit` (equal-budget
    destroy-then-repair of a customer segment, see :mod:`chargecegis.alns`). Solution-state
    features (slack, utilization) are restricted to the routes that actually differ between
    ``before`` and ``after`` so an unrelated tight route elsewhere cannot swamp the local signal.
    Callers must pass a feasible/valid ``after`` (e.g. from ``apply_move`` or a repair step); this
    raises rather than inventing placeholder values so infeasible candidates cannot silently
    pollute training data.
    """
    if after is None:
        raise ValueError("infeasible move")
    history = history or {}

    before_affected = _diff_indices(before, after)
    after_affected = _diff_indices(after, before)

    before_detour, before_charge, before_stations = _station_metrics(instance, before)
    after_detour, after_charge, after_stations = _station_metrics(instance, after)
    delta_charging_distance = after_detour - before_detour
    delta_charging_time = after_charge - before_charge
    delta_station_count = float(after_stations - before_stations)

    target_route: Route | None = None
    measured: tuple[float, float] | None = None

    # Two branches, kept fully separate (rather than a shared `is_move` flag) so type checking
    # can narrow `move_or_meta` to the concrete `Move`/`RemovalUnit` attributes in each one.
    if isinstance(move_or_meta, Move):
        move = move_or_meta
        origin_index = move.route_i
        origin_route = before.routes[origin_index] if 0 <= origin_index < len(before.routes) else before.routes[0]
        if move.route_j is not None and move.route_j < len(before.routes):
            target_route = before.routes[move.route_j]
        move_type = move.move_type

        if move_type is MoveType.TAIL_EXCHANGE and move.route_j is not None:
            cut_i, cut_j = move.indices
            route_j = before.routes[move.route_j]
            tail_i = tuple(n for n in origin_route.node_ids[cut_i:] if _is_customer(instance, n))
            tail_j = tuple(n for n in route_j.node_ids[cut_j:] if _is_customer(instance, n))
            segment = tail_i + tail_j
            segment_distance = 0.0
            if 0 < cut_i < len(origin_route.node_ids) - 1:
                segment_distance += _segment_marginal_distance(instance, origin_route, cut_i, len(origin_route.node_ids) - 2)
            if 0 < cut_j < len(route_j.node_ids) - 1:
                segment_distance += _segment_marginal_distance(instance, route_j, cut_j, len(route_j.node_ids) - 2)
        elif move_type is MoveType.SEGMENT_RELOCATION and move.indices:
            segment = move.segment
            start, end, _insertion = move.indices
            segment_distance = _segment_marginal_distance(instance, origin_route, start, end)
        else:
            segment = move.segment
            segment_distance = 0.0

        if move.station_ids and move.indices:
            alternative_count = _alternative_station_count(
                instance, origin_route, move.indices[0], move.station_ids[0]
            )
        else:
            alternative_count = 0.0

        if move_type is MoveType.STATION_REPLACEMENT and len(move.station_ids) > 1 and origin_index < len(after.routes):
            measured = _station_metrics_at(instance, after.routes[origin_index], move.station_ids[1], move.indices[0])
    else:
        unit = move_or_meta
        origin_index = unit.route_index
        origin_route = before.routes[origin_index] if 0 <= origin_index < len(before.routes) else before.routes[0]
        move_type = MoveType.SEGMENT_RELOCATION  # removal units are reported under this bucket
        segment = unit.customer_ids
        segment_distance = _segment_marginal_distance(
            instance, origin_route, unit.start_customer_position, unit.end_customer_position
        )
        gap_stations = unit.affected_station_ids
        gap_position = next(
            (p for p, nid in enumerate(origin_route.node_ids) if nid in gap_stations), None
        ) if gap_stations else None
        alternative_count = (
            _alternative_station_count(instance, origin_route, gap_position, origin_route.node_ids[gap_position])
            if gap_position is not None else 0.0
        )

    demand = sum(float(instance.nodes[n].demand) for n in segment if n in instance.nodes)
    utilization = _route_utilization(instance, origin_route)
    if target_route is not None:
        utilization = max(utilization, _route_utilization(instance, target_route))

    station_detour_contribution = measured[0] if measured is not None else delta_charging_distance
    station_time_contribution = measured[1] if measured is not None else delta_charging_time

    if len(segment) > 1:
        pairs = list(combinations(segment, 2))
        relatedness = mean(1.0 / (1.0 + arc_metrics(instance, a, b).distance) for a, b in pairs)
    else:
        relatedness = 0.0

    estimated_repair_cost = abs(delta_station_count) + max(0.0, delta_charging_distance) / 100.0

    result = {
        "delta_distance_estimate": _distance(instance, after) - _distance(instance, before),
        "delta_charging_distance": delta_charging_distance,
        "delta_charging_time": delta_charging_time,
        "delta_station_count": delta_station_count,
        "minimum_energy_slack_before": _schedule_values(before, "energy_slack", before_affected),
        "minimum_energy_slack_after": _schedule_values(after, "energy_slack", after_affected),
        "minimum_time_slack_before": _schedule_values(before, "time_slack", before_affected),
        "minimum_time_slack_after": _schedule_values(after, "time_slack", after_affected),
        "segment_distance_contribution": segment_distance,
        "segment_customer_count": float(len(segment)),
        "segment_demand": demand,
        "route_load_utilization": utilization,
        "alternative_station_count": alternative_count,
        "station_detour_contribution": station_detour_contribution,
        "station_time_contribution": station_time_contribution,
        "customer_relatedness": relatedness,
        "estimated_repair_cost": estimated_repair_cost,
        "historical_move_acceptance_rate": float(history.get("acceptance_rate", 0.0)),
        "historical_move_improvement_rate": float(history.get("improvement_rate", 0.0)),
    }
    for kind in MoveType:
        result[f"move_type_{kind.value.lower()}"] = float(move_type is kind)
    return {name: float(result[name]) for name in FEATURE_NAMES}


def compute_features(instance: Instance, solution: Solution, move: Move, history: dict | None = None) -> dict[str, float]:
    """Compute all required features for a move that must already be feasible.

    Callers are responsible for filtering to feasible moves (e.g. those for which
    ``apply_move`` returns a solution) before ranking; thin wrapper around
    :func:`compute_features_for_solutions` for the classic single-``Move`` call sites.
    """
    after = apply_move(instance, solution, move)
    return compute_features_for_solutions(instance, solution, after, move, history=history)


@dataclass
class FeatureNormalizer:
    """Z-score normalizer fitted exclusively on development feature vectors.

    Features whose fitted scale falls below ``scale_floor`` are marked ``constant`` and
    transformed to exactly ``0.0`` (a near-zero-variance feature would otherwise blow up under
    division); normalized values are clipped to ``[-clip_bound, clip_bound]`` so a single extreme
    development sample cannot dominate downstream ranking.
    """
    means: dict[str, float] = field(default_factory=dict)
    scales: dict[str, float] = field(default_factory=dict)
    constant: dict[str, bool] = field(default_factory=dict)
    sample_count: int = 0
    families_used: tuple[str, ...] = ()
    scale_floor: float = 1e-6
    clip_bound: float = 5.0

    def fit(self, development_vectors: list[dict[str, float]]) -> FeatureNormalizer:
        return self.fit_balanced(development_vectors)

    def fit_balanced(
        self, vectors: list[dict[str, float]], families: list[str] | None = None
    ) -> FeatureNormalizer:
        """Fit on ``vectors``; ``families`` (one label per vector) is recorded as metadata only.

        Callers wanting a class-balanced fit should pre-balance ``vectors``/``families`` (e.g. by
        resampling per family) before calling this; the fit itself is a plain per-feature
        mean/scale over whatever sample it is given.
        """
        if not vectors:
            raise ValueError("development vectors are required")
        self.means = {n: mean(float(v.get(n, 0.0)) for v in vectors) for n in FEATURE_NAMES}
        self.scales, self.constant = {}, {}
        for name in FEATURE_NAMES:
            raw_scale = pstdev(float(v.get(name, 0.0)) for v in vectors)
            is_constant = raw_scale < self.scale_floor
            self.scales[name] = self.scale_floor if is_constant else raw_scale
            self.constant[name] = is_constant
        self.sample_count = len(vectors)
        self.families_used = tuple(sorted(set(families))) if families else ()
        return self

    def transform(self, values: dict[str, float]) -> dict[str, float]:
        if not self.means:
            raise RuntimeError("FeatureNormalizer must be fitted on development data")
        out: dict[str, float] = {}
        for name in FEATURE_NAMES:
            if self.constant.get(name, False):
                out[name] = 0.0
                continue
            z = (float(values.get(name, 0.0)) - self.means[name]) / self.scales[name]
            out[name] = max(-self.clip_bound, min(self.clip_bound, z))
        return out

    def to_dict(self) -> dict[str, object]:
        return {
            "means": dict(self.means),
            "scales": dict(self.scales),
            "constant": dict(self.constant),
            "sample_count": self.sample_count,
            "families_used": list(self.families_used),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> FeatureNormalizer:
        means = cast("dict[str, float]", payload.get("means", {}))
        scales = cast("dict[str, float]", payload.get("scales", {}))
        constant = cast("dict[str, bool]", payload.get("constant", {}))
        families_used = cast("list[str]", payload.get("families_used", ()))
        return cls(
            means=dict(means),
            scales=dict(scales),
            constant=dict(constant),
            sample_count=int(cast(Any, payload.get("sample_count", 0))),
            families_used=tuple(families_used),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: str | Path) -> FeatureNormalizer:
        return cls.from_dict(json.loads(Path(path).read_text()))
