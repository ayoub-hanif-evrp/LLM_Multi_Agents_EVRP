"""From-scratch solver synthesis: five-agent team or one coding agent."""
from __future__ import annotations

import ast
import json
import shutil
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from evrptw_autolab.agents import build_team
from evrptw_autolab.agents.base import Agent, extract_json, extract_python_source
from evrptw_autolab.evolution.evaluate import (
    all_c5_instances,
    code_hash,
    find_hardcoded_node_ids,
    known_ids_for_panel,
    panel_instances,
)
from evrptw_autolab.evolution.patch_apply import apply_proposal, parse_proposal_json
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

__all__ = [
    "STAGES",
    "STAGE_CANDIDATES",
    "PROPOSALS_PER_ROLE",
    "NOOP_NOTE",
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
PROPOSALS_PER_ROLE = 2
NOOP_NOTE = (
    "The proposed patch produced a program already tested at this stage. "
    "Make a materially different code change based on the diagnostic."
)
PATCH_FAIL_NOTE = (
    "Previous patch JSON failed to parse or apply. "
    "Top-level symbols only (nested defs inside solve cannot be REPLACE targets). "
    "Either ADD new module-level helpers and REPLACE solve to call them, "
    "or REPLACE solve itself. Ops must use action ADD|REPLACE|REMOVE."
)
MODULAR_CREATE_NOTE = (
    "Put helpers as MODULE-LEVEL functions (def build_routes, def insert_charge, ...), "
    "not nested inside solve. Later patches REPLACE one top-level function at a time."
)

# Coding roles that propose candidates for each stage (Architect/Critic separate).
STAGE_CANDIDATES: dict[str, list[str]] = {
    "executable": ["search"],
    "routing": ["routing", "search"],
    "charging": ["charging", "search"],
    "multi_customer": ["routing", "charging", "search"],
    "schneider_c5": ["routing", "charging", "search"],
}


class _SingleSchema(BaseModel):
    note: str = ""


class _PatchSchema(BaseModel):
    hypothesis: str = ""
    ops: list[dict[str, Any]] = Field(default_factory=list)


class SingleAgent(Agent[_SingleSchema]):
    role = "single"
    prompt_name = "single_agent.md"
    schema = _SingleSchema


def usage_totals(usage: UsageLog) -> tuple[int, int, int]:
    rows = usage.all()
    prompt = sum(int(row.get("prompt_tokens") or 0) for row in rows)
    completion = sum(int(row.get("completion_tokens") or 0) for row in rows)
    return len(rows), prompt, completion


def classify_category(*, g4_passed: bool, category: str, budget: bool) -> str:
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
        return _blocked("SYNTAX", "model did not return def solve", syntax=True)
    try:
        ast.parse(text)
    except SyntaxError as error:
        return _blocked("SYNTAX", f"SyntaxError: {error.msg}", syntax=True, detail=str(error))
    hardcoded = find_hardcoded_node_ids(text, known_ids=known_ids)
    if hardcoded:
        detail = ",".join(hardcoded)
        return {
            "category": "GENERALITY",
            "ok": False,
            "failure_reason": f"GENERALITY: {detail}",
            "execution": {},
            "first_fault": {"family": "GENERALITY", "node_id": "", "route_index": -1, "detail": detail},
            "diagnostic": {"crashed": False, "syntax_valid": True, "family": "GENERALITY", "detail": detail},
            "gates_passed": 0,
            "instances_feasible": 0,
            "by_instance": {},
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
        return _blocked(category, detail, syntax=(category == "SYNTAX"), detail=detail)
    return None


def _blocked(category: str, reason: str, *, syntax: bool, detail: str = "") -> dict[str, Any]:
    return {
        "category": category,
        "ok": False,
        "failure_reason": reason,
        "execution": {
            "exception_type": "SyntaxError" if syntax else category,
            "exception_message": reason,
            "traceback_tail": detail or reason,
            "source_context": "",
        },
        "first_fault": {},
        "diagnostic": {"crashed": True, "syntax_valid": not syntax or category == "SYNTAX", "family": category},
        "gates_passed": 0,
        "instances_feasible": 0,
        "by_instance": {},
    }


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
    by_instance: dict[str, Any] | None = None,
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
        "by_instance": by_instance or {},
    }


def evaluate_through(
    solver_dir: Path,
    stage: str,
    *,
    limits: RunLimits,
    panel: list[EVRPTWInstance],
) -> dict[str, Any]:
    """A later gate counts only when every earlier gate still passes.

    For schneider_c5 every development instance is evaluated; scoring uses X/4.
    """
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
        "by_instance": {},
        "vehicles": None,
        "distance": None,
    }
    gates_passed = 0
    for name in STAGES[: STAGES.index(stage) + 1]:
        if name == "schneider_c5":
            by_instance: dict[str, Any] = {}
            passed = 0
            vehicles = 0
            distance = 0.0
            first_fail: dict[str, Any] | None = None
            missing: list[str] = []
            duplicated: list[str] = []
            depot_violations = 0
            capacity_excess = 0.0
            battery_deficit = 0.0
            lateness = 0.0
            for instance in panel:
                report = run_solver(solver_dir, instance, seed=0, limits=limits)
                ok = _stage_ok(name, report)
                entry: dict[str, Any] = {"ok": ok}
                if ok:
                    passed += 1
                    vehicles += int(report.vehicles or 0)
                    distance += float(report.total_distance or 0.0)
                    entry["vehicles"] = int(report.vehicles or 0)
                    entry["distance"] = float(report.total_distance or 0.0)
                else:
                    fail = _report_failure(
                        name,
                        report,
                        source,
                        instance=instance,
                        gates_passed=gates_passed,
                        instances_feasible=passed,
                    )
                    entry["category"] = fail["category"]
                    entry["failure_reason"] = fail["failure_reason"]
                    entry["diagnostic"] = fail.get("diagnostic") or {}
                    diag = dict(entry["diagnostic"] or {})
                    missing = _unique_str_ids(missing + list(diag.get("customers_missing") or []))
                    duplicated = _unique_str_ids(
                        duplicated + list(diag.get("customers_duplicated") or [])
                    )
                    depot_violations += int(diag.get("depot_violations") or 0)
                    capacity_excess += float(diag.get("capacity_excess") or 0.0)
                    battery_deficit += float(diag.get("battery_deficit") or 0.0)
                    lateness += float(diag.get("lateness") or 0.0)
                    if first_fail is None:
                        first_fail = fail
                by_instance[instance.instance_id] = entry
            if passed == len(panel) and panel:
                return {
                    "ok": True,
                    "failed_stage": "",
                    "category": "",
                    "failure_reason": "",
                    "execution": {},
                    "first_fault": {},
                    "diagnostic": {},
                    "gates_passed": gates_passed + 1,
                    "instances_feasible": passed,
                    "by_instance": by_instance,
                    "g4_passed_here": passed,
                    "vehicles": vehicles,
                    "distance": round(distance, 4),
                }
            total_diag = {
                "customers_missing": missing,
                "customers_duplicated": duplicated,
                "depot_violations": depot_violations,
                "capacity_excess": round(capacity_excess, 4),
                "battery_deficit": round(battery_deficit, 4),
                "lateness": round(lateness, 4),
                "g4_feasible": passed,
                "g4_total": len(panel),
            }
            failed = first_fail or {
                "ok": False,
                "failed_stage": name,
                "category": "RUNTIME",
                "failure_reason": "no panel instance feasible",
                "execution": {},
                "first_fault": {},
                "diagnostic": total_diag,
            }
            failed["ok"] = False
            failed["gates_passed"] = gates_passed
            failed["instances_feasible"] = passed
            failed["by_instance"] = by_instance
            failed["g4_passed_here"] = passed
            failed["diagnostic"] = {
                **dict(failed.get("diagnostic") or {}),
                **total_diag,
            }
            failed["failure_reason"] = (
                f"G4 {passed}/{len(panel)}; "
                + str(failed.get("failure_reason") or "")
            )[:500]
            return failed

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
            "by_instance": {},
            "vehicles": int(report.vehicles or 0) if report.feasible else None,
            "distance": float(report.total_distance or 0.0) if report.feasible else None,
        }
    return last


