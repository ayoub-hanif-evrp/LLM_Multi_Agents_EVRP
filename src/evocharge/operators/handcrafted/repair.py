"""Handcrafted repair operators."""

from __future__ import annotations

import random
from collections.abc import Callable

from evocharge.domain.route import Route
from evocharge.domain.solution import Solution
from evocharge.operators.api import OperatorContext, RepairResult
from evocharge.solver.insertion import (
    best_insertions_for_customer,
    open_route_for_customer,
)
from evocharge.solver.route_utils import customer_sequence_of


def _served(solution: Solution, instance) -> set[str]:
    out: set[str] = set()
    for route in solution.routes:
        out.update(customer_sequence_of(route, instance))
    return out


def _apply_candidate(routes: list[Route], cand) -> list[Route]:
    if cand.route_index >= len(routes):
        routes.append(cand.route)
    else:
        routes[cand.route_index] = cand.route
    return [
        Route(vehicle_index=i, node_ids=r.node_ids, schedule=r.schedule, metadata=r.metadata)
        for i, r in enumerate(routes)
    ]


def greedy_feasible_insertion(
    solution: Solution,
    removed: tuple[str, ...],
    context: OperatorContext,
    rng: random.Random,
) -> RepairResult:
    _ = rng
    instance = context.instance
    routes = list(solution.routes)
    inserted: list[str] = []
    unserved: list[str] = []
    rejections: list[str] = []
    pending = list(removed)
    # Also include currently missing customers
    missing = [c for c in instance.customer_ids if c not in _served(solution, instance)]
    for c in missing:
        if c not in pending:
            pending.append(c)

    while pending:
        progress = False
        best_pair = None
        for cid in list(pending):
            cands = best_insertions_for_customer(
                instance,
                tuple(routes),
                cid,
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
                top_k=1,
            )
            opened = open_route_for_customer(
                instance,
                cid,
                vehicle_index=len(routes),
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
            )
            choices = [c for c in cands if c.rejection is None]
            if opened.rejection is None:
                choices.append(opened)
            if not choices:
                continue
            choices.sort(key=lambda c: c.cost_delta)
            cand = choices[0]
            if best_pair is None or cand.cost_delta < best_pair[1].cost_delta:
                best_pair = (cid, cand)
        if best_pair is None:
            for cid in pending:
                unserved.append(cid)
                rejections.append("no_feasible_insertion")
            break
        cid, cand = best_pair
        routes = _apply_candidate(routes, cand)
        pending.remove(cid)
        inserted.append(cid)
        progress = True
        _ = progress

    return RepairResult(
        solution=Solution(routes=tuple(routes), metadata=dict(solution.metadata)),
        inserted_customers=tuple(inserted),
        unserved=tuple(unserved),
        operator="greedy_feasible_insertion",
        rejection_reasons=tuple(rejections),
    )


def _regret_repair(
    solution: Solution,
    removed: tuple[str, ...],
    context: OperatorContext,
    rng: random.Random,
    k: int,
    name: str,
) -> RepairResult:
    _ = rng
    instance = context.instance
    routes = list(solution.routes)
    inserted: list[str] = []
    unserved: list[str] = []
    rejections: list[str] = []
    pending = list(removed)
    missing = [c for c in instance.customer_ids if c not in _served(solution, instance)]
    for c in missing:
        if c not in pending:
            pending.append(c)

    while pending:
        best_cid = None
        best_cand = None
        best_regret = -1.0
        for cid in list(pending):
            cands = best_insertions_for_customer(
                instance,
                tuple(routes),
                cid,
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
                top_k=k,
            )
            opened = open_route_for_customer(
                instance,
                cid,
                vehicle_index=len(routes),
                cache=context.cache,
                bounds=context.repair_bounds,
                profiler=context.profiler,
            )
            costs = [c.cost_delta for c in cands if c.rejection is None]
            if opened.rejection is None:
                costs.append(opened.cost_delta)
                cands = list(cands) + [opened]
            feasible = [c for c in cands if c.rejection is None]
            if not feasible:
                continue
            feasible.sort(key=lambda c: c.cost_delta)
            first = feasible[0].cost_delta
            if len(feasible) >= k:
                regret = feasible[k - 1].cost_delta - first
            elif len(feasible) >= 2:
                regret = feasible[-1].cost_delta - first
            else:
                regret = first  # prefer opening expensive singles later via regret~cost
            if regret > best_regret:
                best_regret = regret
                best_cid = cid
                best_cand = feasible[0]
        if best_cid is None or best_cand is None:
            for cid in pending:
                unserved.append(cid)
                rejections.append("no_feasible_insertion")
            break
        routes = _apply_candidate(routes, best_cand)
        pending.remove(best_cid)
        inserted.append(best_cid)

    return RepairResult(
        solution=Solution(routes=tuple(routes), metadata=dict(solution.metadata)),
        inserted_customers=tuple(inserted),
        unserved=tuple(unserved),
        operator=name,
        rejection_reasons=tuple(rejections),
    )


