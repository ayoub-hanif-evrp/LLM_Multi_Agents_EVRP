"""From-scratch solver synthesis: five-agent team or one coding agent."""
from __future__ import annotations

import ast
import json
import shutil
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
from evrptw_autolab.synthesis.diagnostics import (  # noqa: F401
    format_runtime_error,
    progress_key,
    solution_diagnostic,
)

# Re-export for tests and callers that historically imported from this module.
__all__ = [
    "STAGES",
    "STAGE_CANDIDATES",
    "SingleAgent",
    "classify_category",
    "copy_run_provenance",
    "evaluate_through",
    "format_runtime_error",
    "owner_for",
    "precheck_source",
    "roles_for",
    "run_from_scratch",
    "solution_diagnostic",
    "usage_totals",
]

STAGES = ("executable", "routing", "charging", "multi_customer", "schneider_c5")
INTEGRATION = {"SYNTAX", "RUNTIME", "TIMEOUT", "GENERALITY"}
FAULTS = {"DEPOT", "VISIT", "CAPACITY", "WINDOW", "BATTERY", "CHARGE_POLICY"}

# Coding roles that emit a complete candidate solver.py for each stage.
STAGE_CANDIDATES: dict[str, list[str]] = {
    "executable": ["search"],
    "routing": ["routing", "search"],
    "charging": ["charging", "search"],
    "multi_customer": ["routing", "charging", "search"],
    "schneider_c5": ["routing", "charging", "search"],
}


class _SingleSchema(BaseModel):
    note: str = ""


class SingleAgent(Agent[_SingleSchema]):
    role = "single"
    prompt_name = "single_agent.md"
    schema = _SingleSchema


