"""From-scratch solver synthesis: five-agent team or one coding agent."""
from __future__ import annotations

import ast
import json
import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from evrptw_autolab.agents import build_team
from evrptw_autolab.agents.base import Agent
from evrptw_autolab.evolution.evaluate import (
    all_c5_instances,
    code_hash,
    find_hardcoded_node_ids,
    known_ids_for_panel,
    panel_instances,
)
from evrptw_autolab.llm.usage import BudgetExhausted, UsageLog
from evrptw_autolab.problem.micro import (
    micro_g1_one_customer,
    micro_g2_needs_charge,
    micro_g3_two_customers,
)
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.sandbox.static_scan import scan_source
from evrptw_autolab.synthesis.contract import PROBLEM_BRIEF

STAGES = ("executable", "routing", "charging", "multi_customer", "schneider_c5")
STAGNATION_NOTE = (
    "This exact program already failed with this exact error; produce a materially different repair."
)
INTEGRATION = {"SYNTAX", "RUNTIME", "TIMEOUT", "GENERALITY"}
FAULTS = {"DEPOT", "VISIT", "CAPACITY", "WINDOW", "BATTERY", "CHARGE_POLICY"}


class _SingleSchema(BaseModel):
    note: str = ""


class SingleAgent(Agent[_SingleSchema]):
    role = "single"
    prompt_name = "single_agent_coder.md"
    schema = _SingleSchema


def usage_totals(usage: UsageLog) -> tuple[int, int, int]:
    rows = usage.all()
    prompt = sum(int(row.get("prompt_tokens") or 0) for row in rows)
    completion = sum(int(row.get("completion_tokens") or 0) for row in rows)
    return len(rows), prompt, completion


def format_runtime_error(error: str, source: str = "") -> dict[str, Any]:
    """Keep the exception at the bottom of a traceback, not the opening banner."""
    lines = [line.rstrip() for line in (error or "").splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith("CONTRACT:")]
    tail = lines[-8:]
    exception_type = ""
    exception_message = ""
    for line in reversed(tail):
        stripped = line.strip()
        if stripped.startswith("Traceback") or stripped.startswith("File ") or stripped.startswith("raise "):
            continue
        if ":" in stripped and not stripped.startswith("File"):
            exception_type, exception_message = stripped.split(":", 1)
            exception_type = exception_type.strip().split()[-1]
            exception_message = exception_message.strip()
            break
    context = ""
    numbers = [int(match) for match in re.findall(r"line (\d+)", "\n".join(tail))]
    if numbers and source:
        lineno = numbers[-1]
        rows = source.splitlines()
        start = max(0, lineno - 3)
        end = min(len(rows), lineno + 2)
        context = "\n".join(f"{index + 1}: {rows[index]}" for index in range(start, end))
    return {
        "exception_type": exception_type,
        "exception_message": exception_message,
        "traceback_tail": "\n".join(tail),
        "source_context": context,
    }


def fault_packet(report: Any) -> dict[str, Any]:
    fault = dict(report.first_fault or {})
    return {
        "family": str(fault.get("family") or ""),
        "node_id": fault.get("node_id", ""),
        "route_index": fault.get("route_index", -1),
        "detail": str(fault.get("detail") or ""),
    }


def classify_category(
    *,
    g4_passed: bool,
    category: str,
    budget: bool,
) -> str:
    if g4_passed:
        return "SUCCESS"
    if category in FAULTS or category in {"SYNTAX", "RUNTIME", "TIMEOUT", "GENERALITY"}:
        return category
    if budget:
        return "BUDGET"
    return "RUNTIME"


