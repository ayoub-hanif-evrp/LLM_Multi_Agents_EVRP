"""Adaptive large neighborhood search baseline (no LLM)."""
from __future__ import annotations

import math
import random
import time

from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.local_search import relocate_improve, two_opt_improve
from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    is_better,
    make_customer_stop,
    served_request_nodes,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def _request_units(spec: ProblemSpecV2) -> list[tuple[str, ...]]:
    """Atomic removal units: single customers or PD pairs."""
    if spec.capabilities.pickup_delivery and spec.requests:
        return [(req.pickup_id, req.delivery_id) for req in spec.requests]
    return [(cid,) for cid in served_request_nodes(spec)]


def _remove_nodes(solution: SolutionV2, node_ids: set[str]) -> SolutionV2:
    from evrptw_autolab.problem.v2.types import RouteStopV2

    out = clone_solution(solution)
    new_routes = []
    new_assign = []
    for route, assign in zip(out.routes, out.vehicle_assignments, strict=False):
        body = [s for s in route if s.event != "depot" and s.node_id not in node_ids]
        if not body:
            continue
        depot_id = route[0].node_id
        rebuilt = [
            RouteStopV2(depot_id, vehicle_type_id=assign, event="depot"),
            *body,
            RouteStopV2(depot_id, vehicle_type_id=assign, event="depot"),
        ]
        new_routes.append(rebuilt)
        new_assign.append(assign)
    out.routes = new_routes
    out.vehicle_assignments = new_assign
    return out


def destroy_random(spec: ProblemSpecV2, solution: SolutionV2, rng: random.Random, k: int) -> tuple[SolutionV2, list[tuple[str, ...]]]:
    units = _request_units(spec)
    present = []
    present_ids = {s.node_id for route in solution.routes for s in route}
    for unit in units:
        if all(n in present_ids for n in unit):
            present.append(unit)
    if not present:
        return clone_solution(solution), []
    k = max(1, min(k, len(present)))
    removed = rng.sample(present, k)
    nodes = {n for unit in removed for n in unit}
    return _remove_nodes(solution, nodes), removed


def destroy_worst(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    rng: random.Random,
    k: int,
    policy: object | None = None,
) -> tuple[SolutionV2, list[tuple[str, ...]]]:
    """Remove units with highest removal_priority (or due-time fallback)."""
    units = _request_units(spec)
    present = []
    present_ids = {s.node_id for route in solution.routes for s in route}
    for unit in units:
        if all(n in present_ids for n in unit):
            present.append(unit)
    if not present:
        return clone_solution(solution), []
    total_dist = max(evaluate(spec, solution).total_distance, 1e-9)
    scorer = getattr(policy, "removal_priority", None) if policy is not None else None
    scored = []
    for unit in present:
        from evrptw_autolab.components.interfaces import normalize_due_time

        dues = [normalize_due_time(spec.node_map[n].due_time) for n in unit]
        due = sum(dues) / len(dues) if dues else 0.0
        share = 1.0 / max(len(present), 1)
        rng_value = rng.random()
        if scorer is not None:
            score = float(scorer(float(due), float(share), float(rng_value)))
        else:
            score = float(due) + 10.0 * share + 0.01 * rng_value
        if score != score or score in (float("inf"), float("-inf")):
            score = 10.0 * share + 0.01 * rng_value
        scored.append((score + 1e-9 * (due / total_dist), unit))
    scored.sort(reverse=True)
    k = max(1, min(k, len(scored)))
    removed = [u for _, u in scored[:k]]
    nodes = {n for unit in removed for n in unit}
    return _remove_nodes(solution, nodes), removed


def repair_greedy(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    rng: random.Random,
    policy: object | None = None,
) -> SolutionV2:
    current = clone_solution(solution)
    vehicle_id = default_vehicle_id(spec)
    if not current.routes:
        current.routes = [empty_route(spec, vehicle_id)]
        current.vehicle_assignments = [vehicle_id]

    order = list(removed)
    rng.shuffle(order)
    for unit in order:
        best = None
        best_score = float("inf")
        if len(unit) == 1:
            node_id = unit[0]
            for r_idx, route in enumerate(current.routes):
                for pos in range(1, len(route)):
                    trial = clone_solution(current)
                    trial.routes[r_idx].insert(pos, make_customer_stop(node_id, spec))
                    report = evaluate(spec, trial)
                    hard = {v.family for v in report.violations} - {
                        "VISIT",
                        "PAIRING",
                        "BATTERY",
                        "CHARGE_POLICY",
                        "DURATION",
                    }
                    if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
                        continue
                    score = _acceptance_score(report)
                    if score < best_score:
                        best_score = score
                        best = trial
            if best is None:
                route = empty_route(spec, vehicle_id)
                route.insert(1, make_customer_stop(node_id, spec))
                current = clone_solution(current)
                current.routes.append(route)
                current.vehicle_assignments.append(vehicle_id)
            else:
                current = best
        else:
            pickup, delivery = unit[0], unit[1]
            for r_idx, route in enumerate(current.routes):
                for ppos in range(1, len(route)):
                    for dpos in range(ppos + 1, len(route) + 1):
                        trial = clone_solution(current)
                        trial.routes[r_idx].insert(ppos, make_customer_stop(pickup, spec))
                        trial.routes[r_idx].insert(dpos, make_customer_stop(delivery, spec))
                        report = evaluate(spec, trial)
                        hard = {v.family for v in report.violations} - {
                            "VISIT",
                            "PAIRING",
                            "BATTERY",
                            "CHARGE_POLICY",
                            "DURATION",
                        }
                        if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
                            continue
                        score = _acceptance_score(report)
                        if score < best_score:
                            best_score = score
                            best = trial
            if best is None:
                route = empty_route(spec, vehicle_id)
                route.insert(1, make_customer_stop(pickup, spec))
                route.insert(2, make_customer_stop(delivery, spec))
                current = clone_solution(current)
                current.routes.append(route)
                current.vehicle_assignments.append(vehicle_id)
            else:
                current = best
    current = repair_energy(spec, current, policy=policy)
    from evrptw_autolab.backbone.charge_completion import complete_solution_charges
    from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges

    current = complete_solution_charges(spec, current)
    return optimize_solution_partial_charges(spec, current)