def usage_totals(usage: UsageLog) -> tuple[int, int, int]:
    rows = usage.all()
    prompt = sum(int(row.get("prompt_tokens") or 0) for row in rows)
    completion = sum(int(row.get("completion_tokens") or 0) for row in rows)
    return len(rows), prompt, completion


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
            "execution": {
                "exception_type": "SyntaxError",
                "exception_message": "missing def solve",
                "traceback_tail": "",
                "source_context": "",
            },
            "first_fault": {},
            "diagnostic": {"crashed": True, "syntax_valid": False, "family": "SYNTAX"},
            "gates_passed": 0,
            "instances_feasible": 0,
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
            "diagnostic": {"crashed": True, "syntax_valid": False, "family": "SYNTAX"},
            "gates_passed": 0,
            "instances_feasible": 0,
        }
    hardcoded = find_hardcoded_node_ids(text, known_ids=known_ids)
    if hardcoded:
        detail = ",".join(hardcoded)
        return {
            "category": "GENERALITY",
            "ok": False,
            "failure_reason": f"GENERALITY: {detail}",
            "execution": {},
            "first_fault": {
                "family": "GENERALITY",
                "node_id": "",
                "route_index": -1,
                "detail": detail,
            },
            "diagnostic": {"crashed": False, "syntax_valid": True, "family": "GENERALITY", "detail": detail},
            "gates_passed": 0,
            "instances_feasible": 0,
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
            "execution": {
                "exception_type": category,
                "exception_message": detail,
                "traceback_tail": detail,
                "source_context": "",
            },
            "first_fault": {},
            "diagnostic": {"crashed": True, "syntax_valid": category != "GENERALITY", "family": category},
            "gates_passed": 0,
            "instances_feasible": 0,
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


def _report_failure(
    stage: str,
    report: Any,
    source: str,
    *,
    instance: EVRPTWInstance | None = None,
    gates_passed: int = 0,
    instances_feasible: int = 0,
) -> dict[str, Any]:
    diagnostic = solution_diagnostic(report, source=source, instance=instance)
    if report.timed_out:
        category = "TIMEOUT"
        reason = "timeout"
        execution = format_runtime_error(report.error or "timeout", source)
    elif report.crashed or not report.parse_ok:
        category = "RUNTIME"
        execution = format_runtime_error(str(report.error or ""), source)
        reason = (
            f"{execution.get('exception_type') or 'RuntimeError'}: "
            f"{execution.get('exception_message') or ''}"
        ).strip()
    else:
        family = str(diagnostic.get("family") or "").upper()
        category = family if family in FAULTS else "RUNTIME"
        execution = {}
        reason = f"{category}: {diagnostic.get('detail') or ''}".strip()
        if category == "BATTERY" and diagnostic.get("battery_deficit"):
            reason = f"BATTERY: battery_deficit={diagnostic['battery_deficit']}"
    return {
        "ok": False,
        "failed_stage": stage,
        "category": category,
        "failure_reason": reason[:500],
        "execution": execution,
        "first_fault": {
            "family": diagnostic.get("family") or "",
            "node_id": diagnostic.get("failed_node") or "",
            "route_index": int((report.first_fault or {}).get("route_index", -1)),
            "detail": diagnostic.get("detail") or "",
        },
        "diagnostic": diagnostic,
        "gates_passed": gates_passed,
        "instances_feasible": instances_feasible,
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
    last: dict[str, Any] = {
        "ok": True,
        "failed_stage": "",
        "category": "",
        "failure_reason": "",
        "execution": {},
        "first_fault": {},
        "diagnostic": {},
        "gates_passed": 0,
        "instances_feasible": 0,
        "vehicles": None,
        "distance": None,
    }
    gates_passed = 0
    for name in STAGES[: STAGES.index(stage) + 1]:
        if name == "schneider_c5":
            passed = 0
            vehicles = 0
            distance = 0.0
            for instance in panel:
                report = run_solver(solver_dir, instance, seed=0, limits=limits)
                if not _stage_ok(name, report):
                    failed = _report_failure(
                        name,
                        report,
                        source,
                        instance=instance,
                        gates_passed=gates_passed,
                        instances_feasible=passed,
                    )
                    failed["g4_passed_here"] = passed
                    return failed
                passed += 1
                vehicles += int(report.vehicles or 0)
                distance += float(report.total_distance or 0.0)
            last = {
                "ok": True,
                "failed_stage": "",
                "category": "",
                "failure_reason": "",
                "execution": {},
                "first_fault": {},
                "diagnostic": {},
                "gates_passed": gates_passed + 1,
                "instances_feasible": passed,
                "g4_passed_here": passed,
                "vehicles": vehicles,
                "distance": round(distance, 4),
            }
            continue
        probe = _probe(name)
        if probe is None:
            raise RuntimeError(f"missing probe for {name}")
        report = run_solver(solver_dir, probe, seed=0, limits=limits)
        if not _stage_ok(name, report):
            return _report_failure(
                name,
                report,
                source,
                instance=probe,
                gates_passed=gates_passed,
                instances_feasible=0,
            )
        gates_passed += 1
        last = {
            "ok": True,
            "failed_stage": "",
            "category": "",
            "failure_reason": "",
            "execution": {},
            "first_fault": {},
            "diagnostic": {},
            "gates_passed": gates_passed,
            "instances_feasible": 1 if name != "executable" else 0,
            "vehicles": int(report.vehicles or 0) if report.feasible else None,
            "distance": float(report.total_distance or 0.0) if report.feasible else None,
        }
    return last


def roles_for(stage: str, category: str = "") -> list[str]:
    """Architect plus coding roles that produce complete solver.py candidates."""
    coding = list(STAGE_CANDIDATES.get(stage, ["search"]))
    if category in {"BATTERY", "WINDOW", "CHARGE_POLICY"} and "charging" not in coding:
        coding = ["charging", *coding]
    if category in {"VISIT", "DEPOT", "CAPACITY"} and "routing" not in coding:
        coding = ["routing", *coding]
    return ["architect", *coding]


def owner_for(category: str) -> str:
    if category in {"BATTERY", "WINDOW", "CHARGE_POLICY"}:
        return "charging"
    if category in {"VISIT", "DEPOT", "CAPACITY"}:
        return "routing"
    return "search"


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


def _lex_pass_key(info: dict[str, Any]) -> tuple:
    vehicles = info.get("vehicles")
    distance = info.get("distance")
    return (
        0 if vehicles is None else int(vehicles),
        0.0 if distance is None else float(distance),
    )


def _base_payload(
    *,
    stage: str,
    stage_index: int,
    committed: str,
    stage_best: str,
    failure: dict[str, Any],
    critic_note: dict[str, Any],
    instruction_extra: str = "",
) -> dict[str, Any]:
    return {
        "problem": PROBLEM_BRIEF,
        "stage": stage,
        "gates_required": list(STAGES[: stage_index + 1]),
        "instruction": (
            f"Current stage: {stage}. Preserve every earlier gate. "
            "Return one complete self-contained solver.py with module-level def solve. "
            "The depot id may appear only at the start and end of each route. "
            "Charging visits must appear as station node ids in the returned routes. "
            + instruction_extra
        ).strip(),
        "committed_solver_py": committed,
        "stage_best_solver_py": stage_best,
        "rejected_solver_py": failure.get("source") or "",
        "failure_reason": failure.get("failure_reason") or "",
        "failure_category": failure.get("category") or "",
        "execution": failure.get("execution") or {},
        "first_fault": failure.get("first_fault") or {},
        "diagnostic": failure.get("diagnostic") or {},
        "critic": critic_note,
    }


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
    stages: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Synthesize one solver.py. mode is 'five_agent' or 'single_agent'."""
    if mode not in {"five_agent", "single_agent"}:
        raise ValueError("mode must be five_agent or single_agent")
    active_stages = stages or STAGES
    for name in active_stages:
        if name not in STAGES:
            raise ValueError(f"unknown stage {name}")
    started = time.monotonic()
    workspace.mkdir(parents=True, exist_ok=True)
    committed_dir = workspace / "committed"
    trial_dir = workspace / "trial"
    rejected_dir = workspace / "rejected"
    candidates_dir = workspace / "candidates"
    usage = UsageLog(workspace / "llm_calls.jsonl")
    if usage.path.exists():
        usage.path.unlink()
    log_path = workspace / "rounds.jsonl"
    if log_path.exists():
        log_path.unlink()
    limits = RunLimits(wall_clock_s=20.0)
    panel = panel_instances(data_root) if "schneider_c5" in active_stages else []
    if "schneider_c5" in active_stages and len(panel) != 4:
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
    stage_best = ""
    stage_index = 0
    passed = {name: False for name in STAGES}
    failure: dict[str, Any] = {}
    critic_note: dict[str, Any] = {}
    architect_plan: dict[str, Any] | None = None
    planned_stage = ""
    planned_family = ""
    repair_step = 0
    rounds = 0
    budget_hit = False
    seen_hashes: set[str] = set()

    def calls() -> int:
        return usage_totals(usage)[0]

    def budget_left() -> bool:
        if calls() >= max_llm_calls:
            return False
        if token_ceiling is not None:
            _, prompt_tokens, completion_tokens = usage_totals(usage)
            if prompt_tokens + completion_tokens >= token_ceiling:
                return False
        return True

    while stage_index < len(active_stages):
        if not budget_left():
            budget_hit = True
            break
        stage = active_stages[stage_index]
        category = str(failure.get("category") or "")
        family = str((failure.get("diagnostic") or {}).get("family") or category)

        if mode == "five_agent":
            if repair_step == 1:
                producers = [owner_for(category)]
                repair_label = "first_repair"
            elif repair_step == 2:
                producers = ["search"]
                repair_label = "second_repair"
            else:
                producers = list(STAGE_CANDIDATES.get(stage, ["search"]))
                repair_label = "fresh"
            need_architect = planned_stage != stage or (
                family and family != planned_family and repair_step == 0
            )
        else:
            producers = ["single"]
            repair_label = "first_repair" if repair_step == 1 else (
                "second_repair" if repair_step == 2 else "fresh"
            )
            need_architect = False

        instruction_extra = ""
        if repair_step == 1:
            instruction_extra = (
                "First repair: edit the failed solver using the exact diagnostic. "
                "Return a complete solver.py."
            )
        elif repair_step == 2:
            instruction_extra = (
                "Second repair: use the failed solver, diagnostic, and Critic note. "
                "Return a complete solver.py."
            )

        payload = _base_payload(
            stage=stage,
            stage_index=STAGES.index(stage),
            committed=committed,
            stage_best=stage_best,
            failure=failure,
            critic_note=critic_note,
            instruction_extra=instruction_extra,
        )
        payload["repair"] = repair_step > 0
        payload["repair_step"] = repair_step

        try:
            if mode == "five_agent" and need_architect:
                architect_plan = team["architect"].run(payload).model_dump()
                planned_stage = stage
                planned_family = family
            if architect_plan:
                payload["architect"] = architect_plan

            candidate_rows: list[dict[str, Any]] = []
            for role in producers:
                if not budget_left():
                    budget_hit = True
                    break
                source = team[role].write_python(
                    payload, filename="solver.py", marker="def solve"
                )
                trial_hash = code_hash(source or "")
                same_round = any(row.get("hash") == trial_hash for row in candidate_rows)
                if same_round or (trial_hash in seen_hashes and repair_step == 0 and len(producers) > 1):
                    # Skip only same-round duplicates or previously failed hashes while
                    # another producer in this fresh round can still be evaluated.
                    already_evaluated = any(
                        row.get("hash") == trial_hash and not row.get("skipped_duplicate")
                        for row in candidate_rows
                    )
                    if already_evaluated or (
                        trial_hash in seen_hashes and any(not row.get("skipped_duplicate") for row in candidate_rows)
                    ):
                        candidate_rows.append(
                            {
                                "role": role,
                                "source": source or "",
                                "hash": trial_hash,
                                "skipped_duplicate": True,
                                "ok": False,
                                "category": "RUNTIME",
                                "failure_reason": "duplicate candidate hash skipped",
                            }
                        )
                        continue
                seen_hashes.add(trial_hash)
                blocked = precheck_source(source or "", known_ids)
                if blocked is not None:
                    info = blocked
                    ok = False
                else:
                    cand_dir = candidates_dir / f"r{rounds + 1}_{role}"
                    _write_solver(cand_dir, source or "")
                    _write_solver(trial_dir, source or "")
                    info = evaluate_through(cand_dir, stage, limits=limits, panel=panel)
                    ok = bool(info.get("ok"))
                if not ok and (source or "").strip():
                    _write_solver(rejected_dir, source or "")
                row = {
                    "role": role,
                    "source": source or "",
                    "hash": trial_hash,
                    "ok": ok,
                    "category": info.get("category") or "",
                    "failure_reason": info.get("failure_reason") or "",
                    "execution": info.get("execution") or {},
                    "first_fault": info.get("first_fault") or {},
                    "diagnostic": info.get("diagnostic") or {},
                    "gates_passed": info.get("gates_passed") or 0,
                    "instances_feasible": info.get("instances_feasible") or 0,
                    "vehicles": info.get("vehicles"),
                    "distance": info.get("distance"),
                    "info": info,
                }
                candidate_rows.append(row)
                if not ok:
                    ideas = payload.get("specialist_ideas")
                    if not isinstance(ideas, list):
                        ideas = []
                        payload["specialist_ideas"] = ideas
                    ideas.append(
                        {
                            "role": role,
                            "failure_reason": str(row.get("failure_reason") or "")[:200],
                        }
                    )
        except BudgetExhausted:
            budget_hit = True
            break
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            failure = {
                "category": "RUNTIME",
                "failure_reason": f"model_error: {error}"[:500],
                "execution": {},
                "first_fault": {},
                "diagnostic": {"crashed": True, "family": "RUNTIME"},
                "source": "",
            }
            break

        if budget_hit and not candidate_rows:
            break

        rounds += 1
        passing = [row for row in candidate_rows if row.get("ok")]
        if passing:
            best = sorted(passing, key=lambda row: _lex_pass_key(row))[0]
            committed = best["source"]
            stage_best = ""
            _write_solver(committed_dir, committed)
            for name in STAGES[: STAGES.index(stage) + 1]:
                if name in active_stages[: stage_index + 1] or name in STAGES[: STAGES.index(stage) + 1]:
                    passed[name] = True
            # Mark all active stages up through current.
            for name in active_stages[: stage_index + 1]:
                passed[name] = True
            stage_index += 1
            failure = {}
            repair_step = 0
            planned_family = ""
            seen_hashes.clear()
        else:
            evaluated = [row for row in candidate_rows if not row.get("skipped_duplicate")]
            if evaluated:
                best_failed = max(evaluated, key=progress_key)
                if not stage_best or progress_key(best_failed) > progress_key(
                    {
                        "gates_passed": failure.get("gates_passed") or 0,
                        "instances_feasible": failure.get("instances_feasible") or 0,
                        "diagnostic": failure.get("diagnostic") or {},
                    }
                ):
                    stage_best = best_failed["source"]
                failure = {
                    "category": best_failed.get("category") or "RUNTIME",
                    "failure_reason": best_failed.get("failure_reason") or "",
                    "execution": best_failed.get("execution") or {},
                    "first_fault": best_failed.get("first_fault") or {},
                    "diagnostic": best_failed.get("diagnostic") or {},
                    "gates_passed": best_failed.get("gates_passed") or 0,
                    "instances_feasible": best_failed.get("instances_feasible") or 0,
                    "source": best_failed.get("source") or "",
                }
            if not evaluated:
                seen_hashes.clear()
                repair_step = 0
            elif repair_step < 2:
                repair_step += 1
            else:
                repair_step = 0
                seen_hashes.clear()

        if mode == "five_agent" and candidate_rows:
            try:
                decision = team["critic"].run(
                    {
                        "stage": stage,
                        "passed": bool(passing),
                        "candidates": [
                            {
                                "role": row.get("role"),
                                "ok": row.get("ok"),
                                "category": row.get("category"),
                                "failure_reason": row.get("failure_reason"),
                                "diagnostic": row.get("diagnostic"),
                                "gates_passed": row.get("gates_passed"),
                                "instances_feasible": row.get("instances_feasible"),
                            }
                            for row in candidate_rows
                        ],
                        "failure_reason": failure.get("failure_reason") or "",
                        "failure_category": failure.get("category") or "",
                        "execution": failure.get("execution") or {},
                        "first_fault": failure.get("first_fault") or {},
                        "diagnostic": failure.get("diagnostic") or {},
                        "evaluation": {"passed": bool(passing), "stage": stage},
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
            except (TypeError, ValueError, KeyError):
                critic_note = critic_note or {
                    "diagnosis": failure.get("failure_reason") or "",
                    "evidence": [],
                    "recommended_next_target": "SEARCH",
                }

        n_calls, prompt_tokens, completion_tokens = usage_totals(usage)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "round": rounds,
                        "stage": stage,
                        "passed": bool(passing),
                        "repair_step": repair_step if not passing else 0,
                        "repair_label": repair_label,
                        "roles": [row.get("role") for row in candidate_rows],
                        "candidates": [
                            {
                                "role": row.get("role"),
                                "ok": row.get("ok"),
                                "category": row.get("category"),
                                "hash": row.get("hash"),
                                "skipped_duplicate": bool(row.get("skipped_duplicate")),
                            }
                            for row in candidate_rows
                        ],
                        "failure_category": failure.get("category") or "",
                        "failure_reason": failure.get("failure_reason") or "",
                        "critic": critic_note,
                        "calls": n_calls,
                        "tokens": prompt_tokens + completion_tokens,
                    }
                )
                + "\n"
            )
        if budget_hit or not budget_left():
            budget_hit = True
            break

    g4_passed = bool(passed.get("schneider_c5"))
    confirmation_feasible = None
    confirmation_total = None
    g4_feasible = 0
    vehicles = None
    distance = None
    fully = False
    if committed.strip():
        _write_solver(committed_dir, committed)
        if panel:
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
    if (
        token_ceiling is not None
        and not g4_passed
        and tokens >= token_ceiling
        and category not in FAULTS | INTEGRATION
    ):
        category = "BUDGET"
    rows = usage.all()
    digest = next((str(row.get("digest") or "") for row in rows if row.get("digest")), "")
    model_tag = next(
        (str(row.get("model_tag") or "") for row in rows if row.get("model_tag")), model
    )
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


def copy_run_provenance(workspace: Path, dest: Path, report: dict[str, Any]) -> None:
    """Copy result.json, rounds, llm_calls, and final solver into results/paper/raw/."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name in ("rounds.jsonl", "llm_calls.jsonl"):
        source = workspace / name
        if source.exists():
            shutil.copyfile(source, dest / name)
    solver = workspace / "committed" / "solver.py"
    if solver.exists() and solver.read_text(encoding="utf-8").strip():
        shutil.copyfile(solver, dest / "solver.py")
