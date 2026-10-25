"""Adaptive large neighborhood search baseline (no LLM)."""
from __future__ import annotations

import math
import random
import time
from typing import Any

from evrptw_autolab.backbone.construct import insert_customer_fast
from evrptw_autolab.backbone.decision_features import (
    edited_route_features,
    insertion_features_v4,
    marginal_removal_distance,
    time_window_width,
)
from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.local_search import relocate_improve, two_opt_improve
from evrptw_autolab.backbone.util import (
    call_scorer,
    clone_solution,
    default_vehicle_id,
    empty_route,
    evaluate,
    is_better,
    make_customer_stop,
    note_decision,
    note_scorer_call,
    note_selected_move,
    served_request_nodes,
    vehicle_for_route,
)
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V4
from evrptw_autolab.problem.v2.transport import travel_distance
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


def _route_travel_distance(spec: ProblemSpecV2, route: list) -> float:
    """Length of one route. This is not the constant route_distance_share."""
    total = 0.0
    nodes = spec.node_map
    for left, right in zip(route, route[1:], strict=False):
        total += travel_distance(spec, nodes[left.node_id], nodes[right.node_id])
    return total


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
    route_length: dict[str, float] = {}
    for route in solution.routes:
        length = _route_travel_distance(spec, route)
        for stop in route:
            if stop.event != "depot":
                route_length[stop.node_id] = length
    scorer = getattr(policy, "removal_priority", None) if policy is not None else None
    scored = []
    for unit in present:
        from evrptw_autolab.backbone.util import finite_due

        dues = [finite_due(spec.node_map[n].due_time) for n in unit]
        due = sum(dues) / len(dues) if dues else 0.0
        share = 1.0 / max(len(present), 1)
        rng_value = rng.random()
        own_route = max((route_length.get(node_id, 0.0) for node_id in unit), default=0.0)
        host = next(
            (
                route
                for route in solution.routes
                if set(unit) <= {stop.node_id for stop in route}
            ),
            [],
        )
        marginal = marginal_removal_distance(spec, host, set(unit)) if host else 0.0
        width = sum(time_window_width(spec, node_id) for node_id in unit) / max(len(unit), 1)
        if scorer is not None:
            note_scorer_call(policy, "removal_priority")
            score = call_scorer(
                scorer,
                {
                    "due_time": float(due),
                    "route_distance_share": float(share),
                    "rng_value": float(rng_value),
                    "own_route_distance": float(own_route),
                    "marginal_removal_distance": float(marginal),
                    "time_window_width": float(width),
                },
                ("due_time", "route_distance_share", "rng_value"),
            )
        else:
            score = float(due) + 10.0 * share + 0.01 * rng_value
        if score != score or score in (float("inf"), float("-inf")):
            score = 10.0 * share + 0.01 * rng_value
        scored.append((score + 1e-9 * (due / total_dist), unit))
    scored.sort(reverse=True)
    if scored:
        note_selected_move(
            policy,
            "removal_priority",
            ",".join(scored[0][1]),
            [",".join(unit) for _, unit in scored],
        )
    k = max(1, min(k, len(scored)))
    removed = [u for _, u in scored[:k]]
    nodes = {n for unit in removed for n in unit}
    return _remove_nodes(solution, nodes), removed


def _v4_insertion(policy: object | None) -> bool:
    return bool(
        policy is not None
        and getattr(policy, "feature_schema", "") == FEATURE_SCHEMA_V4
        and getattr(policy, "insertion_score", None) is not None
    )