def alns_improve(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    rng: random.Random,
    *,
    time_limit_s: float = 5.0,
    iterations: int = 80,
    policy: object | None = None,
) -> SolutionV2:
    """ALNS with random/worst destroy + greedy repair + SA acceptance."""
    start = time.monotonic()
    current = clone_solution(solution)
    current = repair_energy(spec, current, policy=policy)
    current_report = evaluate(spec, current)
    best = clone_solution(current)
    best_report = current_report

    weights = {"random": 1.0, "worst": 1.0}
    temperature = 1.0
    cooling = 0.95

    for it in range(iterations):
        if time.monotonic() - start > time_limit_s:
            break
        n_units = len(_request_units(spec))
        k = max(1, min(3, n_units // 3 or 1))
        # Roulette on destroy operators.
        total_w = sum(weights.values())
        pick = rng.random() * total_w
        acc = 0.0
        destroy_name = "random"
        for name, w in weights.items():
            acc += w
            if pick <= acc:
                destroy_name = name
                break
        if destroy_name == "worst":
            destroyed, removed = destroy_worst(spec, current, rng, k, policy=policy)
        else:
            destroyed, removed = destroy_random(spec, current, rng, k)
        if not removed:
            continue
        candidate = repair_greedy(spec, destroyed, removed, rng, policy=policy)
        if it % 5 == 0:
            candidate = relocate_improve(spec, candidate, max_passes=1)
            candidate = two_opt_improve(spec, candidate)
        cand_report = evaluate(spec, candidate)

        accept = False
        if is_better(cand_report, current_report):
            accept = True
            weights[destroy_name] += 0.5
        else:
            # Metropolis on variant objective scalar + normalized violation count.
            cur_score = _acceptance_score(current_report)
            new_score = _acceptance_score(cand_report)
            delta = new_score - cur_score
            if delta < 0 or rng.random() < math.exp(-delta / max(temperature, 1e-6)):
                accept = True
                weights[destroy_name] += 0.1
            else:
                weights[destroy_name] = max(0.2, weights[destroy_name] * 0.95)

        if accept:
            current = candidate
            current_report = cand_report
            # Incumbent updates only when strictly better (feasibility-first).
            if is_better(current_report, best_report):
                best = clone_solution(current)
                best_report = current_report
        temperature *= cooling

    from evrptw_autolab.backbone.charge_completion import complete_solution_charges
    from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges

    incumbent = clone_solution(best)
    incumbent_report = best_report
    polished = relocate_improve(spec, best, max_passes=2)
    polished = two_opt_improve(spec, polished)
    polished = repair_energy(spec, polished, policy=policy)
    polished = complete_solution_charges(spec, polished)
    polished = optimize_solution_partial_charges(spec, polished)
    polished_report = evaluate(spec, polished)
    if is_better(polished_report, incumbent_report):
        best = polished
        best_report = polished_report
    else:
        best = incumbent
        best_report = incumbent_report
    best.metadata["alns_best_feasible"] = bool(best_report.feasible)
    best.metadata["alns_iterations"] = it + 1 if iterations else 0
    return best


def _acceptance_score(report) -> float:
    """Scalar for SA only: feasibility penalty + objective + violation magnitudes."""
    penalty = 0.0 if report.feasible else 1e6
    viol = 100.0 * len(report.violations) + sum(float(v.magnitude or 0.0) for v in report.violations)
    if report.objective_key:
        obj = 0.0
        scale = 1.0
        for value in report.objective_key:
            obj += float(value) * scale
            scale *= 1e-3
    else:
        obj = float(report.objective) if report.objective is not None else report.total_distance
    return penalty + viol + obj
