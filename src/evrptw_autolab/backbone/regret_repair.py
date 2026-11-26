"""Regret-2 insertion repair for classical ALNS (non-LLM)."""
from __future__ import annotations

import random
import time

from evrptw_autolab.backbone.alns import (
    DEFAULT_REPAIR_SCORING_MODE,
    classical_repair_rank_score,
)
from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.decision_features import insertion_delta_distance
from evrptw_autolab.backbone.energy_repair import repair_energy
from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges
from evrptw_autolab.backbone.perf_counters import bump
from evrptw_autolab.backbone.route_screen import replace_route, screen_repair_route
from evrptw_autolab.backbone.util import (
    clone_solution,
    default_vehicle_id,
    empty_route,
    make_customer_stop,
    vehicle_for_route,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def _best_insertions(
    spec: ProblemSpecV2,
    current: SolutionV2,
    node_id: str,
    *,
    repair_scoring_mode: str,
    deadline: float | None,
) -> list[tuple[float, int, int, SolutionV2]]:
    """Return admissible insertions sorted by classical rank score (lower better)."""
    rows: list[tuple[float, int, int, SolutionV2]] = []
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
            bump("candidates_considered")
            trial_route = list(route)
            trial_route.insert(pos, make_customer_stop(node_id, spec))
            ok, distance = screen_repair_route(spec, trial_route, vehicle, allow_battery_debt=True)
            if not ok:
                bump("candidates_rejected_screen")
                continue
            delta = insertion_delta_distance(spec, route, pos, node_id)
            customers = sum(1 for stop in route if stop.event != "depot")
            score = classical_repair_rank_score(
                repair_scoring_mode,
                total_route_distance=float(distance),
                delta_distance=float(delta),
                route_customer_count=float(customers),
            )
            rows.append((score, r_idx, pos, replace_route(current, r_idx, trial_route)))
    rows.sort(key=lambda item: (item[0], item[1], item[2]))
    return rows


def repair_regret2(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    rng: random.Random,
    *,
    optimize_partial_charges: bool = True,
    deadline: float | None = None,
    repair_scoring_mode: str = DEFAULT_REPAIR_SCORING_MODE,
) -> SolutionV2:
    """Insert single-customer units by regret-2; PD pairs fall back to sequential greedy order.

    Regret = second_best_score - best_score over distinct routes when possible.
    Requests with fewer than two alternatives get a large regret so they insert first.
    """
    if spec.capabilities.pickup_delivery and any(len(unit) > 1 for unit in removed):
        # Keep PD atomicity via the standard greedy path for pairs.
        from evrptw_autolab.backbone.alns import repair_greedy

        return repair_greedy(
            spec,
            solution,
            removed,
            rng,
            policy=None,
            optimize_partial_charges=optimize_partial_charges,
            deadline=deadline,
            repair_scoring_mode=repair_scoring_mode,
        )

    current = clone_solution(solution)
    vehicle_id = default_vehicle_id(spec)
    if not current.routes:
        current.routes = [empty_route(spec, vehicle_id)]
        current.vehicle_assignments = [vehicle_id]
    current.metadata["repair_scoring_mode"] = str(repair_scoring_mode)
    current.metadata["repair_algorithm"] = "regret2"

    pending = [unit[0] for unit in removed if len(unit) == 1]
    rng.shuffle(pending)

    while pending:
        if deadline is not None and time.monotonic() > deadline:
            break
        ranked: list[tuple[float, float, str, SolutionV2]] = []
        for node_id in pending:
            options = _best_insertions(
                spec,
                current,
                node_id,
                repair_scoring_mode=repair_scoring_mode,
                deadline=deadline,
            )
            if not options:
                # Force new route; treat as urgent.
                route = empty_route(spec, vehicle_id)
                route.insert(1, make_customer_stop(node_id, spec))
                opened = clone_solution(current)
                opened.routes.append(route)
                opened.vehicle_assignments.append(vehicle_id)
                ranked.append((1.0e12, 0.0, node_id, opened))
                continue
            best = options[0]
            # Prefer second-best on a different route when available.
            second_score = best[0]
            for cand in options[1:]:
                if cand[1] != best[1]:
                    second_score = cand[0]
                    break
            else:
                if len(options) > 1:
                    second_score = options[1][0]
                else:
                    second_score = best[0] + 1.0e6
            regret = float(second_score - best[0])
            ranked.append((regret, -best[0], node_id, best[3]))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        _regret, _neg_best, chosen_id, chosen_sol = ranked[0]
        current = chosen_sol
        pending.remove(chosen_id)

    current = repair_energy(spec, current, policy=None, deadline=deadline)
    current = complete_solution_charges(spec, current)
    if not optimize_partial_charges:
        return current
    return optimize_solution_partial_charges(spec, current)