def _repair_one_v4(
    spec: ProblemSpecV2,
    current: SolutionV2,
    node_id: str,
    policy: Any,
    vehicle_id: str,
    deadline: float | None,
) -> SolutionV2:
    """Rank screened insertions with the v4 policy. Feasibility stays outside the scorer."""
    screened: list[tuple[float, float, int, int, SolutionV2]] = []
    objective_best: tuple[float, int, int] | None = None
    for r_idx, route in enumerate(current.routes):
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            vehicle = vehicle_for_route(spec, current, r_idx)
        except ValueError:
            continue
        for pos in range(1, len(route)):
            if deadline is not None and time.monotonic() > deadline:
                break
            trial = clone_solution(current)
            trial.routes[r_idx].insert(pos, make_customer_stop(node_id, spec))
            report = evaluate(spec, trial)
            hard = {item.family for item in report.violations} - {
                "VISIT",
                "PAIRING",
                "BATTERY",
                "CHARGE_POLICY",
                "DURATION",
            }
            if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
                continue
            features = insertion_features_v4(spec, route, pos, node_id, vehicle)
            note_scorer_call(policy, "insertion_score")
            scorer = policy.insertion_score
            score = call_scorer(scorer, features, ())
            objective = _acceptance_score(report)
            screened.append((float(score), objective, r_idx, pos, trial))
            if objective_best is None or objective < objective_best[0]:
                objective_best = (objective, r_idx, pos)
    if not screened:
        route = empty_route(spec, vehicle_id)
        route.insert(1, make_customer_stop(node_id, spec))
        opened = clone_solution(current)
        opened.routes.append(route)
        opened.vehicle_assignments.append(vehicle_id)
        return opened
    screened.sort(key=lambda item: (item[0], item[2], item[3]))
    chosen = screened[0]
    objective_label = None if objective_best is None else f"{objective_best[1]}:{objective_best[2]}"
    note_selected_move(
        policy,
        "insertion_score",
        f"{node_id}:{chosen[2]}:{chosen[3]}",
        [f"{node_id}:{item[2]}:{item[3]}" for item in screened],
    )
    note_decision(
        policy,
        {
            "stage": "alns_repair",
            "customer": node_id,
            "candidates": len(screened),
            "selected": f"{chosen[2]}:{chosen[3]}",
            "objective_best": objective_label,
            "changed_from_objective": f"{chosen[2]}:{chosen[3]}" != objective_label,
            "policy_score": chosen[0],
        },
    )
    return chosen[4]


def _repair_pair_v4(
    spec: ProblemSpecV2,
    current: SolutionV2,
    pickup: str,
    delivery: str,
    policy: Any,
    vehicle_id: str,
    deadline: float | None,
) -> SolutionV2:
    """Rank screened pickup-delivery insertions. The pair is never split."""
    screened: list[tuple[float, float, int, SolutionV2, str]] = []
    objective_best: str | None = None
    objective_score = float("inf")
    for r_idx, route in enumerate(current.routes):
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            vehicle = vehicle_for_route(spec, current, r_idx)
        except ValueError:
            continue
        for ppos in range(1, len(route)):
            for dpos in range(ppos + 1, len(route) + 1):
                if deadline is not None and time.monotonic() > deadline:
                    break
                trial = clone_solution(current)
                trial.routes[r_idx].insert(ppos, make_customer_stop(pickup, spec))
                trial.routes[r_idx].insert(dpos, make_customer_stop(delivery, spec))
                report = evaluate(spec, trial)
                hard = {item.family for item in report.violations} - {
                    "VISIT",
                    "PAIRING",
                    "BATTERY",
                    "CHARGE_POLICY",
                    "DURATION",
                }
                if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
                    continue
                features = edited_route_features(spec, route, trial.routes[r_idx], vehicle)
                note_scorer_call(policy, "insertion_score")
                score = float(call_scorer(policy.insertion_score, features, ()))
                objective = _acceptance_score(report)
                label = f"{r_idx}:{ppos}:{dpos}"
                screened.append((score, objective, r_idx, trial, label))
                if objective < objective_score:
                    objective_score = objective
                    objective_best = label
    if not screened:
        opened = clone_solution(current)
        route = empty_route(spec, vehicle_id)
        route.insert(1, make_customer_stop(pickup, spec))
        route.insert(2, make_customer_stop(delivery, spec))
        opened.routes.append(route)
        opened.vehicle_assignments.append(vehicle_id)
        return opened
    screened.sort(key=lambda item: (item[0], item[4]))
    chosen = screened[0]
    note_decision(
        policy,
        {
            "stage": "alns_repair_pair",
            "customer": f"{pickup}+{delivery}",
            "candidates": len(screened),
            "selected": chosen[4],
            "objective_best": objective_best,
            "changed_from_objective": chosen[4] != objective_best,
            "policy_score": chosen[0],
        },
    )
    return chosen[3]


