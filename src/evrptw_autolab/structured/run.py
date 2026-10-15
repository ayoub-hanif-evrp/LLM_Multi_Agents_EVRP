"""Experiment B: structured function-by-function synthesis with a population archive."""
from __future__ import annotations

import json
import random
import shutil
import time
from pathlib import Path
from typing import Any

from evrptw_autolab.evolution.evaluate import code_hash, write_solver
from evrptw_autolab.llm.usage import BudgetExhausted, UsageLog
from evrptw_autolab.sandbox.limits import limits_from_config
from evrptw_autolab.structured.archive import Population
from evrptw_autolab.structured.codegen import (
    apply_function_to_solver,
    generate_function,
    level_a_micro_pass,
    llm_complete,
    load_prompt,
    parts_from_source,
    reassemble_from_parts,
    unit_test_functions,
)
from evrptw_autolab.structured.failure_memory import FailureMemory, FailureRecord
from evrptw_autolab.structured.fitness import (
    evaluate_candidate,
    fitness_key,
    known_ids_for_panel,
    panel_instances,
)
from evrptw_autolab.structured.signatures import (
    DEFAULT_IMPORTS,
    REQUIRED_FUNCTIONS,
    stub_solver_source,
)
from evrptw_autolab.structured.spec import FormalSpec, default_spec, freeze_spec, validate_spec
from evrptw_autolab.synthesis.from_scratch import classify_category, usage_totals
from evrptw_autolab.synthesis.provenance import stamp_report

ROOT = Path(__file__).resolve().parents[3]

DEFAULT_MAX_GENERATIONS = 12
DEFAULT_ARCHIVE_SIZE = 8
DEFAULT_OFFSPRING = 12
DEFAULT_MAX_LLM_CALLS = 400