def roles_for(stage: str, category: str = "") -> list[str]:
    coding = list(STAGE_CANDIDATES.get(stage, ["search"]))
    if category in {"BATTERY", "WINDOW", "CHARGE_POLICY"}:
        coding = ["charging", "search"]
    elif category in {"VISIT", "DEPOT", "CAPACITY"}:
        coding = ["routing", "search"]
    return ["architect", *coding]


def owner_for(category: str) -> str:
    if category in {"BATTERY", "WINDOW", "CHARGE_POLICY"}:
        return "charging"
    if category in {"VISIT", "DEPOT", "CAPACITY"}:
        return "routing"
    return "search"


def coding_roles_for(stage: str, category: str = "") -> list[str]:
    return [role for role in roles_for(stage, category) if role != "architect"]


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


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _unique_str_ids(values: Any) -> list[str]:
    """Flatten nested id lists and dedupe while keeping order."""
    out: list[str] = []
    seen: set[str] = set()

    def walk(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, (list, tuple, set)):
            for child in item:
                walk(child)
            return
        text = str(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)

    walk(values)
    return out


def _top_level_names(source: str) -> list[str]:
    try:
        tree = ast.parse(source or "")
    except SyntaxError:
        return []
    return [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]


def _source_from_files_payload(data: dict[str, Any]) -> str:
    files = data.get("files") or []
    if not isinstance(files, list):
        return ""
    for item in files:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")
        if "def solve" in content:
            return content
    return ""


