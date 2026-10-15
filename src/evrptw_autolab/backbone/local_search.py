"""Deterministic local-search neighborhoods."""
from __future__ import annotations

from evrptw_autolab.backbone.util import clone_solution, evaluate, is_better, make_customer_stop
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2


def _is_request_node(spec: ProblemSpecV2, node_id: str) -> bool:
    kind = spec.node_map[node_id].kind
    return kind in {"customer", "pickup", "delivery"}


def relocate_improve(spec: ProblemSpecV2, solution: SolutionV2, *, max_passes: int = 3) -> SolutionV2:
    """Relocate customer/pickup/delivery nodes to cheaper feasible positions."""
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for _ in range(max_passes):
        improved = False
        for r_idx, route in enumerate(current.routes):
            for i in range(1, len(route) - 1):
                if not _is_request_node(spec, route[i].node_id):
                    continue
                node_id = route[i].node_id
                # Remove then reinsert.
                base = clone_solution(current)
                del base.routes[r_idx][i]
                # Drop empty customer-less routes later.
                for rr, rt in enumerate(base.routes):
                    for pos in range(1, len(rt)):
                        if rr == r_idx and pos == i:
                            continue
                        trial = clone_solution(base)
                        trial.routes[rr].insert(pos, make_customer_stop(node_id, spec))
                        # Clean empty routes (only depot-depot).
                        trial.routes = [r for r in trial.routes if len(r) > 2]
                        trial.vehicle_assignments = trial.vehicle_assignments[: len(trial.routes)]
                        while len(trial.vehicle_assignments) < len(trial.routes):
                            trial.vehicle_assignments.append(current.vehicle_assignments[0])
                        report = evaluate(spec, trial)
                        if is_better(report, current_report):
                            current = trial
                            current_report = report
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return current


def two_opt_improve(spec: ProblemSpecV2, solution: SolutionV2) -> SolutionV2:
    """Intra-route 2-opt on customer sequences (keeps depots fixed)."""
    if spec.capabilities.pickup_delivery:
        # 2-opt can break PD precedence; skip for PD instances.
        return solution
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for r_idx, route in enumerate(current.routes):
        n = len(route)
        if n < 5:
            continue
        improved = True
        while improved:
            improved = False
            for i in range(1, n - 2):
                for j in range(i + 1, n - 1):
                    trial = clone_solution(current)
                    segment = trial.routes[r_idx][i : j + 1]
                    trial.routes[r_idx][i : j + 1] = list(reversed(segment))
                    report = evaluate(spec, trial)
                    if is_better(report, current_report):
                        current = trial
                        current_report = report
                        improved = True
                        break
                if improved:
                    break
    return current