def regret2_insertion(
    solution: Solution,
    removed: tuple[str, ...],
    context: OperatorContext,
    rng: random.Random,
) -> RepairResult:
    return _regret_repair(solution, removed, context, rng, k=2, name="regret2_insertion")


def regret3_insertion(
    solution: Solution,
    removed: tuple[str, ...],
    context: OperatorContext,
    rng: random.Random,
) -> RepairResult:
    return _regret_repair(solution, removed, context, rng, k=3, name="regret3_insertion")


def time_energy_aware_insertion(
    solution: Solution,
    removed: tuple[str, ...],
    context: OperatorContext,
    rng: random.Random,
) -> RepairResult:
    """Greedy insertion ordered by tight TW then low energy slack proxy."""
    instance = context.instance
    ordered = sorted(
        removed,
        key=lambda cid: (
            instance.nodes[cid].due_time - instance.nodes[cid].ready_time,
            instance.nodes[cid].due_time,
            cid,
        ),
    )
    # Insert in that order greedily
    routes = list(solution.routes)
    inserted: list[str] = []
    unserved: list[str] = []
    rejections: list[str] = []
    pending = list(ordered)
    missing = [c for c in instance.customer_ids if c not in _served(solution, instance)]
    for c in missing:
        if c not in pending:
            pending.append(c)
    for cid in list(pending):
        cands = best_insertions_for_customer(
            instance,
            tuple(routes),
            cid,
            cache=context.cache,
            bounds=context.repair_bounds,
            profiler=context.profiler,
            top_k=3,
        )
        # Prefer insertions with higher resulting min energy slack
        scored = []
        for cand in cands:
            if cand.rejection is not None:
                continue
            min_slack = min((s.energy_slack for s in cand.route.schedule), default=0.0)
            scored.append((cand.cost_delta - 0.01 * min_slack, cand))
        opened = open_route_for_customer(
            instance,
            cid,
            vehicle_index=len(routes),
            cache=context.cache,
            bounds=context.repair_bounds,
            profiler=context.profiler,
        )
        if opened.rejection is None:
            min_slack = min((s.energy_slack for s in opened.route.schedule), default=0.0)
            scored.append((opened.cost_delta - 0.01 * min_slack, opened))
        if not scored:
            unserved.append(cid)
            rejections.append("no_feasible_insertion")
            continue
        scored.sort(key=lambda x: x[0])
        routes = _apply_candidate(routes, scored[0][1])
        inserted.append(cid)
        pending.remove(cid)
    _ = rng
    return RepairResult(
        solution=Solution(routes=tuple(routes), metadata=dict(solution.metadata)),
        inserted_customers=tuple(inserted),
        unserved=tuple(unserved),
        operator="time_energy_aware_insertion",
        rejection_reasons=tuple(rejections),
    )


REPAIR_OPERATORS: dict[str, Callable[..., RepairResult]] = {
    "greedy_feasible_insertion": greedy_feasible_insertion,
    "regret2_insertion": regret2_insertion,
    "regret3_insertion": regret3_insertion,
    "time_energy_aware_insertion": time_energy_aware_insertion,
}