def _repair_one_selective(
    spec: ProblemSpecV2,
    current: SolutionV2,
    node_id: str,
    policy: Any,
    vehicle_id: str,
    deadline: float | None,
    partition: str,
) -> SolutionV2:
    """Rank feasible insertions with the selective controller. Physics screening stays here."""
    from evrptw_autolab.discovery.schemas import OperatorSpec
    from evrptw_autolab.transfer.context_features import search_context
    from evrptw_autolab.transfer.search_decision import ScreenedRepair, choose_screened_repair

    if not isinstance(policy, OperatorSpec):
        raise TypeError("selective repair requires an OperatorSpec")
    rows: list[ScreenedRepair] = []
    for r_idx, route in enumerate(current.routes):
        if deadline is not None and time.monotonic() > deadline:
            break
        try:
            vehicle = vehicle_for_route(spec, current, r_idx)
        except ValueError:
            continue
        for pos in range(1, len(route)):
            if deadline is not None and time.monotonic() > deadline:
                break
            trial = clone_solution(current)
            trial.routes[r_idx].insert(pos, make_customer_stop(node_id, spec))
            report = evaluate(spec, trial)
            hard = {item.family for item in report.violations} - {
                "VISIT",
                "PAIRING",
                "BATTERY",
                "CHARGE_POLICY",
                "DURATION",
            }
            if hard & {"PARSE", "DEPOT", "CAPACITY", "WINDOW", "PRECEDENCE"}:
                continue
            rows.append(
                ScreenedRepair(
                    label=f"{r_idx}:{pos}",
                    features=insertion_features_v4(spec, route, pos, node_id, vehicle),
                    solution=trial,
                    objective=tuple(float(value) for value in report.objective_key),
                    feasible=bool(report.feasible),
                    acceptance=_acceptance_score(report),
                )
            )
    if not rows:
        route = empty_route(spec, vehicle_id)
        route.insert(1, make_customer_stop(node_id, spec))
        opened = clone_solution(current)
        opened.routes.append(route)
        opened.vehicle_assignments.append(vehicle_id)
        return opened
    decision = choose_screened_repair(
        spec,
        policy,
        rows,
        search_context(spec, current),
        seed=0,
        partition=partition,
        mine=bool(policy.mine_counterexamples),
    )
    return decision.solution


def repair_greedy(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    rng: random.Random,
    policy: object | None = None,
    *,
    optimize_partial_charges: bool = True,
    deadline: float | None = None,
    partition: str = "development",
) -> SolutionV2:
    current = clone_solution(solution)
    vehicle_id = default_vehicle_id(spec)
    if not current.routes:
        current.routes = [empty_route(spec, vehicle_id)]
        current.vehicle_assignments = [vehicle_id]

    order = list(removed)
    rng.shuffle(order)
    from evrptw_autolab.discovery.schemas import OperatorSpec

    for unit in order:
        if deadline is not None and time.monotonic() > deadline:
            break
        best = None
        best_score = float("inf")
        if len(unit) == 1:
            node_id = unit[0]
            if isinstance(policy, OperatorSpec) and policy.operator_family == "repair":
                current = _repair_one_selective(
                    spec, current, node_id, policy, vehicle_id, deadline, partition
                )
                continue
            if _v4_insertion(policy):
                current = _repair_one_v4(spec, current, node_id, policy, vehicle_id, deadline)
                continue
            if spec.capabilities.heterogeneous_fleet:
                current = insert_customer_fast(spec, current, node_id, policy=policy)
                continue
            for r_idx, route in enumerate(current.routes):
                if deadline is not None and time.monotonic() > deadline:
                    break
                for pos in range(1, len(route)):
                    if deadline is not None and time.monotonic() > deadline:
                        break
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
            if _v4_insertion(policy):
                current = _repair_pair_v4(spec, current, pickup, delivery, policy, vehicle_id, deadline)
                continue
            for r_idx, route in enumerate(current.routes):
                if deadline is not None and time.monotonic() > deadline:
                    break
                for ppos in range(1, len(route)):
                    if deadline is not None and time.monotonic() > deadline:
                        break
                    for dpos in range(ppos + 1, len(route) + 1):
                        if deadline is not None and time.monotonic() > deadline:
                            break
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
    current = repair_energy(spec, current, policy=policy, deadline=deadline)
    from evrptw_autolab.backbone.charge_completion import complete_solution_charges
    from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges

    current = complete_solution_charges(spec, current)
    if not optimize_partial_charges:
        return current
    return optimize_solution_partial_charges(spec, current)