def precheck_source(source: str, known_ids: set[str]) -> dict[str, Any] | None:
    """Reject a trial before execution. None means the source may be executed."""
    text = source or ""
    if "def solve" not in text:
        return {
            "category": "SYNTAX",
            "ok": False,
            "failure_reason": "model did not return def solve",
            "execution": {"exception_type": "SyntaxError", "exception_message": "missing def solve", "traceback_tail": "", "source_context": ""},
            "first_fault": {},
        }
    try:
        ast.parse(text)
    except SyntaxError as error:
        return {
            "category": "SYNTAX",
            "ok": False,
            "failure_reason": f"SyntaxError: {error.msg}",
            "execution": {
                "exception_type": "SyntaxError",
                "exception_message": str(error.msg),
                "traceback_tail": str(error),
                "source_context": "",
            },
            "first_fault": {},
        }
    hardcoded = find_hardcoded_node_ids(text, known_ids=known_ids)
    if hardcoded:
        detail = ",".join(hardcoded)
        return {
            "category": "GENERALITY",
            "ok": False,
            "failure_reason": f"GENERALITY: {detail}",
            "execution": {},
            "first_fault": {"family": "GENERALITY", "node_id": "", "route_index": -1, "detail": detail},
        }
    scan_errors = scan_source(text)
    if scan_errors:
        detail = scan_errors[0]
        if "heldout" in detail or "hardcode" in detail:
            category = "GENERALITY"
        elif detail.startswith("syntax_error"):
            category = "SYNTAX"
        else:
            category = "RUNTIME"
        return {
            "category": category,
            "ok": False,
            "failure_reason": detail,
            "execution": {"exception_type": category, "exception_message": detail, "traceback_tail": detail, "source_context": ""},
            "first_fault": {},
        }
    return None


def _probe(stage: str) -> EVRPTWInstance | None:
    return {
        "executable": micro_g1_one_customer(),
        "routing": micro_g1_one_customer(),
        "charging": micro_g2_needs_charge(),
        "multi_customer": micro_g3_two_customers(),
    }.get(stage)


def _stage_ok(stage: str, report: Any) -> bool:
    if report.timed_out:
        return False
    if stage == "executable":
        return bool(report.parse_ok and not report.crashed)
    return bool(report.feasible and report.parse_ok and not report.crashed)


def _report_failure(stage: str, report: Any, source: str) -> dict[str, Any]:
    packet = fault_packet(report)
    if report.timed_out:
        category = "TIMEOUT"
        reason = "timeout"
        execution = format_runtime_error(report.error or "timeout", source)
    elif report.crashed or not report.parse_ok:
        category = "RUNTIME"
        execution = format_runtime_error(str(report.error or ""), source)
        reason = f"{execution.get('exception_type') or 'RuntimeError'}: {execution.get('exception_message') or ''}".strip()
    else:
        family = str(packet.get("family") or "").upper()
        category = family if family in FAULTS else "RUNTIME"
        execution = {}
        reason = f"{category}: {packet.get('detail') or ''}".strip()
    return {
        "ok": False,
        "failed_stage": stage,
        "category": category,
        "failure_reason": reason[:500],
        "execution": execution,
        "first_fault": packet,
    }


