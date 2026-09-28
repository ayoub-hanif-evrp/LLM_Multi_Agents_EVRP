"""Isolated execution of a generated solver. The parent process does evaluation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from evrptw_autolab.problem.evaluator import evaluate_solution
from evrptw_autolab.problem.types import CandidateSolution, EvaluationReport, EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.static_scan import scan_directory

CONTRACT_HINT = (
    "CONTRACT: use lab EVRPTWInstance as-is. "
    "distance/energy_required need Node objects via instance.node_map[id] — never raw str ids. "
    "VehicleSpec: capacity, battery_capacity, consumption_rate, velocity, inverse_refuel_rate "
    "(NO battery_efficiency). energy_required(node_a, node_b, vehicle). "
    "routes=list[list[str]] start/end depot_id."
)

_DRIVER = """
import inspect
import json
import sys
from pathlib import Path

sys.path.insert(0, {package_src!r})
sys.path.insert(0, {solver_dir!r})
from evrptw_autolab.problem.schneider import load_instance
from solver import solve

instance = load_instance(Path({instance_path!r}))
seed = {seed}
limit = {limit}


def _call_solve():
    params = inspect.signature(solve).parameters
    names = [n for n in params if n not in {{"args", "kwargs"}} and params[n].kind != inspect.Parameter.VAR_KEYWORD]
    kwargs = {{}}
    if "seed" in params:
        kwargs["seed"] = seed
    if "time_limit_s" in params:
        kwargs["time_limit_s"] = limit
    if "instance" in params:
        return solve(instance, **kwargs)
    if names and names[0] in {{"customers", "customer_ids", "nodes"}}:
        # Last-resort: wrong first arg name but still wants the instance object.
        return solve(instance, **kwargs)
    try:
        return solve(instance, seed=seed, time_limit_s=limit)
    except TypeError:
        try:
            return solve(instance, seed, limit)
        except TypeError:
            return solve(instance, time_limit_s=limit)


def _normalize(result):
    if result is None:
        raise ValueError("solve returned None")
    if isinstance(result, str):
        raise ValueError("solve returned a string; need routes list")
    if isinstance(result, list):
        return list(result), {{}}
    if isinstance(result, tuple) and result and isinstance(result[0], list):
        meta = result[1] if len(result) > 1 and isinstance(result[1], dict) else {{}}
        return list(result[0]), dict(meta)
    if hasattr(result, "routes"):
        routes = list(result.routes)
        meta = dict(getattr(result, "metadata", {{}}) or {{}})
        return routes, meta
    if isinstance(result, dict):
        if "routes" not in result:
            raise KeyError("solve dict missing routes")
        return list(result["routes"]), dict(result.get("metadata") or {{}})
    raise TypeError(f"unsupported solve return type: {{type(result)!r}}")


try:
    result = _call_solve()
    routes, meta = _normalize(result)
except Exception:
    import traceback
    # Traceback first so coding repair sees the real exception, not only the API banner.
    traceback.print_exc()
    print({contract_hint!r}, file=sys.stderr)
    raise SystemExit(1)
print(json.dumps({{"routes": routes, "metadata": meta}}))
"""


def run_solver(
    solver_dir: Path,
    instance: EVRPTWInstance,
    *,
    seed: int,
    limits: RunLimits | None = None,
    package_src: Path | None = None,
) -> EvaluationReport:
    limits = limits or RunLimits()
    scan_errors = scan_directory(solver_dir)
    if scan_errors:
        detail = "; ".join(scan_errors[:8])
        return EvaluationReport(
            parse_ok=False,
            crashed=True,
            error=detail,
            first_fault={"family": "CRASH", "node_id": "", "route_index": -1, "detail": detail},
        )
    source_path = instance.metadata.get("source_path")
    root = Path(__file__).resolve().parents[3]
    src = str(package_src or (root / "src"))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="evrptw_autolab_") as tmp:
        work = Path(tmp)
        if source_path:
            instance_copy = work / Path(source_path).name
            instance_copy.write_bytes(Path(source_path).read_bytes())
        else:
            from evrptw_autolab.problem.serialize import write_instance_json

            instance_copy = work / f"{instance.instance_id}.json"
            write_instance_json(instance, instance_copy)
        driver = work / "driver.py"
        driver.write_text(
            _DRIVER.format(
                package_src=src,
                solver_dir=str(solver_dir.resolve()),
                instance_path=str(instance_copy),
                seed=int(seed),
                limit=float(limits.wall_clock_s),
                contract_hint=CONTRACT_HINT,
            ),
            encoding="utf-8",
        )
        env = {**os.environ, "PYTHONPATH": src, "PYTHONUNBUFFERED": "1"}
        env.pop("OLLAMA_HOST", None)
        try:
            completed = subprocess.run(
                [sys.executable, str(driver)],
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=limits.wall_clock_s + 2.0,
                env=env,
                check=False,
            )
        except subprocess.TimeoutExpired:
            report = EvaluationReport(
                timed_out=True,
                crashed=True,
                error="timeout",
                first_fault={"family": "CRASH", "node_id": "", "route_index": -1, "detail": "timeout"},
            )
            report.runtime_s = time.monotonic() - started
            return report
        runtime = time.monotonic() - started
        if completed.returncode != 0:
            err = (completed.stderr or completed.stdout or "solver_crash")[-2000:]
            return EvaluationReport(
                crashed=True,
                error=err,
                runtime_s=runtime,
                first_fault={"family": "CRASH", "node_id": "", "route_index": -1, "detail": err[-400:]},
            )
        try:
            payload: dict[str, Any] = json.loads(completed.stdout.strip().splitlines()[-1])
            solution = CandidateSolution(list(payload["routes"]), dict(payload.get("metadata") or {}))
        except (json.JSONDecodeError, KeyError, IndexError) as error:
            return EvaluationReport(
                parse_ok=False,
                crashed=True,
                error=str(error),
                runtime_s=runtime,
                first_fault={"family": "PARSE", "node_id": "", "route_index": -1, "detail": str(error)[:400]},
            )
        report = evaluate_solution(instance, solution)
        report.runtime_s = runtime
        return report
