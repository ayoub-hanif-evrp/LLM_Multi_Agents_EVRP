"""Initial feasible solution construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.domain.solution import Solution
from evocharge.solver.charging_repair import ChargingRepairCache, RepairBounds
from evocharge.solver.feasibility import evaluate_feasibility, evaluate_objective
from evocharge.solver.insertion import best_insertions_for_customer, open_route_for_customer
from evocharge.solver.profiling import Profiler


@dataclass
class ConstructionResult:
    solution: Solution | None
    feasible: bool
    unserved: list[str] = field(default_factory=list)
    rejection_log: list[dict[str, Any]] = field(default_factory=list)
    cache: ChargingRepairCache | None = None
    profiler: Profiler | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def construct_initial_solution(
    instance: Instance,
    *,
    cache: ChargingRepairCache | None = None,
    bounds: RepairBounds | None = None,
    profiler: Profiler | None = None,
    seed_order: str = "due_time",
) -> ConstructionResult:
    """Build a feasible solution by sequential insertion + charging repair."""
    cache = cache or ChargingRepairCache()
    bounds = bounds or RepairBounds()
    profiler = profiler or Profiler()
    if seed_order == "due_time":
        order = sorted(
            instance.customer_ids,
            key=lambda cid: (instance.nodes[cid].due_time, cid),
        )
    else:
        order = list(instance.customer_ids)

    routes: list[Route] = []
    rejections: list[dict[str, Any]] = []
    unserved: list[str] = []

    with profiler.section("construction"):
        for cid in order:
            best = None
            if routes:
                cands = best_insertions_for_customer(
                    instance,
                    tuple(routes),
                    cid,
                    cache=cache,
                    bounds=bounds,
                    profiler=profiler,
                    top_k=1,
                )
                if cands:
                    best = cands[0]
            opened = open_route_for_customer(
                instance,
                cid,
                vehicle_index=len(routes),
                cache=cache,
                bounds=bounds,
                profiler=profiler,
            )
            chosen = None
            if best is not None and best.rejection is None:
                if opened.rejection is None:
                    chosen = best if best.cost_delta <= opened.cost_delta else opened
                else:
                    chosen = best
            elif opened.rejection is None:
                chosen = opened
            else:
                unserved.append(cid)
                rejections.append(
                    {
                        "customer": cid,
                        "existing_best": best.rejection if best else "no_route",
                        "open_route": opened.rejection,
                    }
                )
                continue

            assert chosen is not None and chosen.rejection is None
            if chosen.route_index >= len(routes):
                routes.append(chosen.route)
            else:
                routes[chosen.route_index] = chosen.route

    routes = [r for r in routes if len(r.node_ids) > 2]
    routes = [
        Route(vehicle_index=i, node_ids=r.node_ids, schedule=r.schedule, metadata=r.metadata)
        for i, r in enumerate(routes)
    ]
    solution = Solution(routes=tuple(routes), metadata={"construction": seed_order})
    with profiler.section("feasibility"):
        report = evaluate_feasibility(instance, solution)
        obj = evaluate_objective(instance, solution, report)
    return ConstructionResult(
        solution=solution,
        feasible=report.feasible,
        unserved=unserved or list(report.missing_customers),
        rejection_log=rejections,
        cache=cache,
        profiler=profiler,
        metadata={
            "objective": obj.model_dump(),
            "cache": cache.stats(),
            "profile": profiler.snapshot(),
            "feasible": report.feasible,
        },
    )