def evaluate_through(
    solver_dir: Path,
    stage: str,
    *,
    limits: RunLimits,
    panel: list[EVRPTWInstance],
) -> dict[str, Any]:
    """A later gate counts only when every earlier gate still passes."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage}")
    source = (solver_dir / "solver.py").read_text(encoding="utf-8")
    last: dict[str, Any] = {"ok": True, "failed_stage": "", "category": "", "failure_reason": "", "execution": {}, "first_fault": {}}
    for name in STAGES[: STAGES.index(stage) + 1]:
        if name == "schneider_c5":
            passed = 0
            for instance in panel:
                report = run_solver(solver_dir, instance, seed=0, limits=limits)
                if not _stage_ok(name, report):
                    failed = _report_failure(name, report, source)
                    failed["g4_passed_here"] = passed
                    return failed
                passed += 1
            last = {"ok": True, "failed_stage": "", "category": "", "failure_reason": "", "execution": {}, "first_fault": {}, "g4_passed_here": passed}
            continue
        probe = _probe(name)
        if probe is None:
            raise RuntimeError(f"missing probe for {name}")
        report = run_solver(solver_dir, probe, seed=0, limits=limits)
        if not _stage_ok(name, report):
            return _report_failure(name, report, source)
        last = {"ok": True, "failed_stage": "", "category": "", "failure_reason": "", "execution": {}, "first_fault": fault_packet(report)}
    return last


def roles_for(stage: str, category: str) -> list[str]:
    if category in {"BATTERY", "WINDOW", "CHARGE_POLICY"}:
        return ["architect", "charging", "search"]
    if category in {"VISIT", "DEPOT", "CAPACITY"}:
        return ["architect", "routing", "search"]
    if stage == "executable":
        return ["architect", "search"]
    if stage == "routing":
        return ["architect", "routing", "search"]
    if stage == "charging":
        return ["architect", "charging", "search"]
    return ["architect", "routing", "charging", "search"]


def _write_solver(directory: Path, source: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for extra in directory.glob("*.py"):
        if extra.name != "solver.py":
            extra.unlink()
    (directory / "solver.py").write_text(source, encoding="utf-8")


def _deepest(passed: dict[str, bool]) -> str:
    deepest = ""
    for name in STAGES:
        if passed[name]:
            deepest = name
        else:
            break
    return deepest


def run_from_scratch(
    *,
    mode: str,
    model: str,
    backend: Any,
    workspace: Path,
    temperatures: dict[str, float] | None = None,
    max_llm_calls: int = 80,
    token_ceiling: int | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Synthesize one solver.py. mode is 'five_agent' or 'single_agent'."""
    if mode not in {"five_agent", "single_agent"}:
        raise ValueError("mode must be five_agent or single_agent")
    started = time.monotonic()
    workspace.mkdir(parents=True, exist_ok=True)
    committed_dir = workspace / "committed"
    trial_dir = workspace / "trial"
    rejected_dir = workspace / "rejected"
    usage = UsageLog(workspace / "llm_calls.jsonl")
    if usage.path.exists():
        usage.path.unlink()
    log_path = workspace / "rounds.jsonl"
    if log_path.exists():
        log_path.unlink()
    limits = RunLimits(wall_clock_s=20.0)
    panel = panel_instances(data_root)
    if len(panel) != 4:
        raise RuntimeError(f"expected 4 Schneider C5 panel instances, found {len(panel)}")
    known_ids = known_ids_for_panel(data_root)
    if hasattr(backend, "diversify_calls"):
        backend.diversify_calls = True

    if mode == "five_agent":
        team: dict[str, Any] = build_team(
            backend, model=model, temperatures=temperatures, usage_log=usage
        )
    else:
        temp = (temperatures or {}).get("single", 0.25)
        team = {"single": SingleAgent(backend, model=model, temperature=temp, usage_log=usage)}
    for agent in team.values():
        agent.max_calls = max_llm_calls
        agent.token_ceiling = token_ceiling

    committed = ""
    rejected = ""
    stage_index = 0
    passed = {name: False for name in STAGES}
    failure: dict[str, Any] = {}
    critic_note: dict[str, Any] = {}
    architect_plan: dict[str, Any] | None = None
    planned_stage = ""
    repair_mode = False
    repairs_used = 0
    rounds = 0
    budget_hit = False
    activated: list[str] = []
    seen_trials: dict[tuple[str, str, str], int] = {}
    stagnation_note = ""
    stagnation_stop = False

    def calls() -> int:
        return usage_totals(usage)[0]

    while stage_index < len(STAGES):
        stage = STAGES[stage_index]
        category = str(failure.get("category") or "")
        if repair_mode and repairs_used < 2:
            active = ["search"]
            repairs_used += 1
            repair_round = True
        else:
            repair_mode = False
            repairs_used = 0
            active = roles_for(stage, category)
            repair_round = False
        payload: dict[str, Any] = {
            "problem": PROBLEM_BRIEF,
            "stage": stage,
            "gates_required": list(STAGES[: stage_index + 1]),
            "instruction": (
                f"Current stage: {stage}. "
                "Preserve every earlier gate. "
                "Return one complete self-contained solver.py. "
                "The depot id may appear only at the start and end of each route."
                + (f" {stagnation_note}" if stagnation_note else "")
            ),
            "committed_solver_py": committed,
            "rejected_solver_py": rejected,
            "failure_reason": failure.get("failure_reason") or "",
            "failure_category": category,
            "execution": failure.get("execution") or {},
            "first_fault": failure.get("first_fault") or {},
            "critic": critic_note,
            "repair": repair_round,
        }
        routing_fragment = ""
        charging_fragment = ""
        try:
            if mode == "five_agent":
                if "architect" in active and planned_stage != stage:
                    architect_plan = team["architect"].run(payload).model_dump()
                    planned_stage = stage
                if architect_plan:
                    payload["architect"] = architect_plan
                if "routing" in active:
                    routing_fragment = team["routing"].write_python(
                        payload, filename="routing fragment", marker="def "
                    )
                    payload["routing_fragment"] = routing_fragment
                if "charging" in active:
                    charging_fragment = team["charging"].write_python(
                        payload, filename="charging fragment", marker="def "
                    )
                    payload["charging_fragment"] = charging_fragment
                source = team["search"].write_python(
                    payload, filename="solver.py", marker="def solve"
                )
                activated = list(active)
            else:
                source = team["single"].write_python(
                    payload, filename="solver.py", marker="def solve"
                )
                activated = ["single"]
        except BudgetExhausted:
            budget_hit = True
            break
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            failure = {
                "category": "RUNTIME",
                "failure_reason": f"model_error: {error}"[:500],
                "execution": {},
                "first_fault": {},
            }
            break

        rounds += 1
        blocked = precheck_source(source or "", known_ids)
        if blocked is not None:
            info = blocked
            ok = False
        else:
            _write_solver(trial_dir, source)
            info = evaluate_through(trial_dir, stage, limits=limits, panel=panel)
            ok = bool(info.get("ok"))
        if ok:
            committed = source
            rejected = ""
            _write_solver(committed_dir, committed)
            for name in STAGES[: stage_index + 1]:
                passed[name] = True
            stage_index += 1
            failure = {}
            repair_mode = False
            repairs_used = 0
            stagnation_note = ""
        else:
            failure = info
            trial_key = (stage, str(info.get("category") or ""), code_hash(source or ""))
            seen_trials[trial_key] = seen_trials.get(trial_key, 0) + 1
            if seen_trials[trial_key] >= 3:
                stagnation_stop = True
                failure["failure_reason"] = (
                    str(failure.get("failure_reason") or "") + " | repeated identical trial"
                )[:500]
            elif seen_trials[trial_key] == 2:
                stagnation_note = STAGNATION_NOTE
            else:
                stagnation_note = ""
            rejected = source or ""
            if rejected.strip():
                _write_solver(rejected_dir, rejected)
            if str(info.get("category") or "") in INTEGRATION:
                if repairs_used < 2:
                    repair_mode = True
                else:
                    repair_mode = False
                    repairs_used = 0
            else:
                repair_mode = False
                repairs_used = 0
        if stagnation_stop:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "round": rounds,
                            "stage": stage,
                            "passed": False,
                            "stagnation": True,
                            "failure_category": failure.get("category") or "",
                            "failure_reason": failure.get("failure_reason") or "",
                        }
                    )
                    + "\n"
                )
            break
        if mode == "five_agent":
            try:
                decision = team["critic"].run(
                    {
                        "stage": stage,
                        "passed": ok,
                        "failure_reason": failure.get("failure_reason") or "",
                        "failure_category": failure.get("category") or "",
                        "execution": failure.get("execution") or {},
                        "first_fault": failure.get("first_fault") or {},
                        "evaluation": {"passed": ok, "stage": stage},
                    }
                )
                critic_note = {
                    "diagnosis": decision.primary_cause,
                    "evidence": list(decision.evidence),
                    "recommended_next_target": decision.next_target,
                    "lesson": decision.lesson,
                }
            except BudgetExhausted:
                budget_hit = True
                break
            except (TypeError, ValueError, KeyError):
                critic_note = critic_note or {
                    "diagnosis": failure.get("failure_reason") or "",
                    "evidence": [],
                    "recommended_next_target": "SEARCH",
                }
        n_calls, prompt_tokens, completion_tokens = usage_totals(usage)
        row = {
            "round": rounds,
            "stage": stage,
            "passed": ok,
            "repair": repair_round,
            "roles": activated,
            "failure_category": failure.get("category") or "",
            "failure_reason": failure.get("failure_reason") or "",
            "critic": critic_note,
            "calls": n_calls,
            "tokens": prompt_tokens + completion_tokens,
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        if budget_hit or calls() >= max_llm_calls:
            if calls() >= max_llm_calls:
                budget_hit = True
            if budget_hit and stage_index >= len(STAGES):
                break
            if calls() >= max_llm_calls:
                break

    g4_passed = bool(passed["schneider_c5"])
    confirmation_feasible = None
    confirmation_total = None
    g4_feasible = 0
    vehicles = None
    distance = None
    fully = False
    if committed.strip():
        _write_solver(committed_dir, committed)
        g4_count = 0
        for instance in panel:
            report = run_solver(committed_dir, instance, seed=0, limits=limits)
            if report.feasible and not report.crashed and not report.timed_out:
                g4_count += 1
        g4_feasible = g4_count
        if g4_passed:
            confirmation = [
                instance
                for instance in all_c5_instances(data_root)
                if instance.instance_id not in {item.instance_id for item in panel}
            ]
            confirmation_total = len(confirmation)
            confirmation_feasible = 0
            held_vehicles = 0
            held_distance = 0.0
            panel_vehicles = 0
            panel_distance = 0.0
            for instance in panel:
                report = run_solver(committed_dir, instance, seed=0, limits=limits)
                if report.feasible and not report.crashed:
                    panel_vehicles += int(report.vehicles or 0)
                    panel_distance += float(report.total_distance or 0.0)
            for instance in confirmation:
                report = run_solver(committed_dir, instance, seed=0, limits=limits)
                if report.feasible and not report.crashed and not report.timed_out:
                    confirmation_feasible += 1
                    held_vehicles += int(report.vehicles or 0)
                    held_distance += float(report.total_distance or 0.0)
            fully = confirmation_feasible == confirmation_total and g4_feasible == len(panel)
            if fully:
                vehicles = panel_vehicles + held_vehicles
                distance = round(panel_distance + held_distance, 4)
    n_calls, prompt_tokens, completion_tokens = usage_totals(usage)
    tokens = prompt_tokens + completion_tokens
    category = classify_category(
        g4_passed=g4_passed,
        category=str(failure.get("category") or ""),
        budget=budget_hit or (not g4_passed and n_calls >= max_llm_calls),
    )
    if token_ceiling is not None and not g4_passed and tokens >= token_ceiling and category not in FAULTS | INTEGRATION:
        category = "BUDGET"
    rows = usage.all()
    digest = next((str(row.get("digest") or "") for row in rows if row.get("digest")), "")
    model_tag = next((str(row.get("model_tag") or "") for row in rows if row.get("model_tag")), model)
    overshoot = 0
    if token_ceiling is not None:
        overshoot = max(0, tokens - int(token_ceiling))
    solver_path = committed_dir / "solver.py"
    return {
        "experiment": "five_agent_synthesis" if mode == "five_agent" else "single_agent_synthesis",
        "model": model,
        "model_tag": model_tag,
        "model_digest": digest,
        "executable": passed["executable"],
        "routing": passed["routing"],
        "charging": passed["charging"],
        "multi_customer": passed["multi_customer"],
        "schneider_c5": passed["schneider_c5"],
        "deepest_gate": _deepest(passed),
        "g4_feasible": g4_feasible,
        "g4_total": len(panel),
        "confirmation_feasible": confirmation_feasible,
        "confirmation_total": confirmation_total,
        "llm_calls": n_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": tokens,
        "token_ceiling": token_ceiling,
        "token_overshoot": overshoot,
        "failure_reason": "" if g4_passed else str(failure.get("failure_reason") or ""),
        "failure_category": category,
        "feasible": (g4_feasible + int(confirmation_feasible or 0)) if g4_passed else g4_feasible,
        "c5_total": (len(panel) + int(confirmation_total or 0)) if g4_passed else len(panel),
        "fully_feasible": fully,
        "vehicles": vehicles,
        "distance": distance,
        "solver_hash": code_hash(committed)[:16] if committed.strip() else "",
        "wall_s": round(time.monotonic() - started, 1),
        "rounds": rounds,
        "solver_path": str(solver_path),
    }