def _select_destroy(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    policy: object | None,
    rng: random.Random,
    weights: dict[str, float],
    trace: list[dict[str, str]],
) -> str:
    """Classical roulette, unless a destroy operator is selected."""
    from evrptw_autolab.discovery.schemas import OperatorSpec
    from evrptw_autolab.transfer.operators import choose_destroy

    if not isinstance(policy, OperatorSpec) or policy.operator_family != "destroy":
        return _roulette_destroy(rng, weights)
    name, action = choose_destroy(spec, policy, solution, rng, weights)
    trace.append({"name": name, "action": action})
    return name


def _roulette_destroy(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(weights.values())
    pick = rng.random() * total
    acc = 0.0
    chosen = "random"
    for name, weight in weights.items():
        acc += weight
        if pick <= acc:
            chosen = name
            break
    return chosen


def alns_improve(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    rng: random.Random,
    *,
    time_limit_s: float = 5.0,
    iterations: int = 80,
    policy: object | None = None,
    deadline: float | None = None,
    optimize_partial_charges: bool = True,
    adaptive_destroy: bool = True,
    heavy_local: bool = True,
) -> SolutionV2:
    """ALNS with random/worst destroy + greedy repair + SA acceptance."""
    start = time.monotonic()
    end_by = start + float(time_limit_s)
    if deadline is not None:
        end_by = min(end_by, float(deadline))
    current = clone_solution(solution)
    current = repair_energy(spec, current, policy=policy, deadline=end_by)
    current_report = evaluate(spec, current)
    best = clone_solution(current)
    best_report = current_report

    weights = {"random": 1.0, "worst": 1.0}
    destroy_trace: list[dict[str, str]] = []
    temperature = 1.0
    cooling = 0.95
    it = -1

    for it in range(iterations):
        if time.monotonic() > end_by:
            break
        n_units = len(_request_units(spec))
        k = max(1, min(3, n_units // 3 or 1))
        destroy_name = _select_destroy(spec, current, policy, rng, weights, destroy_trace)
        if destroy_name == "worst":
            destroyed, removed = destroy_worst(spec, current, rng, k, policy=policy)
        else:
            destroyed, removed = destroy_random(spec, current, rng, k)
        if not removed:
            continue
        candidate = repair_greedy(
            spec,
            destroyed,
            removed,
            rng,
            policy=policy,
            optimize_partial_charges=optimize_partial_charges,
            deadline=end_by,
        )
        if it % 5 == 0 and heavy_local:
            candidate = relocate_improve(spec, candidate, max_passes=1, deadline=end_by)
            candidate = two_opt_improve(spec, candidate, deadline=end_by)
        cand_report = evaluate(spec, candidate)

        accept = False
        if is_better(cand_report, current_report):
            accept = True
            if adaptive_destroy:
                weights[destroy_name] += 0.5
        else:
            # Metropolis on variant objective scalar + normalized violation count.
            cur_score = _acceptance_score(current_report)
            new_score = _acceptance_score(cand_report)
            delta = new_score - cur_score
            if delta < 0 or rng.random() < math.exp(-delta / max(temperature, 1e-6)):
                accept = True
                if adaptive_destroy:
                    weights[destroy_name] += 0.1
            elif adaptive_destroy:
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
    if time.monotonic() < end_by and heavy_local:
        polished = relocate_improve(spec, best, max_passes=2, deadline=end_by)
        polished = two_opt_improve(spec, polished, deadline=end_by)
        polished = repair_energy(spec, polished, policy=policy, deadline=end_by)
        polished = complete_solution_charges(spec, polished)
        if optimize_partial_charges:
            polished = optimize_solution_partial_charges(spec, polished)
        polished_report = evaluate(spec, polished)
        if is_better(polished_report, incumbent_report):
            best = polished
            best_report = polished_report
        else:
            best = incumbent
            best_report = incumbent_report
    else:
        best = incumbent
        best_report = incumbent_report
    if destroy_trace:
        best.metadata["destroy_trace"] = destroy_trace
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
