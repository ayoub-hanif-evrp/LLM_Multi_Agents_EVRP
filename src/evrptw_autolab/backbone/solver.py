"""Classical non-LLM solver entry point."""
from __future__ import annotations

import multiprocessing as mp
import os
import pickle
import random
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.alns import alns_improve
from evrptw_autolab.backbone.charge_completion import complete_solution_charges
from evrptw_autolab.backbone.construct import construct_greedy
from evrptw_autolab.backbone.energy_repair import remove_redundant_stations, repair_energy
from evrptw_autolab.backbone.local_search import (
    merge_routes_improve,
    relocate_improve,
    two_opt_improve,
)
from evrptw_autolab.backbone.nonlinear_charge import optimize_solution_partial_charges
from evrptw_autolab.backbone.route_split import split_infeasible_routes
from evrptw_autolab.backbone.util import (
    candidate_vehicle_ids,
    clone_solution,
    empty_route,
    evaluate,
    is_better,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2, RouteStopV2, SolutionV2


def _deadline_remaining(started: float, time_limit_s: float) -> float:
    return max(0.0, float(time_limit_s) - (time.monotonic() - started))


def _reassign_vehicles(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    deadline: float | None = None,
) -> SolutionV2:
    """Try cheaper vehicle types per route on heterogeneous fleets."""
    if not spec.capabilities.heterogeneous_fleet:
        return solution
    current = clone_solution(solution)
    current_report = evaluate(spec, current)
    for r_idx in range(len(current.routes)):
        if deadline is not None and time.monotonic() > deadline:
            break
        best = current
        best_report = current_report
        for type_id in candidate_vehicle_ids(spec):
            if deadline is not None and time.monotonic() > deadline:
                break
            trial = clone_solution(current)
            if r_idx < len(trial.vehicle_assignments):
                trial.vehicle_assignments[r_idx] = type_id
            else:
                trial.vehicle_assignments.append(type_id)
            trial.routes[r_idx] = [
                RouteStopV2(
                    node_id=stop.node_id,
                    vehicle_type_id=type_id,
                    event=stop.event,
                    charge_amount=stop.charge_amount,
                    charge_technology=stop.charge_technology,
                    target_soc=stop.target_soc,
                )
                for stop in trial.routes[r_idx]
            ]
            report = evaluate(spec, trial)
            if is_better(report, best_report):
                best = trial
                best_report = report
        current = best
        current_report = best_report
    return current


def repair_feasibility(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    policy: object | None = None,
    deadline: float | None = None,
) -> SolutionV2:
    """Unified repair: energy → charges → partial charge → route splits → local search."""
    current = clone_solution(solution)
    if deadline is not None and time.monotonic() > deadline:
        return current
    current = repair_energy(spec, current, policy=policy, deadline=deadline)
    current = complete_solution_charges(spec, current)
    current = optimize_solution_partial_charges(spec, current)
    report = evaluate(spec, current)
    if report.feasible:
        return current
    if deadline is not None and time.monotonic() > deadline:
        return current
    current = split_infeasible_routes(spec, current, policy=policy)
    current = optimize_solution_partial_charges(spec, current)
    if deadline is not None and time.monotonic() > deadline:
        return current
    current = relocate_improve(spec, current, max_passes=2, deadline=deadline)
    current = repair_energy(spec, current, policy=policy, deadline=deadline)
    current = complete_solution_charges(spec, current)
    current = optimize_solution_partial_charges(spec, current)
    return current


def _maybe_merge(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    *,
    deadline: float | None,
    max_passes: int = 2,
) -> SolutionV2:
    """Apply route merge only when the lexicographic objective improves."""
    if deadline is not None and time.monotonic() > deadline:
        return solution
    before = evaluate(spec, solution)
    merged = merge_routes_improve(spec, solution, max_passes=max_passes, deadline=deadline)
    after = evaluate(spec, merged)
    return merged if is_better(after, before) else solution


@dataclass
class ClassicalSolver:
    """Transparent constructive + energy-repair + ALNS baseline."""

    seed: int = 0
    time_limit_s: float = 5.0
    alns_iterations: int = 60
    use_alns: bool = True
    policy: object | None = None
    hard_timeout: bool = True
    debug_sleep_s: float = 0.0

    def solve(self, spec: ProblemSpecV2) -> SolutionV2:
        if not self.hard_timeout:
            return self._solve_body(spec, box=None)
        return _solve_in_process(self, spec)

    def _publish(
        self,
        box: dict[str, Any] | None,
        spec: ProblemSpecV2,
        solution: SolutionV2,
    ) -> None:
        if box is None:
            return
        report = evaluate(spec, solution)
        prev_report = box.get("report")
        if prev_report is None or is_better(report, prev_report):
            snapshot = clone_solution(solution)
            box["incumbent"] = snapshot
            box["report"] = report
            sink = box.get("sink")
            if sink is not None:
                try:
                    sink.put(snapshot, timeout=0.2)
                except Exception:  # noqa: BLE001 — a full queue must not stall the solver
                    pass

    def _solve_body(
        self,
        spec: ProblemSpecV2,
        box: dict[str, Any] | None,
    ) -> SolutionV2:
        started = time.monotonic()
        deadline = started + float(self.time_limit_s)
        rng = random.Random(int(self.seed))
        solution = construct_greedy(spec, rng, policy=self.policy)
        self._publish(box, spec, solution)
        solution = repair_feasibility(spec, solution, policy=self.policy, deadline=deadline)
        self._publish(box, spec, solution)
        if time.monotonic() < deadline:
            solution = two_opt_improve(spec, solution, deadline=deadline)
            self._publish(box, spec, solution)
        remaining = _deadline_remaining(started, self.time_limit_s)
        if self.use_alns and remaining > 0.2:
            solution = alns_improve(
                spec,
                solution,
                rng,
                time_limit_s=remaining,
                iterations=self.alns_iterations,
                policy=self.policy,
                deadline=deadline,
            )
            self._publish(box, spec, solution)
        if time.monotonic() < deadline:
            solution = _maybe_merge(spec, solution, deadline=deadline, max_passes=3)
            self._publish(box, spec, solution)
            # Always refresh charge annotations; keep only if not worse.
            polished = remove_redundant_stations(spec, solution)
            polished = complete_solution_charges(spec, polished)
            polished = optimize_solution_partial_charges(spec, polished)
            polished_report = evaluate(spec, polished)
            current_report = evaluate(spec, solution)
            if is_better(polished_report, current_report) or (
                polished_report.feasible == current_report.feasible
                and polished_report.objective_key == current_report.objective_key
            ):
                solution = polished
            elif not current_report.feasible and polished_report.feasible:
                solution = polished
            # Feasibility repair only if currently infeasible.
            if not evaluate(spec, solution).feasible:
                solution = repair_feasibility(spec, solution, policy=self.policy, deadline=deadline)
            else:
                # Feasible incumbents still need Bezzi charge completion after structural edits.
                solution = complete_solution_charges(spec, solution)
                solution = optimize_solution_partial_charges(spec, solution)
            solution = _reassign_vehicles(spec, solution, deadline=deadline)
            if time.monotonic() < deadline:
                solution = _maybe_merge(spec, solution, deadline=deadline, max_passes=2)
                solution = complete_solution_charges(spec, solution)
            self._publish(box, spec, solution)
        report = evaluate(spec, solution)
        elapsed = time.monotonic() - started
        solution.metadata.update(
            {
                "solver": "classical_backbone",
                "seed": int(self.seed),
                "feasible": bool(report.feasible),
                "objective": report.objective,
                "objective_key": list(report.objective_key),
                "vehicles": report.vehicles,
                "distance": report.total_distance,
                "runtime_s": elapsed,
                "time_limit_s": float(self.time_limit_s),
                "deadline_exceeded": elapsed > float(self.time_limit_s) + 0.05,
                "first_fault": report.first_fault.as_dict() if report.first_fault else None,
            }
        )
        self._publish(box, spec, solution)
        return solution


class _FileSink:
    """Parent-readable incumbent slot. Writes are replaced atomically."""

    def __init__(self, path: str) -> None:
        self.path = path

    def put(self, solution: SolutionV2, timeout: float = 0.2) -> None:
        del timeout
        _write_incumbent(self.path, solution)


def _write_incumbent(path: str, solution: SolutionV2) -> None:
    target = Path(path)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(pickle.dumps(solution, protocol=pickle.HIGHEST_PROTOCOL))
    tmp.replace(target)


def _read_incumbent(path: str) -> SolutionV2 | None:
    target = Path(path)
    if not target.exists():
        return None
    try:
        loaded = pickle.loads(target.read_bytes())  # noqa: S301 — local solver snapshot
    except (OSError, pickle.UnpicklingError, EOFError):
        return None
    return loaded if isinstance(loaded, SolutionV2) else None


def _solver_process_main(spec: ProblemSpecV2, config: dict[str, Any], incumbent_path: str) -> None:
    """Child process. The parent joins with a timeout and may terminate this process."""
    policy = None
    sources = config.get("sources") or {}
    if sources:
        from evrptw_autolab.components.loader import load_bundle

        policy, _errors = load_bundle(sources, config.get("owners"))
    solver = ClassicalSolver(
        seed=int(config["seed"]),
        time_limit_s=float(config["time_limit_s"]),
        alns_iterations=int(config["alns_iterations"]),
        use_alns=bool(config["use_alns"]),
        policy=policy,
        hard_timeout=False,
    )
    sink = _FileSink(incumbent_path)
    if float(config.get("debug_sleep_s") or 0) > 0:
        rng = random.Random(int(config["seed"]))
        sink.put(construct_greedy(spec, rng, policy=policy))
        time.sleep(float(config["debug_sleep_s"]))
        return
    solver._solve_body(spec, {"sink": sink})


def _mark_timeout(solution: SolutionV2, *, seed: int, limit: float, wall: float) -> SolutionV2:
    solution.metadata.update(
        {
            "solver": "classical_backbone",
            "seed": int(seed),
            "time_limit_s": float(limit),
            "runtime_s": wall,
            "deadline_exceeded": True,
            "hard_timeout": True,
            "terminated": True,
        }
    )
    return solution


def _solve_in_process(solver: ClassicalSolver, spec: ProblemSpecV2) -> SolutionV2:
    """Run the solver in a child process and terminate it when the budget expires."""
    ctx = mp.get_context("spawn")
    config = {
        "seed": int(solver.seed),
        "time_limit_s": float(solver.time_limit_s),
        "alns_iterations": int(solver.alns_iterations),
        "use_alns": bool(solver.use_alns),
        "debug_sleep_s": float(solver.debug_sleep_s),
        "sources": dict(getattr(solver.policy, "sources", {}) or {}),
        "owners": dict(getattr(solver.policy, "owners", {}) or {}),
    }
    fd, incumbent_path = tempfile.mkstemp(prefix="voltforge-incumbent-", suffix=".pkl")
    os.close(fd)
    proc = ctx.Process(
        target=_solver_process_main,
        args=(spec, config, incumbent_path),
        daemon=True,
    )
    started = time.monotonic()
    limit = float(solver.time_limit_s)
    proc.start()
    proc.join(limit)
    timed_out = proc.is_alive()
    if timed_out:
        proc.terminate()
        proc.join(2)
        if proc.is_alive():
            proc.kill()
            proc.join(1)
    wall = time.monotonic() - started
    latest = _read_incumbent(incumbent_path)
    Path(incumbent_path).unlink(missing_ok=True)
    Path(incumbent_path + ".tmp").unlink(missing_ok=True)
    if latest is None:
        vid = spec.vehicle_types[0].type_id if spec.vehicle_types else None
        latest = SolutionV2(routes=[empty_route(spec, vid)], vehicle_assignments=[vid or ""])
        return _mark_timeout(latest, seed=solver.seed, limit=limit, wall=wall)
    if timed_out:
        return _mark_timeout(latest, seed=solver.seed, limit=limit, wall=wall)
    latest.metadata["runtime_s"] = wall
    latest.metadata["hard_timeout"] = False
    latest.metadata["terminated"] = False
    return latest


def solve_classical(
    spec: ProblemSpecV2,
    *,
    seed: int = 0,
    time_limit_s: float = 5.0,
    alns_iterations: int = 60,
    use_alns: bool = True,
    policy: object | None = None,
    hard_timeout: bool = True,
) -> SolutionV2:
    return ClassicalSolver(
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        use_alns=use_alns,
        policy=policy,
        hard_timeout=hard_timeout,
    ).solve(spec)


def solve_report(
    spec: ProblemSpecV2,
    *,
    seed: int = 0,
    time_limit_s: float = 5.0,
) -> dict[str, Any]:
    sol = solve_classical(spec, seed=seed, time_limit_s=time_limit_s)
    report = evaluate(spec, sol)
    return {
        "feasible": report.feasible,
        "objective": report.objective,
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "violations": [v.as_dict() for v in report.violations[:20]],
        "metadata": sol.metadata,
        "routes": [[s.node_id for s in route] for route in sol.routes],
    }
