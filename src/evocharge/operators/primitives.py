"""Executable primitive registry for Milestone 7."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evocharge.domain.solution import Solution
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import (
    API_VERSION,
    EntityCandidate,
    OperatorPlan,
    PlanAction,
    ReadOnlySearchState,
)
from evocharge.reproducibility import hash_mapping
from evocharge.solver.feasibility import evaluate_feasibility
from evocharge.solver.propagation import propagate_route


class PrimitiveDefinition(BaseModel):
    primitive_id: str
    api_version: str = API_VERSION
    category: str
    input_types: list[str] = Field(default_factory=list)
    output_type: str
    mutates_solution: bool = False
    deterministic: bool = True
    worst_case_complexity: str = "O(n)"
    contract_requirements: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)


def _definitions() -> list[PrimitiveDefinition]:
    defs: list[tuple[str, str, str, bool]] = [
        ("query_time_slack", "query", "float", False),
        ("query_energy_slack", "query", "float", False),
        ("query_load_slack", "query", "float", False),
        ("query_charging_detour", "query", "float", False),
        ("query_station_dependency", "query", "float", False),
        ("query_route_distance", "query", "float", False),
        ("query_route_duration", "query", "float", False),
        ("query_customer_relatedness", "query", "float", False),
        ("query_insertion_delta", "query", "dict", False),
        ("query_downstream_charging_delay", "query", "float", False),
        ("query_insertion_feasibility", "query", "float", False),
        ("customers_in_route", "query", "tuple", False),
        ("stations_in_route", "query", "tuple", False),
        ("customer_positions_only", "query", "tuple", False),
        ("non_depot_segments", "query", "tuple", False),
        ("rank_customers_by_energy_criticality", "select", "tuple", False),
        ("rank_segments_by_charging_detour_contribution", "select", "tuple", False),
        ("rank_stations_by_detour", "select", "tuple", False),
        ("enumerate_feasible_station_replacements", "select", "tuple", False),
        ("identify_energy_critical_arc", "query", "tuple", False),
        ("identify_charging_time_cascade", "query", "list", False),
        ("select_customers_by_score", "select", "tuple", False),
        ("select_routes_by_score", "select", "tuple", False),
        ("select_segments_by_score", "select", "tuple", False),
        ("select_stations_by_score", "select", "tuple", False),
        ("plan_customer_removal", "plan", "PlanAction", False),
        ("plan_segment_removal", "plan", "PlanAction", False),
        ("plan_route_removal", "plan", "PlanAction", False),
        ("plan_station_removal", "plan", "PlanAction", False),
        ("plan_station_replacement", "plan", "PlanAction", False),
        ("plan_segment_relocation", "plan", "PlanAction", False),
        ("plan_customer_swap", "plan", "PlanAction", False),
        ("plan_charging_reconstruction", "plan", "PlanAction", False),
        ("plan_greedy_reinsertion", "plan", "PlanAction", False),
        ("plan_regret_reinsertion", "plan", "PlanAction", False),
        ("enumerate_feasible_insertions", "service", "list", False),
        ("reconstruct_charging_pattern", "service", "tuple", False),
        ("validate_operator_plan", "service", "dict", False),
        ("evaluate_candidate_delta", "service", "dict", False),
    ]
    out: list[PrimitiveDefinition] = []
    for pid, cat, out_t, mut in defs:
        out.append(
            PrimitiveDefinition(
                primitive_id=pid,
                category=cat,
                input_types=["OperatorContext", "ReadOnlySearchState"],
                output_type=out_t,
                mutates_solution=mut,
                invariants=["deterministic_on_fixed_seed"],
                contract_requirements=["schneider_v1.0"],
            )
        )
    return out


PRIMITIVE_DEFINITIONS: list[PrimitiveDefinition] = _definitions()
PRIMITIVE_IDS: set[str] = {d.primitive_id for d in PRIMITIVE_DEFINITIONS}


def catalogue_payload() -> dict[str, Any]:
    return {
        "api_version": API_VERSION,
        "catalogue_version": "1.0.0",
        "primitives": [d.model_dump() for d in PRIMITIVE_DEFINITIONS],
    }


def catalogue_hash() -> str:
    return hash_mapping(catalogue_payload())


def write_catalogue_json(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = catalogue_payload()
    digest = hash_mapping(payload)
    out = {**payload, "catalogue_hash": digest}
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


# --- Executable implementations (parent process only) ---


def query_route_distance(state: ReadOnlySearchState, route_index: int) -> float:
    route = state.solution.routes[route_index]
    if not route.schedule:
        return 0.0
    return float(route.schedule[-1].traveled_distance)


def query_route_duration(state: ReadOnlySearchState, route_index: int) -> float:
    route = state.solution.routes[route_index]
    if not route.schedule:
        return 0.0
    return float(route.schedule[-1].departure_time)


def query_energy_slack(state: ReadOnlySearchState, route_index: int) -> float:
    route = state.solution.routes[route_index]
    if not route.schedule:
        return float(state.instance.vehicle.battery_capacity)
    return float(min(s.battery_on_departure for s in route.schedule))


def query_time_slack(state: ReadOnlySearchState, route_index: int, stop_index: int) -> float:
    route = state.solution.routes[route_index]
    stop = route.schedule[stop_index]
    node = state.instance.nodes[stop.node_id]
    return float(node.due_time - stop.arrival_time)


def query_charging_detour(state: ReadOnlySearchState, route_index: int) -> float:
    from evocharge.solver.route_features import route_features

    feats = route_features(state.instance, state.solution.routes[route_index])
    return float(feats.get("charging_detour_ratio") or 0.0)


def query_station_dependency(state: ReadOnlySearchState, route_index: int) -> float:
    from evocharge.solver.route_features import route_features

    feats = route_features(state.instance, state.solution.routes[route_index])
    return float(feats.get("station_dependency") or 0.0)


def query_load_slack(state: ReadOnlySearchState, route_index: int) -> float:
    route = state.solution.routes[route_index]
    cap = float(state.instance.vehicle.freight_capacity)
    if not route.schedule:
        return cap
    peak = max(float(s.cumulative_load) for s in route.schedule)
    return cap - peak


def _entity_id(c: EntityCandidate | str | Any) -> str:
    if isinstance(c, str):
        return c
    eid = getattr(c, "entity_id", None)
    if eid is not None:
        return str(eid)
    if isinstance(c, dict):
        return str(c.get("entity_id", c))
    return str(c)


def select_customers_by_score(
    candidates: tuple[EntityCandidate, ...] | list[Any] | tuple[Any, ...],
    scores: tuple[float, ...] | list[float],
    k: int,
) -> tuple[str, ...]:
    ranked = sorted(
        zip(scores, [_entity_id(c) for c in candidates], strict=True), reverse=True
    )
    return tuple(cid for _, cid in ranked[: max(0, k)])


def plan_customer_removal(customer_ids: list[str], action_id: str = "a0") -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_customer_removal",
        arguments={"customer_ids": list(customer_ids)},
        rationale="remove customers",
    )


def plan_charging_reconstruction(route_index: int, action_id: str = "a1") -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_charging_reconstruction",
        arguments={"route_index": route_index},
        rationale="reconstruct charging",
    )


def plan_station_removal(
    route_index: int, station_id: str, action_id: str = "a2"
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_station_removal",
        arguments={"route_index": route_index, "station_id": station_id},
        rationale="remove station",
    )


def plan_station_replacement(
    route_index: int,
    old_station_id: str,
    new_station_id: str,
    action_id: str = "a3",
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_station_replacement",
        arguments={
            "route_index": route_index,
            "old_station_id": old_station_id,
            "new_station_id": new_station_id,
        },
        rationale="replace station",
    )


def plan_segment_removal(
    route_index: int, start_index: int, end_index: int, action_id: str = "a4"
) -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_segment_removal",
        arguments={
            "route_index": route_index,
            "start_index": start_index,
            "end_index": end_index,
        },
        rationale="remove segment",
    )


def plan_regret_reinsertion(customer_ids: list[str], action_id: str = "a5") -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_regret_reinsertion",
        arguments={"customer_ids": list(customer_ids)},
        rationale="regret reinsertion",
    )


def plan_greedy_reinsertion(customer_ids: list[str], action_id: str = "a6") -> PlanAction:
    return PlanAction(
        action_id=action_id,
        primitive_id="plan_greedy_reinsertion",
        arguments={"customer_ids": list(customer_ids)},
        rationale="greedy reinsertion",
    )


def validate_operator_plan_struct(plan: OperatorPlan) -> dict[str, Any]:
    return {"ok": True, "n_actions": len(plan.actions)}


def evaluate_candidate_delta(
    context: OperatorContext, before: Solution, after: Solution
) -> dict[str, Any]:
    b = evaluate_feasibility(context.instance, before)
    a = evaluate_feasibility(context.instance, after)
    return {
        "before_feasible": b.feasible,
        "after_feasible": a.feasible,
        "before_violations": b.violation_count,
        "after_violations": a.violation_count,
    }


# Namespace exposed to sandbox (serialized names only; parent applies plans)
APPROVED_NAMESPACE: dict[str, Callable[..., Any]] = {
    "query_time_slack": query_time_slack,
    "query_energy_slack": query_energy_slack,
    "query_load_slack": query_load_slack,
    "query_charging_detour": query_charging_detour,
    "query_station_dependency": query_station_dependency,
    "query_route_distance": query_route_distance,
    "query_route_duration": query_route_duration,
    "select_customers_by_score": select_customers_by_score,
    "plan_customer_removal": plan_customer_removal,
    "plan_segment_removal": plan_segment_removal,
    "plan_station_removal": plan_station_removal,
    "plan_station_replacement": plan_station_replacement,
    "plan_charging_reconstruction": plan_charging_reconstruction,
    "plan_regret_reinsertion": plan_regret_reinsertion,
    "plan_greedy_reinsertion": plan_greedy_reinsertion,
    "validate_operator_plan": validate_operator_plan_struct,
}


def _register_state_queries() -> None:
    from evocharge.operators import state_queries as sq

    for name in (
        "customers_in_route",
        "stations_in_route",
        "customer_positions_only",
        "non_depot_segments",
        "rank_customers_by_energy_criticality",
        "rank_segments_by_charging_detour_contribution",
        "rank_stations_by_detour",
        "enumerate_feasible_station_replacements",
        "query_downstream_charging_delay",
        "query_insertion_feasibility",
    ):
        APPROVED_NAMESPACE[name] = getattr(sq, name)


_register_state_queries()


def apply_operator_plan(
    state: ReadOnlySearchState,
    context: OperatorContext,
    plan: OperatorPlan,
) -> Solution:
    """Apply a validated plan using parent-process primitives only."""
    from evocharge.operators.handcrafted.repair import regret2_insertion
    from evocharge.solver.charging_repair import repair_charging
    from evocharge.solver.route_utils import remove_customers_from_solution

    solution = state.solution
    removed: list[str] = []
    for action in plan.actions:
        pid = action.primitive_id
        args = action.arguments
        if pid == "plan_customer_removal":
            raw_ids = args.get("customer_ids")
            ids = (
                [str(x) for x in raw_ids]
                if isinstance(raw_ids, (list, tuple))
                else ([] if raw_ids is None else [str(raw_ids)])
            )
            removed.extend(ids)
            solution = remove_customers_from_solution(
                context.instance,
                solution,
                set(ids),
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
            )
        elif pid == "plan_segment_removal":
            ri = int(str(args["route_index"]))
            start = int(str(args["start_index"]))
            end = int(str(args["end_index"]))
            route = solution.routes[ri]
            segment_custs = [
                nid
                for nid in route.node_ids[start:end]
                if nid in set(context.instance.customer_ids)
            ]
            removed.extend(segment_custs)
            solution = remove_customers_from_solution(
                context.instance,
                solution,
                set(segment_custs),
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
            )
        elif pid == "plan_station_removal":
            ri = int(str(args["route_index"]))
            sid = str(args["station_id"])
            route = solution.routes[ri]
            nodes = tuple(n for n in route.node_ids if n != sid)
            new_route = propagate_route(context.instance, nodes, vehicle_index=ri)
            routes = list(solution.routes)
            routes[ri] = new_route
            solution = Solution(routes=tuple(routes))
        elif pid == "plan_station_replacement":
            ri = int(str(args.get("route_index", 0)))
            old = str(args.get("old_station_id") or args.get("station_id") or "")
            new = str(args.get("new_station_id") or "")
            if ri < 0 or ri >= len(solution.routes) or not old or not new:
                continue
            route = solution.routes[ri]
            nodes = tuple(new if n == old else n for n in route.node_ids)
            # Prefer the explicit substitution so planned station changes are observable;
            # fall back to charging repair only if the substituted route is infeasible.
            new_route = propagate_route(context.instance, nodes, vehicle_index=ri)
            routes = list(solution.routes)
            routes[ri] = new_route
            trial = Solution(routes=tuple(routes))
            trial_report = evaluate_feasibility(context.instance, trial)
            if trial_report.feasible:
                solution = trial
            else:
                custs = tuple(
                    n for n in nodes if n in set(context.instance.customer_ids)
                )
                repaired = repair_charging(
                    context.instance,
                    custs,
                    cache=context.cache,
                    bounds=context.repair_bounds,
                    profiler=context.profiler,
                )
                if repaired.route is not None:
                    routes = list(solution.routes)
                    routes[ri] = repaired.route
                    solution = Solution(routes=tuple(routes))
                else:
                    solution = trial
        elif pid == "plan_charging_reconstruction":
            ri = int(str(args["route_index"]))
            route = solution.routes[ri]
            remaining_custs = tuple(
                n for n in route.node_ids if n in set(context.instance.customer_ids)
            )
            repaired = repair_charging(
                context.instance,
                remaining_custs,
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
            )
            if repaired.route is not None:
                routes = list(solution.routes)
                routes[ri] = repaired.route
                solution = Solution(routes=tuple(routes))
        elif pid in {"plan_regret_reinsertion", "plan_greedy_reinsertion"}:
            raw = args.get("customer_ids")
            reinsert: tuple[str, ...]
            if isinstance(raw, (list, tuple)):
                reinsert = tuple(str(x) for x in raw)
            elif raw is None:
                reinsert = tuple(removed)
            else:
                reinsert = (str(raw),)
            if reinsert:
                result = regret2_insertion(
                    solution, reinsert, context, __import__("random").Random(0)
                )
                solution = result.solution
                removed = []
    return solution