def _write_solver(directory: Path, source: str) -> None:
    write_solver(directory, source)


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _architect_spec(
    backend: Any,
    *,
    model: str,
    usage_log: UsageLog,
    max_calls: int,
    token_ceiling: int | None,
) -> FormalSpec:
    prompt = load_prompt("architect_spec.md") + "\n\nINPUT:\n" + json.dumps(
        {"task": "Produce the immutable FormalSpec JSON for EVRPTW structured synthesis."}
    )
    try:
        raw = llm_complete(
            backend,
            prompt=prompt,
            role="architect",
            model=model,
            temperature=0.2,
            json_mode=True,
            usage_log=usage_log,
            max_calls=max_calls,
            token_ceiling=token_ceiling,
            reasoning_effort="high",
        )
        from evrptw_autolab.agents.base import extract_json

        data = extract_json(raw)
        return freeze_spec(data)
    except (BudgetExhausted, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return default_spec()
    except Exception:  # noqa: BLE001
        return default_spec()


def _bootstrap_functions(
    *,
    backend: Any,
    model: str,
    spec: FormalSpec,
    workspace: Path,
    usage_log: UsageLog,
    max_calls: int,
    token_ceiling: int | None,
    rng: random.Random,
    function_by_function: bool,
    temperatures: dict[str, float],
) -> tuple[str, dict[str, Any]]:
    """Generate construct→repair→improve→solve until Level A unit tests pass."""
    parts: dict[str, str] = parts_from_source(stub_solver_source())
    source = stub_solver_source()
    meta: dict[str, Any] = {"bootstrap_rounds": 0, "level_a": {}}
    order = list(REQUIRED_FUNCTIONS)
    if not function_by_function:
        # Single shot: ask for solve that embeds helpers, still assemble four defs.
        order = ["construct", "repair", "improve", "solve"]

    for _round in range(8):
        meta["bootstrap_rounds"] = _round + 1
        for fname in order:
            if usage_totals(usage_log)[0] >= max_calls:
                break
            temp = float(temperatures.get(fname, temperatures.get("default", 0.4)))
            # Breadth vs depth: alternate temperature.
            if _round % 2 == 1:
                temp = min(1.0, temp + 0.25)
            effort = "high" if fname in {"solve", "repair"} and _round % 2 == 0 else "medium"
            name, code, err = generate_function(
                backend,
                function_name=fname,
                model=model,
                spec=spec,
                parent_source=source,
                temperature=temp,
                usage_log=usage_log,
                max_calls=max_calls,
                token_ceiling=token_ceiling,
                reasoning_effort=effort,
                extra_context={"bootstrap_round": _round},
            )
            if err or not code.strip():
                continue
            target = name or fname
            new_source, apply_err = apply_function_to_solver(source, target, code)
            if apply_err or not new_source.strip():
                # If we only have the function body, stash into parts and reassemble.
                if code.strip().startswith("def "):
                    parts[fname] = code
                    source = reassemble_from_parts(parts, DEFAULT_IMPORTS)
                continue
            source = new_source
            parts = parts_from_source(source) or parts
            parts[fname] = parts.get(fname) or code

        source = reassemble_from_parts(parts, DEFAULT_IMPORTS) if parts else source
        unit = unit_test_functions(source)
        trial = workspace / "trial"
        _write_solver(trial, source)
        if unit.get("ok"):
            level = level_a_micro_pass(trial)
            meta["level_a"] = level
            if level.get("ok") or level.get("gates", {}).get("executable"):
                # Accept if at least executable; Level A full is preferred.
                if level.get("ok") or unit.get("ok"):
                    meta["unit"] = unit
                    return source, meta
        meta["unit"] = unit
        # Keep trying until budget.
        if usage_totals(usage_log)[0] >= max_calls:
            break

    # Last resort: assemble whatever we have.
    if parts:
        source = reassemble_from_parts(parts, DEFAULT_IMPORTS)
    meta["unit"] = unit_test_functions(source)
    _write_solver(workspace / "trial", source)
    meta["level_a"] = level_a_micro_pass(workspace / "trial")
    return source, meta


def _mutate_one(
    backend: Any,
    *,
    parent: str,
    model: str,
    spec: FormalSpec,
    usage_log: UsageLog,
    max_calls: int,
    token_ceiling: int | None,
    rng: random.Random,
    failure_memory: FailureMemory | None,
    temperatures: dict[str, float],
    mode: str = "mutate",
    other_parent: str = "",
) -> tuple[str, str]:
    """LLM patch preferably one function. Returns (source, function_changed)."""
    target = rng.choice(list(REQUIRED_FUNCTIONS))
    relevant = []
    if failure_memory is not None:
        relevant = [
            {
                "family": r.failure_family,
                "diagnostic": r.diagnostic[:300],
                "attempted_repair": r.attempted_repair[:200],
                "effect": r.effect,
            }
            for r in failure_memory.relevant("", k=3)
        ]
    temp = float(temperatures.get(mode, temperatures.get("default", 0.5)))
    # Breadth sample: higher temp; depth: lower + reasoning_effort.
    if rng.random() < 0.5:
        temp = min(1.0, temp + 0.3)
        effort: str | None = "low"
    else:
        temp = max(0.1, temp - 0.15)
        effort = "high"
    fname = "crossover" if mode == "crossover" else "mutate"
    name, code, err = generate_function(
        backend,
        function_name=fname,
        model=model,
        spec=spec,
        parent_source=parent,
        temperature=temp,
        usage_log=usage_log,
        max_calls=max_calls,
        token_ceiling=token_ceiling,
        reasoning_effort=effort,
        extra_context={
            "prefer_function": target,
            "relevant_failures": relevant,
            "other_parent_solver_py": other_parent[:8000] if other_parent else "",
            "instruction_extra": f"Change preferably ONLY `{target}`.",
        },
    )
    if err or not code.strip():
        return "", ""
    changed = name if name in REQUIRED_FUNCTIONS else target
    if changed not in REQUIRED_FUNCTIONS:
        changed = target
    # Force symbol name if mutate returned wrong def name but body ok.
    if f"def {changed}" not in code and name and f"def {name}" in code:
        changed = name if name in REQUIRED_FUNCTIONS else target
    new_source, apply_err = apply_function_to_solver(parent, changed, code)
    if apply_err or not new_source.strip():
        return "", ""
    return new_source, changed


def _self_debug(
    backend: Any,
    *,
    source: str,
    info: dict[str, Any],
    model: str,
    spec: FormalSpec,
    usage_log: UsageLog,
    max_calls: int,
    token_ceiling: int | None,
    failure_memory: FailureMemory | None,
) -> tuple[str, str]:
    """Error Analyst → Repair → Judge. Returns (source, function_changed)."""
    diagnostic = info.get("diagnostic") or {}
    failure_reason = str(info.get("failure_reason") or "")
    analyst_prompt = (
        load_prompt("error_analyst.md")
        + "\n\nINPUT:\n"
        + json.dumps(
            {
                "failure_reason": failure_reason,
                "category": info.get("category"),
                "diagnostic": diagnostic,
                "spec": spec.model_dump(),
                "solver_py": source[:12000],
            },
            default=str,
        )
    )
    analysis_raw = llm_complete(
        backend,
        prompt=analyst_prompt,
        role="error_analyst",
        model=model,
        temperature=0.2,
        usage_log=usage_log,
        max_calls=max_calls,
        token_ceiling=token_ceiling,
        reasoning_effort="high",
    )
    repair_prompt = (
        load_prompt("repair_coder.md")
        + "\n\nINPUT:\n"
        + json.dumps(
            {
                "analysis": analysis_raw[:4000],
                "failure_reason": failure_reason,
                "diagnostic": diagnostic,
                "prefer_one_function": True,
                "solver_py": source[:12000],
                "memory": (
                    [
                        {"family": r.failure_family, "repair": r.attempted_repair, "effect": r.effect}
                        for r in (failure_memory.relevant(failure_reason, k=3) if failure_memory else [])
                    ]
                ),
            },
            default=str,
        )
    )
    repair_raw = llm_complete(
        backend,
        prompt=repair_prompt,
        role="repair_coder",
        model=model,
        temperature=0.35,
        usage_log=usage_log,
        max_calls=max_calls,
        token_ceiling=token_ceiling,
    )
    from evrptw_autolab.structured.codegen import extract_function_payload

    name, code = extract_function_payload(repair_raw)
    if not code.strip():
        return source, ""
    changed = name if name in REQUIRED_FUNCTIONS else "solve"
    candidate, err = apply_function_to_solver(source, changed, code)
    if err or not candidate.strip():
        return source, ""
    judge_prompt = (
        load_prompt("judge.md")
        + "\n\nINPUT:\n"
        + json.dumps(
            {
                "parent_solver_py": source[:8000],
                "candidate_solver_py": candidate[:8000],
                "analysis": analysis_raw[:2000],
                "failure_reason": failure_reason,
            },
            default=str,
        )
    )
    judge_raw = llm_complete(
        backend,
        prompt=judge_prompt,
        role="judge",
        model=model,
        temperature=0.1,
        usage_log=usage_log,
        max_calls=max_calls,
        token_ceiling=token_ceiling,
    )
    accept = "accept" in judge_raw.lower() or '"decision": "accept"' in judge_raw.lower()
    if "reject" in judge_raw.lower() and "accept" not in judge_raw.lower()[:80]:
        accept = False
    if '"decision": "reject"' in judge_raw.lower():
        accept = False
    if accept:
        return candidate, changed
    return source, ""


def run_structured_synthesis(
    *,
    model: str,
    backend: Any,
    workspace: Path,
    temperatures: dict[str, float] | None = None,
    max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
    token_ceiling: int | None = None,
    max_generations: int = DEFAULT_MAX_GENERATIONS,
    archive_size: int = DEFAULT_ARCHIVE_SIZE,
    offspring_per_generation: int = DEFAULT_OFFSPRING,
    data_root: Path | None = None,
    repo_root: Path | None = None,
    seed: int = 0,
    ablation: str = "full",
    spec: FormalSpec | None = None,
) -> dict[str, Any]:
    """Main Experiment B loop. Final solver.py has zero LLM calls."""
    root = repo_root or ROOT
    temps = dict(temperatures or {})
    temps.setdefault("default", 0.4)
    started = time.monotonic()
    workspace.mkdir(parents=True, exist_ok=True)
    committed_dir = workspace / "committed"
    trial_dir = workspace / "trial"
    usage = UsageLog(workspace / "llm_calls.jsonl")
    if usage.path.exists():
        usage.path.unlink()
    log_path = workspace / "rounds.jsonl"
    if log_path.exists():
        log_path.unlink()

    use_memory = ablation != "no_failure_memory"
    use_population = ablation != "no_population"
    function_by_function = ablation != "no_function_by_function"

    limits = limits_from_config()
    panel = panel_instances(data_root)
    known_ids = known_ids_for_panel(data_root)
    rng = random.Random(int(seed))

    # 1) Immutable architect spec.
    if spec is None:
        frozen = _architect_spec(
            backend,
            model=model,
            usage_log=usage,
            max_calls=max_llm_calls,
            token_ceiling=token_ceiling,
        )
    else:
        frozen = freeze_spec(spec)
    (workspace / "spec.json").write_text(
        json.dumps(frozen.model_dump(), indent=2), encoding="utf-8"
    )

    # 2) Bootstrap construct → repair → improve → solve.
    source, boot_meta = _bootstrap_functions(
        backend=backend,
        model=model,
        spec=frozen,
        workspace=workspace,
        usage_log=usage,
        max_calls=max_llm_calls,
        token_ceiling=token_ceiling,
        rng=rng,
        function_by_function=function_by_function,
        temperatures=temps,
    )
    _write_solver(committed_dir, source)
    _write_solver(trial_dir, source)

    archive = Population(archive_size=archive_size if use_population else 1)
    memory = FailureMemory() if use_memory else None

    info = evaluate_candidate(
        committed_dir,
        stage="schneider_c5",
        limits=limits,
        panel=panel,
        known_ids=known_ids,
        source=source,
    )
    archive.add(source, info, generation=0)
    best_source = source
    best_info = info
    best_fit = fitness_key(info)
    last_failure = str(info.get("failure_reason") or "")
    same_failure_streak = 0
    generations_run = 0
    budget_hit = False

    def budget_left() -> bool:
        n_calls, prompt_t, completion_t = usage_totals(usage)
        if n_calls >= max_llm_calls:
            return False
        if token_ceiling is not None and (prompt_t + completion_t) >= token_ceiling:
            return False
        return True

    # 3) Population search.
    gen_limit = 1 if not use_population else max_generations
    offspring_n = 1 if not use_population else offspring_per_generation

    for gen in range(1, gen_limit + 1):
        if not budget_left():
            budget_hit = True
            break
        generations_run = gen
        parents = archive.select_parents(rng, k=2) if archive.members else []
        if not parents:
            parents_src = [best_source]
        else:
            parents_src = [p.source for p in parents]

        for child_ix in range(offspring_n):
            if not budget_left():
                budget_hit = True
                break
            parent = parents_src[child_ix % len(parents_src)]
            mode = "crossover" if child_ix % 4 == 3 and len(parents_src) > 1 else "mutate"
            other = parents_src[(child_ix + 1) % len(parents_src)] if mode == "crossover" else ""
            try:
                child, changed = _mutate_one(
                    backend,
                    parent=parent,
                    model=model,
                    spec=frozen,
                    usage_log=usage,
                    max_calls=max_llm_calls,
                    token_ceiling=token_ceiling,
                    rng=rng,
                    failure_memory=memory,
                    temperatures=temps,
                    mode=mode,
                    other_parent=other,
                )
            except BudgetExhausted:
                budget_hit = True
                break
            if not child.strip():
                continue
            if code_hash(child) == code_hash(parent):
                continue
            cand_dir = workspace / "candidates" / f"g{gen}_{child_ix}"
            _write_solver(cand_dir, child)
            child_info = evaluate_candidate(
                cand_dir,
                stage="schneider_c5",
                limits=limits,
                panel=panel,
                known_ids=known_ids,
                source=child,
            )
            child_fit = fitness_key(child_info)
            effect: str = "unchanged"
            if child_fit > best_fit:
                effect = "improved"
            elif child_fit < fitness_key(info):
                effect = "regressed"

            if memory is not None:
                memory.add(
                    FailureRecord(
                        code_hash=code_hash(child)[:16],
                        function_changed=changed or "unknown",
                        failure_family=str(
                            (child_info.get("diagnostic") or {}).get("family")
                            or child_info.get("category")
                            or ""
                        ),
                        failed_instance=str(
                            next(
                                (
                                    k
                                    for k, v in (child_info.get("by_instance") or {}).items()
                                    if not v.get("ok")
                                ),
                                "",
                            )
                        ),
                        diagnostic=str(child_info.get("failure_reason") or "")[:500],
                        attempted_repair=f"{mode}:{changed}",
                        effect=effect,  # type: ignore[arg-type]
                    )
                )

            archive.add(child, child_info, generation=gen)
            if child_fit > best_fit:
                best_fit = child_fit
                best_source = child
                best_info = child_info
                _write_solver(committed_dir, best_source)

            # Self-debug trigger: g4==3 or sticky failure.
            g4 = int(child_info.get("instances_feasible") or 0)
            fail_now = str(child_info.get("failure_reason") or "")
            if fail_now and fail_now == last_failure:
                same_failure_streak += 1
            else:
                same_failure_streak = 1 if fail_now else 0
                last_failure = fail_now
            if budget_left() and (g4 == 3 or same_failure_streak >= 3):
                try:
                    repaired, ch = _self_debug(
                        backend,
                        source=best_source,
                        info=best_info,
                        model=model,
                        spec=frozen,
                        usage_log=usage,
                        max_calls=max_llm_calls,
                        token_ceiling=token_ceiling,
                        failure_memory=memory,
                    )
                except BudgetExhausted:
                    budget_hit = True
                    break
                if repaired.strip() and code_hash(repaired) != code_hash(best_source):
                    _write_solver(trial_dir, repaired)
                    rinfo = evaluate_candidate(
                        trial_dir,
                        stage="schneider_c5",
                        limits=limits,
                        panel=panel,
                        known_ids=known_ids,
                        source=repaired,
                    )
                    if fitness_key(rinfo) >= best_fit:
                        best_source = repaired
                        best_info = rinfo
                        best_fit = fitness_key(rinfo)
                        _write_solver(committed_dir, best_source)
                        archive.add(repaired, rinfo, generation=gen)
                        same_failure_streak = 0

        n_calls, prompt_tokens, completion_tokens = usage_totals(usage)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "generation": gen,
                        "archive": len(archive),
                        "best_fitness": list(best_fit),
                        "g4": int(best_info.get("instances_feasible") or 0),
                        "gates_passed": int(best_info.get("gates_passed") or 0),
                        "calls": n_calls,
                        "tokens": prompt_tokens + completion_tokens,
                        "ablation": ablation,
                    }
                )
                + "\n"
            )
        if budget_hit or not budget_left():
            budget_hit = True
            break
        if bool(best_info.get("ok")) and int(best_info.get("gates_passed") or 0) >= 5:
            break

    _write_solver(committed_dir, best_source)
    gates_passed = int(best_info.get("gates_passed") or 0)
    passed = {
        "executable": gates_passed >= 1,
        "routing": gates_passed >= 2,
        "charging": gates_passed >= 3,
        "multi_customer": gates_passed >= 4,
        "schneider_c5": bool(best_info.get("ok")) and gates_passed >= 5,
    }
    g4_passed = bool(passed["schneider_c5"])
    n_calls, prompt_tokens, completion_tokens = usage_totals(usage)
    tokens = prompt_tokens + completion_tokens
    category = classify_category(
        g4_passed=g4_passed,
        category=str(best_info.get("category") or ""),
        budget=budget_hit or (not g4_passed and n_calls >= max_llm_calls),
    )
    deepest = ""
    for name in ("executable", "routing", "charging", "multi_customer", "schneider_c5"):
        if passed[name]:
            deepest = name
        else:
            break
    report: dict[str, Any] = {
        "experiment": "structured_synthesis",
        "ablation": ablation,
        "model": model,
        "seed": seed,
        "executable": passed["executable"],
        "routing": passed["routing"],
        "charging": passed["charging"],
        "multi_customer": passed["multi_customer"],
        "schneider_c5": passed["schneider_c5"],
        "deepest_gate": deepest,
        "g4_feasible": int(best_info.get("instances_feasible") or 0),
        "g4_total": len(panel),
        "best_g4_feasible": int(best_info.get("instances_feasible") or 0),
        "curriculum_g4_best": int(best_info.get("instances_feasible") or 0),
        "posthoc_g4_score": int(best_info.get("instances_feasible") or 0),
        "llm_calls": n_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "tokens": tokens,
        "token_ceiling": token_ceiling,
        "failure_reason": "" if g4_passed else str(best_info.get("failure_reason") or ""),
        "failure_category": category,
        "feasible": int(best_info.get("instances_feasible") or 0),
        "c5_total": len(panel),
        "fully_feasible": g4_passed,
        "vehicles": best_info.get("vehicles") if g4_passed else None,
        "distance": best_info.get("distance") if g4_passed else None,
        "solver_hash": code_hash(best_source)[:16] if best_source.strip() else "",
        "wall_s": round(time.monotonic() - started, 1),
        "generations": generations_run,
        "archive_size": len(archive),
        "bootstrap": boot_meta,
        "spec_valid": not validate_spec(frozen),
        "solver_path": _relative(committed_dir / "solver.py", root),
        "fitness": list(best_fit),
    }
    report = stamp_report(report, root)
    (workspace / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def copy_structured_provenance(workspace: Path, dest: Path, report: dict[str, Any]) -> None:
    """Copy result artifacts under results/structured/raw/ (never paper/)."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    for name in ("rounds.jsonl", "llm_calls.jsonl", "spec.json"):
        source = workspace / name
        if source.exists():
            shutil.copyfile(source, dest / name)
    solver = workspace / "committed" / "solver.py"
    if solver.exists() and solver.read_text(encoding="utf-8").strip():
        shutil.copyfile(solver, dest / "solver.py")