def _request_full_solver(agent: Agent[Any], payload: dict[str, Any]) -> str:
    body = dict(payload)
    instruction = str(body.get("instruction") or "")
    if MODULAR_CREATE_NOTE not in instruction:
        body["instruction"] = (instruction + " " + MODULAR_CREATE_NOTE).strip()
    return agent.write_python(body, filename="solver.py", marker="def solve")


def _request_patch(agent: Agent[Any], payload: dict[str, Any], parent: str) -> tuple[str, str]:
    """Return (source, error). error non-empty means apply/parse failed."""
    symbols = _top_level_names(parent)
    body = dict(payload)
    body["mode"] = "patch"
    body["parent_top_level_symbols"] = symbols
    body["instruction"] = (
        str(payload.get("instruction") or "")
        + " Return ONLY one JSON object with keys hypothesis and ops. "
        "Each op is {action: ADD|REPLACE|REMOVE, symbol: function_name, code: def ...}. "
        f"Parent top-level symbols: {symbols or ['(none — ADD helpers then REPLACE solve)']}. "
        "Nested functions inside solve are NOT patchable; ADD module-level helpers or REPLACE solve. "
        "Prefer changing one top-level function. Keep def solve."
    ).strip()
    prompt = (
        agent.prompt
        + "\n\nINPUT:\n"
        + json.dumps({k: v for k, v in body.items() if k != "instruction"}, default=str)
        + "\n\n"
        + body["instruction"]
    )
    raw = agent._complete(prompt, json_mode=True)
    text = raw if isinstance(raw, str) else str(raw)
    try:
        data = extract_json(text)
    except (ValueError, json.JSONDecodeError, TypeError) as error:
        fallback = extract_python_source(text)
        if "def solve" in fallback:
            return fallback, ""
        return "", f"patch_parse: {error}"
    try:
        proposal = parse_proposal_json(data, role=getattr(agent, "role", ""))
    except (ValueError, TypeError, KeyError) as error:
        files_src = _source_from_files_payload(data)
        if "def solve" in files_src:
            return files_src, ""
        fallback = extract_python_source(text)
        if "def solve" in fallback:
            return fallback, ""
        return "", f"patch_parse: {error}"
    applied = apply_proposal(parent, proposal)
    if applied.ok:
        return applied.source, ""
    files_src = _source_from_files_payload(data)
    if "def solve" in files_src:
        return files_src, ""
    return "", f"patch_apply: {applied.error}"


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
    proposals_per_role: int = PROPOSALS_PER_ROLE,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Synthesize one solver.py. mode is 'five_agent' or 'single_agent'."""
    if mode not in {"five_agent", "single_agent"}:
        raise ValueError("mode must be five_agent or single_agent")
    active_stages = stages or STAGES
    for name in active_stages:
        if name not in STAGES:
            raise ValueError(f"unknown stage {name}")
    root = repo_root or Path(__file__).resolve().parents[3]
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
    stage_best_info: dict[str, Any] = {}
    stage_index = 0
    passed = {name: False for name in STAGES}
    failure: dict[str, Any] = {}
    critic_note: dict[str, Any] = {}
    architect_plan: dict[str, Any] | None = None
    planned_stage = ""
    planned_family = ""
    rounds = 0
    budget_hit = False
    failed_hashes: set[str] = set()
    best_g4 = 0

    def calls() -> int:
        return usage_totals(usage)[0]

    def tokens_spent() -> int:
        _, prompt_tokens, completion_tokens = usage_totals(usage)
        return prompt_tokens + completion_tokens

    def budget_left() -> bool:
        if calls() >= max_llm_calls:
            return False
        if token_ceiling is not None and tokens_spent() >= token_ceiling:
            return False
        return True

    def base_payload(stage: str, extra: str = "") -> dict[str, Any]:
        return {
            "problem": PROBLEM_BRIEF,
            "stage": stage,
            "gates_required": list(STAGES[: STAGES.index(stage) + 1]),
            "instruction": (
                f"Current stage: {stage}. Preserve every earlier gate. "
                + (
                    "Return a small ADD/REPLACE/REMOVE patch against committed_solver_py. "
                    if committed.strip()
                    else (
                        "Return one complete self-contained solver.py. "
                        + MODULAR_CREATE_NOTE
                        + " "
                    )
                )
                + "Depot only at route ends. Station ids must appear in routes for charging. "
                + extra
            ).strip(),
            "committed_solver_py": committed,
            "stage_best_solver_py": stage_best,
            "rejected_solver_py": failure.get("source") or "",
            "failure_reason": failure.get("failure_reason") or "",
            "failure_category": failure.get("category") or "",
            "execution": failure.get("execution") or {},
            "first_fault": failure.get("first_fault") or {},
            "diagnostic": failure.get("diagnostic") or {},
            "by_instance": failure.get("by_instance") or {},
            "critic": critic_note,
            "use_patches": bool(committed.strip()),
        }

    def produce_source(agent: Agent[Any], payload: dict[str, Any]) -> tuple[str, str]:
        if committed.strip():
            return _request_patch(agent, payload, committed if not stage_best else (stage_best or committed))
        return _request_full_solver(agent, payload), ""

    while stage_index < len(active_stages):
        if not budget_left():
            budget_hit = True
            break
        stage = active_stages[stage_index]
        category = str(failure.get("category") or "")
        family = str((failure.get("diagnostic") or {}).get("family") or category)

        if mode == "five_agent":
            producers = coding_roles_for(stage, category)
            need_architect = planned_stage != stage or (family and family != planned_family)
        else:
            producers = ["single"]
            need_architect = False

        payload = base_payload(stage)
        candidate_rows: list[dict[str, Any]] = []

        try:
            if mode == "five_agent" and need_architect and budget_left():
                architect_plan = team["architect"].run(payload).model_dump()
                planned_stage = stage
                planned_family = family
            if architect_plan:
                payload["architect"] = architect_plan

            parent_for_patch = stage_best if stage_best.strip() else committed
            for role in producers:
                for _proposal_ix in range(max(1, int(proposals_per_role))):
                    if not budget_left():
                        budget_hit = True
                        break
                    agent = team[role]
                    attempt_payload = dict(payload)
                    source = ""
                    apply_error = ""
                    resampled = False
                    used_full_fallback = False
                    for attempt in range(3):
                        if not budget_left():
                            budget_hit = True
                            break
                        if attempt == 1:
                            attempt_payload = dict(payload)
                            note = NOOP_NOTE if apply_error == "noop_or_duplicate" else PATCH_FAIL_NOTE
                            if apply_error and apply_error not in {"noop_or_duplicate", ""}:
                                note = f"{PATCH_FAIL_NOTE} Last error: {apply_error}."
                            attempt_payload["instruction"] = (
                                str(payload.get("instruction") or "") + " " + note
                            ).strip()
                            resampled = True
                        if attempt == 2 and parent_for_patch.strip() and committed.strip():
                            # Patches could not land on this parent; allow one complete rewrite.
                            used_full_fallback = True
                            attempt_payload = dict(payload)
                            attempt_payload["use_patches"] = False
                            attempt_payload["instruction"] = (
                                str(payload.get("instruction") or "")
                                + " Patch mode failed twice. Return a COMPLETE modular solver.py. "
                                + MODULAR_CREATE_NOTE
                            ).strip()
                            source = _request_full_solver(agent, attempt_payload)
                            apply_error = ""
                        elif parent_for_patch.strip() and committed.strip() and not used_full_fallback:
                            source, apply_error = _request_patch(
                                agent, attempt_payload, parent_for_patch
                            )
                        else:
                            source = _request_full_solver(agent, attempt_payload)
                            apply_error = ""
                        if apply_error and apply_error != "noop_or_duplicate":
                            source = ""
                            continue
                        if not (source or "").strip():
                            apply_error = apply_error or "empty candidate"
                            continue
                        trial_hash = code_hash(source)
                        if trial_hash == code_hash(parent_for_patch) or trial_hash in failed_hashes:
                            apply_error = "noop_or_duplicate"
                            source = ""
                            continue
                        apply_error = ""
                        break
                    if budget_hit:
                        break
                    if apply_error or not (source or "").strip():
                        candidate_rows.append(
                            {
                                "role": role,
                                "source": "",
                                "hash": "",
                                "ok": False,
                                "skipped_noop": True,
                                "resampled": resampled,
                                "category": "RUNTIME",
                                "failure_reason": apply_error or "empty candidate",
                                "gates_passed": 0,
                                "instances_feasible": 0,
                                "by_instance": {},
                                "diagnostic": {},
                            }
                        )
                        continue
                    trial_hash = code_hash(source)
                    if trial_hash in failed_hashes or trial_hash == code_hash(parent_for_patch):
                        candidate_rows.append(
                            {
                                "role": role,
                                "source": source,
                                "hash": trial_hash,
                                "ok": False,
                                "skipped_noop": True,
                                "resampled": resampled,
                                "category": "RUNTIME",
                                "failure_reason": "noop_or_duplicate",
                                "gates_passed": 0,
                                "instances_feasible": 0,
                                "by_instance": {},
                                "diagnostic": {},
                            }
                        )
                        continue
                    blocked = precheck_source(source, known_ids)
                    if blocked is not None:
                        info = blocked
                        ok = False
                    else:
                        cand_dir = candidates_dir / f"r{rounds + 1}_{role}_{_proposal_ix}"
                        _write_solver(cand_dir, source)
                        _write_solver(trial_dir, source)
                        info = evaluate_through(cand_dir, stage, limits=limits, panel=panel)
                        ok = bool(info.get("ok"))
                    if not ok:
                        failed_hashes.add(trial_hash)
                        if (source or "").strip():
                            _write_solver(rejected_dir, source)
                    row = {
                        "role": role,
                        "source": source,
                        "hash": trial_hash,
                        "ok": ok,
                        "skipped_noop": False,
                        "resampled": resampled,
                        "category": info.get("category") or "",
                        "failure_reason": info.get("failure_reason") or "",
                        "execution": info.get("execution") or {},
                        "first_fault": info.get("first_fault") or {},
                        "diagnostic": info.get("diagnostic") or {},
                        "gates_passed": info.get("gates_passed") or 0,
                        "instances_feasible": info.get("instances_feasible") or 0,
                        "by_instance": info.get("by_instance") or {},
                        "vehicles": info.get("vehicles"),
                        "distance": info.get("distance"),
                        "info": info,
                    }
                    candidate_rows.append(row)
                if budget_hit:
                    break
        except BudgetExhausted:
            budget_hit = True
        except (RuntimeError, ValueError, KeyError, TypeError) as error:
            failure = {
                "category": "RUNTIME",
                "failure_reason": f"model_error: {error}"[:500],
                "execution": {},
                "first_fault": {},
                "diagnostic": {"crashed": True, "family": "RUNTIME"},
                "source": "",
                "by_instance": {},
            }
            break

        evaluated = [row for row in candidate_rows if not row.get("skipped_noop")]
        if not evaluated and not candidate_rows:
            if budget_hit:
                break
            continue

        rounds += 1
        passing = [row for row in evaluated if row.get("ok")]
        if passing:
            best = sorted(passing, key=_lex_pass_key)[0]
            committed = best["source"]
            stage_best = ""
            stage_best_info = {}
            _write_solver(committed_dir, committed)
            for name in active_stages[: stage_index + 1]:
                passed[name] = True
            for name in STAGES[: STAGES.index(stage) + 1]:
                passed[name] = True
            if stage == "schneider_c5":
                best_g4 = max(best_g4, int(best.get("instances_feasible") or 0))
            stage_index += 1
            failure = {}
            critic_note = {}
            planned_family = ""
            failed_hashes.clear()
        else:
            if evaluated:
                best_failed = max(evaluated, key=progress_key)
                if not stage_best or progress_key(best_failed) > progress_key(stage_best_info or {}):
                    stage_best = best_failed["source"]
                    stage_best_info = best_failed
                best_g4 = max(best_g4, int(best_failed.get("instances_feasible") or 0))
                failure = {
                    "category": best_failed.get("category") or "RUNTIME",
                    "failure_reason": best_failed.get("failure_reason") or "",
                    "execution": best_failed.get("execution") or {},
                    "first_fault": best_failed.get("first_fault") or {},
                    "diagnostic": best_failed.get("diagnostic") or {},
                    "gates_passed": best_failed.get("gates_passed") or 0,
                    "instances_feasible": best_failed.get("instances_feasible") or 0,
                    "by_instance": best_failed.get("by_instance") or {},
                    "source": best_failed.get("source") or "",
                }
            if mode == "five_agent" and evaluated and budget_left():
                try:
                    decision = team["critic"].run(
                        {
                            "stage": stage,
                            "passed": False,
                            "candidates": [
                                {
                                    "role": row.get("role"),
                                    "ok": row.get("ok"),
                                    "category": row.get("category"),
                                    "failure_reason": row.get("failure_reason"),
                                    "instances_feasible": row.get("instances_feasible"),
                                    "by_instance": row.get("by_instance"),
                                    "diagnostic": row.get("diagnostic"),
                                }
                                for row in evaluated
                            ],
                            "failure_reason": failure.get("failure_reason") or "",
                            "failure_category": failure.get("category") or "",
                            "diagnostic": failure.get("diagnostic") or {},
                            "by_instance": failure.get("by_instance") or {},
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
                        "roles": [row.get("role") for row in candidate_rows],
                        "candidates": [
                            {
                                "role": row.get("role"),
                                "ok": row.get("ok"),
                                "category": row.get("category"),
                                "hash": (row.get("hash") or "")[:16],
                                "instances_feasible": row.get("instances_feasible"),
                                "skipped_noop": bool(row.get("skipped_noop")),
                                "by_instance": {
                                    key: {"ok": val.get("ok"), "category": val.get("category")}
                                    for key, val in (row.get("by_instance") or {}).items()
                                },
                            }
                            for row in candidate_rows
                        ],
                        "failure_category": failure.get("category") or "",
                        "failure_reason": failure.get("failure_reason") or "",
                        "best_g4": best_g4,
                        "critic": critic_note if not passing else {},
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
            best_g4 = max(best_g4, g4_count)
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
        "best_g4_feasible": best_g4,
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
        "solver_path": _relative(solver_path, root),
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
