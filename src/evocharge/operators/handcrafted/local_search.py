"""Basic local search with mandatory validation."""

from __future__ import annotations

from evocharge.domain.instance import Instance
from evocharge.domain.route import Route
from evocharge.domain.solution import Solution
from evocharge.solver.charging_repair import ChargingRepairCache, RepairBounds, repair_charging
from evocharge.solver.feasibility import evaluate_feasibility, evaluate_objective
from evocharge.solver.route_utils import customer_sequence_of


def _rebuild_routes(
    instance: Instance,
    sequences: list[tuple[str, ...]],
    cache: ChargingRepairCache,
    bounds: RepairBounds | None = None,
) -> Solution | None:
    routes: list[Route] = []
    for seq in sequences:
        if not seq:
            continue
        repaired = repair_charging(
            instance, seq, vehicle_index=len(routes), cache=cache, bounds=bounds
        )
        if repaired.status != "success" or repaired.route is None:
            return None
        routes.append(repaired.route)
    sol = Solution(routes=tuple(routes))
    report = evaluate_feasibility(instance, sol)
    return sol if report.feasible else None


def local_search(
    instance: Instance,
    solution: Solution,
    *,
    cache: ChargingRepairCache,
    max_moves: int = 50,
    bounds: RepairBounds | None = None,
) -> Solution:
    """First-improvement relocate / swap / 2-opt on customer sequences."""
    current = solution
    cur_obj = evaluate_objective(instance, current)
    moves = 0

    def sequences() -> list[list[str]]:
        return [list(customer_sequence_of(r, instance)) for r in current.routes]

    improved = True
    while improved and moves < max_moves:
        improved = False
        seqs = sequences()
        for r_i, seq_i in enumerate(seqs):
            for idx, cust in enumerate(list(seq_i)):
                for r_j, seq_j in enumerate(seqs):
                    for pos in range(len(seq_j) + 1):
                        if r_i == r_j and (pos == idx or pos == idx + 1):
                            continue
                        new_seqs = [list(s) for s in seqs]
                        new_seqs[r_i].pop(idx if r_i != r_j else idx)
                        insert_pos = pos
                        if r_i == r_j and pos > idx:
                            insert_pos -= 1
                        new_seqs[r_j].insert(insert_pos, cust)
                        cand = _rebuild_routes(
                            instance,
                            [tuple(s) for s in new_seqs if s],
                            cache,
                            bounds=bounds,
                        )
                        moves += 1
                        if cand is None:
                            continue
                        obj = evaluate_objective(instance, cand)
                        if obj.as_tuple() < cur_obj.as_tuple():
                            current = cand
                            cur_obj = obj
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if improved:
            continue

        seqs = sequences()
        flat = [(ri, i, c) for ri, seq in enumerate(seqs) for i, c in enumerate(seq)]
        for a in range(len(flat)):
            for b in range(a + 1, len(flat)):
                ri, i, ca = flat[a]
                rj, j, cb = flat[b]
                new_seqs = [list(s) for s in seqs]
                new_seqs[ri][i], new_seqs[rj][j] = cb, ca
                cand = _rebuild_routes(
                    instance,
                    [tuple(s) for s in new_seqs if s],
                    cache,
                    bounds=bounds,
                )
                moves += 1
                if cand is None:
                    continue
                obj = evaluate_objective(instance, cand)
                if obj.as_tuple() < cur_obj.as_tuple():
                    current = cand
                    cur_obj = obj
                    improved = True
                    break
            if improved:
                break
        if improved:
            continue

        seqs = sequences()
        for ri, seq in enumerate(seqs):
            if len(seq) < 4:
                continue
            for i in range(len(seq) - 1):
                for k in range(i + 1, len(seq)):
                    new_seq = seq[:i] + list(reversed(seq[i : k + 1])) + seq[k + 1 :]
                    new_seqs = [list(s) for s in seqs]
                    new_seqs[ri] = new_seq
                    cand = _rebuild_routes(
                        instance,
                        [tuple(s) for s in new_seqs if s],
                        cache,
                        bounds=bounds,
                    )
                    moves += 1
                    if cand is None:
                        continue
                    obj = evaluate_objective(instance, cand)
                    if obj.as_tuple() < cur_obj.as_tuple():
                        current = cand
                        cur_obj = obj
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break

    return current
