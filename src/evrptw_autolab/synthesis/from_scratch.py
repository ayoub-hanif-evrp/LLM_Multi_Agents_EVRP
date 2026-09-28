"""From-scratch solver synthesis: five-agent team or one coding agent."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from evrptw_autolab.agents import build_team
from evrptw_autolab.agents.base import Agent
from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.problem.micro import (
    micro_g1_one_customer,
    micro_g2_needs_charge,
    micro_g3_two_customers,
)
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.sandbox.static_scan import scan_source
from evrptw_autolab.slm_evo.evaluate import all_c5_instances, code_hash, panel_instances
from evrptw_autolab.synthesis.contract import PROBLEM_BRIEF

STAGES = ("executable", "routing", "charging", "multi_customer", "schneider_c5")


class _SingleSchema(BaseModel):
    note: str = ""


class SingleAgent(Agent[_SingleSchema]):
    role = "single"
    prompt_name = "single_agent_coder.md"
    schema = _SingleSchema


def _usage_totals(usage: UsageLog) -> tuple[int, int, int]:
    rows = usage.all()
    prompt = sum(int(row.get("prompt_tokens") or 0) for row in rows)
    completion = sum(int(row.get("completion_tokens") or 0) for row in rows)
    return len(rows), prompt, completion


def _brief(report: Any) -> dict[str, Any]:
    fault = dict(report.first_fault or {})
    return {
        "feasible": bool(report.feasible),
        "crashed": bool(report.crashed),
        "parse_ok": bool(report.parse_ok),
        "timed_out": bool(report.timed_out),
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "error": str(report.error or "")[:500],
        "first_fault": fault,
    }


def _failure_text(report: Any) -> str:
    if report.crashed or not report.parse_ok:
        return str(report.error or "crash")[:300]
    fault = report.first_fault or {}
    family = str(fault.get("family") or "infeasible")
    detail = str(fault.get("detail") or "")
    return f"{family}: {detail}"[:300]


def _eval_stage(
    stage: str,
    solver_dir: Path,
    *,
    limits: RunLimits,
    panel: list[EVRPTWInstance],
) -> tuple[bool, str, dict[str, Any]]:
    probes = {
        "executable": micro_g1_one_customer(),
        "routing": micro_g1_one_customer(),
        "charging": micro_g2_needs_charge(),
        "multi_customer": micro_g3_two_customers(),
    }
    if stage == "schneider_c5":
        details = []
        for instance in panel:
            report = run_solver(solver_dir, instance, seed=0, limits=limits)
            details.append({"instance": instance.instance_id, **_brief(report)})
            if not report.feasible:
                return False, _failure_text(report), {"instances": details}
        return True, "", {"instances": details}
    instance = probes[stage]
    report = run_solver(solver_dir, instance, seed=0, limits=limits)
    info = _brief(report)
    if stage == "executable":
        ok = bool(report.parse_ok and not report.crashed and not report.timed_out)
        return ok, "" if ok else _failure_text(report), info
    ok = bool(report.feasible and not report.crashed and not report.timed_out)
    return ok, "" if ok else _failure_text(report), info


def _write_sources(solver_dir: Path, source: str, routing: str = "", charging: str = "") -> None:
    solver_dir.mkdir(parents=True, exist_ok=True)
    (solver_dir / "solver.py").write_text(source, encoding="utf-8")
    if routing.strip():
        (solver_dir / "routing.py").write_text(routing, encoding="utf-8")
    if charging.strip():
        (solver_dir / "charging.py").write_text(charging, encoding="utf-8")


def run_from_scratch(
    *,
    mode: str,
    model: str,
    backend: Any,
    workspace: Path,
    temperatures: dict[str, float] | None = None,
    max_llm_calls: int = 80,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Synthesize solver.py from an empty directory. mode is 'five_agent' or 'single_agent'."""
    if mode not in {"five_agent", "single_agent"}:
        raise ValueError("mode must be five_agent or single_agent")
    started = time.monotonic()
    workspace.mkdir(parents=True, exist_ok=True)
    solver_dir = workspace / "solver"
    usage = UsageLog(workspace / "llm_calls.jsonl")
    log_path = workspace / "rounds.jsonl"
    limits = RunLimits(wall_clock_s=20.0)
    panel = panel_instances(data_root)
    if len(panel) != 4:
        raise RuntimeError(f"expected 4 Schneider C5 panel instances, found {len(panel)}")

    if mode == "five_agent":
        team: dict[str, Any] = build_team(
            backend, model=model, temperatures=temperatures, usage_log=usage
        )
    else:
        temp = (temperatures or {}).get("single", 0.25)
        team = {
            "single": SingleAgent(backend, model=model, temperature=temp, usage_log=usage)
        }

    committed = ""
    rejected = ""
    stage_index = 0
    passed = {name: False for name in STAGES}
    failure_reason = ""
    rounds = 0

    def calls() -> int:
        return _usage_totals(usage)[0]

    while stage_index < len(STAGES) and calls() < max_llm_calls:
        stage = STAGES[stage_index]
        payload = {
            "problem": PROBLEM_BRIEF,
            "stage": stage,
            "instruction": (
                f"Current stage: {stage}. "
                "Preserve feasibility already achieved. "
                "Return a complete solver. The depot id may appear only at the start and end of each route."
            ),
            "current_solver_py": committed,
            "rejected_solver_py": rejected,
            "failure_reason": failure_reason,
        }
        routing_src = ""
        charging_src = ""
        try:
            if mode == "five_agent":
                if calls() >= max_llm_calls:
                    break
                try:
                    plan = team["architect"].run(payload)
                    payload["architect"] = plan.model_dump()
                except (TypeError, ValueError, KeyError) as error:
                    payload["architect_error"] = str(error)[:300]
                if calls() >= max_llm_calls:
                    break
                routing_src = team["routing"].write_python(
                    payload, filename="routing.py", marker="def "
                )
                if calls() >= max_llm_calls:
                    break
                charging_src = team["charging"].write_python(
                    payload, filename="charging.py", marker="def "
                )
                payload["routing_py"] = routing_src
                payload["charging_py"] = charging_src
                if calls() >= max_llm_calls:
                    break
                source = team["search"].write_python(
                    payload, filename="solver.py", marker="def solve"
                )
            else:
                source = team["single"].write_python(
                    payload, filename="solver.py", marker="def solve"
                )
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            failure_reason = f"model_error: {error}"[:300]
            break

        rounds += 1
        scan_errors = scan_source(source or "")
        if scan_errors or "def solve" not in (source or ""):
            ok = False
            reason = scan_errors[0] if scan_errors else "model did not return def solve"
            info: dict[str, Any] = {}
        else:
            _write_sources(solver_dir, source, routing_src, charging_src)
            ok, reason, info = _eval_stage(stage, solver_dir, limits=limits, panel=panel)
        if ok:
            committed = source
            rejected = ""
            passed[stage] = True
            stage_index += 1
            failure_reason = ""
        else:
            failure_reason = reason or "stage failed"
            rejected = source or ""
            if not committed:
                committed = source or committed
        if mode == "five_agent" and calls() < max_llm_calls:
            try:
                team["critic"].run(
                    {
                        "stage": stage,
                        "passed": ok,
                        "failure_reason": failure_reason,
                        "evaluation": info,
                    }
                )
            except (TypeError, ValueError, KeyError):
                pass
        row = {
            "round": rounds,
            "stage": stage,
            "passed": ok,
            "failure_reason": failure_reason,
            "calls": calls(),
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    if committed.strip():
        _write_sources(solver_dir, committed)
    c5 = all_c5_instances(data_root)
    feasible = 0
    vehicles = 0
    distance = 0.0
    if committed.strip() and (solver_dir / "solver.py").exists():
        for instance in c5:
            report = run_solver(solver_dir, instance, seed=0, limits=limits)
            if report.feasible and not report.crashed:
                feasible += 1
                vehicles += int(report.vehicles or 0)
                distance += float(report.total_distance or 0.0)
    n_calls, prompt_tokens, completion_tokens = _usage_totals(usage)
    fully = feasible == len(c5) and len(c5) > 0
    if not passed["schneider_c5"] and not failure_reason:
        failure_reason = "budget_exhausted"
    return {
        "experiment": "five_agent_synthesis" if mode == "five_agent" else "single_agent_synthesis",
        "model": model,
        "executable": passed["executable"],
        "routing": passed["routing"],
        "charging": passed["charging"],
        "multi_customer": passed["multi_customer"],
        "schneider_c5": passed["schneider_c5"],
        "llm_calls": n_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": prompt_tokens + completion_tokens,
        "failure_reason": "" if passed["schneider_c5"] else failure_reason,
        "feasible": feasible,
        "c5_total": len(c5),
        "fully_feasible": fully,
        "vehicles": vehicles if fully else None,
        "distance": round(distance, 4) if fully else None,
        "solver_hash": code_hash(committed)[:16] if committed.strip() else "",
        "wall_s": round(time.monotonic() - started, 1),
        "rounds": rounds,
        "solver_path": str(solver_dir / "solver.py"),
    }
