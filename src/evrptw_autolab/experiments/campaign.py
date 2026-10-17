"""Matched classical / single-agent / five-agent / evolution campaign.

This is the paper-facing experiment entry point. It does not invent results:
every arm writes raw rows with feasibility, objective_key, attribution, tokens,
and wall time. Held-out instances are never loaded here.
"""
from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.baselines.classical_pilot import PilotInstance, development_panel
from evrptw_autolab.components.evolution import EvolutionConfig, run_evolution
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.components.run import synthesize_components
from evrptw_autolab.problem.v2.types import ProblemSpecV2

ROOT = Path(__file__).resolve().parents[3]

ArmName = Literal["classical", "single_agent", "five_agent", "five_agent_evolution"]


@dataclass
class CampaignConfig:
    """Bounded, matched-budget research campaign on the development panel."""

    seed: int = 7
    profile: str = "qwen3_coder_30b"
    fake: bool = True
    arms: list[ArmName] = field(
        default_factory=lambda: [
            "classical",
            "single_agent",
            "five_agent",
            "five_agent_evolution",
        ]
    )
    # Cap panel size for cheap smoke; None = full development panel.
    max_instances: int | None = 3
    time_limit_s: float = 5.0
    alns_iterations: int = 40
    evolution_generations: int = 2
    max_llm_calls: int = 24
    max_llm_tokens: int | None = 80_000
    max_wall_s: float | None = 600.0
    out_dir: Path | None = None


def _select_panel_items(cfg: CampaignConfig) -> list[PilotInstance]:
    """Prefer one instance per family when capping, for fair multi-variant coverage."""
    items = development_panel()
    if cfg.max_instances is None:
        return items
    cap = max(1, int(cfg.max_instances))
    if cap >= len(items):
        return items
    # Round-robin across families so a 5-cap is not Schneider-only.
    by_family: dict[str, list[PilotInstance]] = {}
    for item in items:
        by_family.setdefault(item.family, []).append(item)
    selected: list[PilotInstance] = []
    families = list(by_family.keys())
    idx = 0
    while len(selected) < cap:
        progressed = False
        for fam in families:
            bucket = by_family[fam]
            if idx < len(bucket):
                selected.append(bucket[idx])
                progressed = True
                if len(selected) >= cap:
                    break
        if not progressed:
            break
        idx += 1
    return selected


def _load_panel(cfg: CampaignConfig) -> list[tuple[PilotInstance, ProblemSpecV2]]:
    items = _select_panel_items(cfg)
    out: list[tuple[PilotInstance, ProblemSpecV2]] = []
    for item in items:
        out.append((item, item.loader(item.path)))
    return out


def _make_backend(cfg: CampaignConfig) -> tuple[Any, str]:
    if cfg.fake:
        from evrptw_autolab.llm.registry import FakeBackend

        backend = FakeBackend(
            {
                "architect": json.dumps(
                    {
                        "summary": "campaign",
                        "components": ["insertion_score", "station_score", "removal_priority"],
                        "risks": [],
                        "success_criteria": ["feasible"],
                        "variant_notes": "dev-panel",
                    }
                ),
                "routing": json.dumps(
                    {
                        "component": "insertion_score",
                        "owner_role": "routing",
                        "code": DEFAULT_SOURCES["insertion_score"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "charging": json.dumps(
                    {
                        "component": "station_score",
                        "owner_role": "charging",
                        "code": DEFAULT_SOURCES["station_score"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "search": json.dumps(
                    {
                        "component": "removal_priority",
                        "owner_role": "search",
                        "code": DEFAULT_SOURCES["removal_priority"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "critic": json.dumps(
                    {
                        "verdict": "ACCEPT",
                        "reason": "campaign-fake",
                        "next_component": "none",
                        "diagnosis": "objective_stagnation",
                    }
                ),
            }
        )
        return backend, "fake"
    from evrptw_autolab.llm.ollama import OllamaBackend
    from evrptw_autolab.llm.registry import availability, make_backend, resolve_profile

    ollama = OllamaBackend()
    prof = resolve_profile(cfg.profile)
    status = availability(prof, ollama)
    if status != "installed":
        raise RuntimeError(f"profile {cfg.profile} status={status}; cannot run live campaign")
    return make_backend(prof, ollama_host=ollama.host), prof.model


def _row_from_solution(
    *,
    arm: str,
    family: str,
    instance_id: str,
    seed: int,
    solution: Any,
    report: Any,
    wall_s: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "arm": arm,
        "family": family,
        "instance_id": instance_id,
        "seed": seed,
        "feasible": bool(report.feasible),
        "solution_feasible": bool(report.feasible),
        "completed_within_budget": solution.metadata.get("completed_within_budget"),
        "hard_timeout_triggered": bool(solution.metadata.get("hard_timeout_triggered")),
        "worker_terminated": bool(solution.metadata.get("worker_terminated")),
        "incumbent_available": solution.metadata.get("incumbent_available"),
        "parent_validated": bool(solution.metadata.get("parent_validated")),
        "objective": report.objective,
        "objective_key": list(report.objective_key),
        "vehicles": report.vehicles,
        "distance": report.total_distance,
        "duration": report.total_duration,
        "runtime_s": float(solution.metadata.get("runtime_s", wall_s)),
        "wall_s": wall_s,
        "deadline_exceeded": bool(solution.metadata.get("deadline_exceeded")),
        "solver_time_limit_s": solution.metadata.get("time_limit_s"),
        "first_fault": (
            f"{report.first_fault.family}: {report.first_fault.detail}"
            if report.first_fault
            else ""
        ),
        "llm_calls": 0,
        "llm_tokens": 0,
        "genuine_llm_components": 0,
        "attribution": [],
    }
    if extra:
        row.update(extra)
    return row


def _run_classical(
    panel: list[tuple[PilotInstance, ProblemSpecV2]],
    cfg: CampaignConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item, spec in panel:
        started = time.monotonic()
        sol = solve_classical(
            spec,
            seed=cfg.seed,
            time_limit_s=min(cfg.time_limit_s, item.time_limit_s),
            alns_iterations=min(cfg.alns_iterations, item.alns_iterations),
        )
        report = evaluate(spec, sol)
        rows.append(
            _row_from_solution(
                arm="classical",
                family=spec.family,
                instance_id=spec.instance_id,
                seed=cfg.seed,
                solution=sol,
                report=report,
                wall_s=time.monotonic() - started,
                extra={"source": "human_backbone", "model": "none"},
            )
        )
    return rows


def _run_single_agent(
    panel: list[tuple[PilotInstance, ProblemSpecV2]],
    cfg: CampaignConfig,
    backend: Any,
    model: str,
    work: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One model, one unified call, same three component slots as the five-agent arm."""
    from evrptw_autolab.agents.base import extract_json
    from evrptw_autolab.components.expressions import materialize_component, repair_prompt
    from evrptw_autolab.components.interfaces import ComponentKind
    from evrptw_autolab.components.loader import load_bundle, validate_component_source
    from evrptw_autolab.llm.usage import UsageCollector as UC

    kinds: tuple[ComponentKind, ...] = ("insertion_score", "station_score", "removal_priority")
    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for item, spec in panel:
        started = time.monotonic()
        collector = UC(max_calls=cfg.max_llm_calls, max_tokens=cfg.max_llm_tokens)
        prompt = (
            "You are one unified heuristic designer. Return JSON with an arithmetic "
            "expression for each component: insertion_score, station_score, removal_priority. "
            "No function definitions. "
            f"Family={spec.family}. "
            '{"components":[{"component":"insertion_score","expression":"delta_distance"},'
            '{"component":"station_score","expression":"detour"},'
            '{"component":"removal_priority","expression":"due_time"}]}'
        )
        try:
            raw = collector.complete(
                backend, prompt=prompt, role="routing", temperature=0.2, model=model, json_mode=True
            )
        except Exception as err:  # noqa: BLE001
            rows.append(
                {
                    "arm": "single_agent",
                    "family": spec.family,
                    "instance_id": spec.instance_id,
                    "seed": cfg.seed,
                    "status": "LLM_ERROR",
                    "feasible": None,
                    "error": str(err),
                }
            )
            continue
        payload = extract_json(raw)
        by_kind: dict[str, dict[str, Any]] = {}
        listed = payload.get("components")
        if isinstance(listed, list):
            for entry in listed:
                if isinstance(entry, dict) and entry.get("component"):
                    by_kind[str(entry["component"])] = entry
        elif payload.get("component"):
            by_kind[str(payload["component"])] = payload
        sources: dict[ComponentKind, str] = {}
        owners: dict[ComponentKind, str] = {}
        attribution: list[dict[str, Any]] = []
        for kind in kinds:
            piece = by_kind.get(kind, {})
            code, status = materialize_component(kind, piece)
            ok = bool(code) and bool(validate_component_source(kind, code).get("ok"))
            if not ok:
                repair_raw = collector.complete(
                    backend,
                    prompt=repair_prompt(kind, status),
                    role="routing",
                    temperature=0.0,
                    model=model,
                    json_mode=True,
                )
                repaired = extract_json(repair_raw)
                code, status = materialize_component(kind, repaired)
                ok = bool(code) and bool(validate_component_source(kind, code).get("ok"))
            used_default = not ok or code.strip() == DEFAULT_SOURCES[kind].strip()
            if not ok:
                code = DEFAULT_SOURCES[kind]
            sources[kind] = code
            owners[kind] = "unified" if not used_default else "default"
            attribution.append(
                {
                    "component": kind,
                    "status": status if ok else f"fallback:{status}",
                    "llm_generated": not used_default,
                    "is_default_heuristic": code.strip() == DEFAULT_SOURCES[kind].strip(),
                    "source": code,
                }
            )
        bundle, _ = load_bundle(sources, owners)
        sol = solve_classical(
            spec,
            seed=cfg.seed,
            time_limit_s=min(cfg.time_limit_s, item.time_limit_s),
            alns_iterations=min(cfg.alns_iterations, item.alns_iterations),
            policy=bundle,
        )
        report = evaluate(spec, sol)
        genuine = sum(1 for a in attribution if a["llm_generated"])
        rows.append(
            _row_from_solution(
                arm="single_agent",
                family=spec.family,
                instance_id=spec.instance_id,
                seed=cfg.seed,
                solution=sol,
                report=report,
                wall_s=time.monotonic() - started,
                extra={
                    "model": model,
                    "genuine_llm_components": genuine,
                    "attribution": attribution,
                    "component_slots": list(kinds),
                    "work_dir": str(work / "single_agent" / spec.instance_id),
                    "scorer_calls": dict(sol.metadata.get("scorer_calls") or {}),
                },
            )
        )
        runs.append(
            {
                "arm": "single_agent",
                "instance_id": spec.instance_id,
                "model": model,
                "seed": cfg.seed,
                "llm_calls": collector.logical_calls,
                "llm_tokens": collector.total_tokens,
                "usage_scope": "instance",
            }
        )
    return rows, runs


def _run_five_agent(
    panel: list[tuple[PilotInstance, ProblemSpecV2]],
    cfg: CampaignConfig,
    backend: Any,
    model: str,
    work: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    for item, spec in panel:
        out = work / "five_agent" / spec.instance_id
        result = synthesize_components(
            spec,
            backend,
            model=model,
            seed=cfg.seed,
            time_limit_s=min(cfg.time_limit_s, item.time_limit_s),
            work_dir=out,
        )
        rows.append(
            {
                "arm": "five_agent",
                "family": spec.family,
                "instance_id": spec.instance_id,
                "seed": cfg.seed,
                "feasible": result.get("feasible"),
                "objective": result.get("objective"),
                "objective_key": result.get("objective_key"),
                "vehicles": result.get("vehicles"),
                "distance": result.get("distance"),
                "wall_s": result.get("wall_s"),
                "llm_calls": result.get("llm_calls"),
                "llm_tokens": result.get("llm_tokens"),
                "genuine_llm_components": result.get("genuine_llm_components"),
                "attribution": result.get("component_attribution") or result.get("attribution"),
                "model": model,
                "critic_verdict": result.get("critic_verdict"),
                "solution_feasible": result.get("solution_feasible"),
                "completed_within_budget": result.get("completed_within_budget"),
                "hard_timeout_triggered": result.get("hard_timeout_triggered"),
                "worker_terminated": result.get("worker_terminated"),
                "incumbent_available": result.get("incumbent_available"),
                "parent_validated": result.get("parent_validated"),
                "return_status": result.get("return_status"),
                "first_fault": (
                    f"{result.get('fault_family')}: {result.get('detail')}"
                    if result.get("fault_family")
                    else ""
                ),
                "scorer_calls": result.get("scorer_calls") or {},
            }
        )
        runs.append(
            {
                "arm": "five_agent",
                "instance_id": spec.instance_id,
                "model": model,
                "seed": cfg.seed,
                "llm_calls": result.get("llm_calls"),
                "llm_tokens": result.get("llm_tokens"),
                "usage_scope": "instance",
            }
        )
    return rows, runs


def _evolution_instance_rows(
    result: dict[str, Any],
    specs: list[ProblemSpecV2],
    *,
    seed: int,
    model: str,
) -> list[dict[str, Any]]:
    """One row per frozen evaluation. Never copy run-level tokens onto each row."""
    panel = result.get("best_panel") or {}
    recorded = {
        (str(row.get("family")), str(row.get("instance_id")), int(row.get("seed") or seed)): row
        for row in (panel.get("per_instance") or [])
        if isinstance(row, dict)
    }
    attribution = str(result.get("best_attribution_category") or "")
    genuine = int(result.get("best_genuine_llm_components") or 0)
    winner = "NO_LLM_WINNER" if genuine <= 0 or attribution == "pure_classical" else "LLM_CANDIDATE"
    rows: list[dict[str, Any]] = []
    for spec in specs:
        key = (spec.family, spec.instance_id, int(seed))
        src = recorded.get(key)
        if src is None:
            rows.append(
                {
                    "arm": "five_agent_evolution",
                    "family": spec.family,
                    "instance_id": spec.instance_id,
                    "seed": seed,
                    "status": "NOT_EVALUATED",
                    "feasible": None,
                    "winner_status": winner,
                    "best_candidate_id": result.get("best_candidate_id"),
                    "model": model,
                }
            )
            continue
        rows.append(
            {
                "arm": "five_agent_evolution",
                "family": src.get("family"),
                "instance_id": src.get("instance_id"),
                "seed": src.get("seed"),
                "status": "EVALUATED",
                "feasible": src.get("feasible"),
                "objective": (src.get("objective_key") or [None])[0],
                "objective_key": src.get("objective_key"),
                "vehicles": src.get("vehicles"),
                "distance": src.get("distance"),
                "duration": src.get("duration"),
                "runtime_s": src.get("runtime_s"),
                "fault_family": src.get("fault_family"),
                "winner_status": winner,
                "attribution_category": attribution,
                "best_candidate_id": result.get("best_candidate_id"),
                "model": model,
            }
        )
    return rows


def _run_evolution(
    panel: list[tuple[PilotInstance, ProblemSpecV2]],
    cfg: CampaignConfig,
    backend: Any,
    model: str,
    work: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    specs = [spec for _, spec in panel]
    evo_cfg = EvolutionConfig(
        generations=cfg.evolution_generations,
        seed=cfg.seed,
        time_limit_s=cfg.time_limit_s,
        alns_iterations=cfg.alns_iterations,
        model=model,
        use_critic=True,
        use_cross_variant_memory=True,
        max_llm_calls=cfg.max_llm_calls,
        max_llm_tokens=cfg.max_llm_tokens,
        max_wall_s=cfg.max_wall_s,
        panel_seeds=[cfg.seed],
        work_dir=work / "evolution",
    )
    started = time.monotonic()
    result = run_evolution(specs, backend, evo_cfg)
    wall = time.monotonic() - started
    rows = _evolution_instance_rows(result, specs, seed=cfg.seed, model=model)
    runs = [
        {
            "arm": "five_agent_evolution",
            "model": model,
            "seed": cfg.seed,
            "llm_calls": result.get("llm_calls"),
            "llm_tokens": result.get("llm_tokens"),
            "http_attempts": result.get("http_attempts"),
            "development_wall_s": wall,
            "usage_scope": "run",
            "best_candidate_id": result.get("best_candidate_id"),
            "attribution_category": result.get("best_attribution_category"),
        }
    ]
    (work / "evolution_result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return rows, runs


def _aggregate(rows: list[dict[str, Any]], runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(str(row.get("arm")), []).append(row)
    tokens_by_arm: dict[str, int] = {}
    for run in runs:
        arm = str(run.get("arm"))
        tokens_by_arm[arm] = tokens_by_arm.get(arm, 0) + int(run.get("llm_tokens") or 0)
    summary: dict[str, Any] = {}
    for arm, arm_rows in by_arm.items():
        feas = [bool(r.get("feasible")) for r in arm_rows if r.get("feasible") is not None]
        walls = [float(r["wall_s"]) for r in arm_rows if r.get("wall_s") is not None]
        summary[arm] = {
            "n": len(arm_rows),
            "feasible_count": sum(feas),
            "feasible_rate": (sum(feas) / len(feas)) if feas else None,
            "mean_wall_s": statistics.fmean(walls) if walls else None,
            "total_llm_tokens": tokens_by_arm.get(arm, 0),
            "token_accounting": "run_level_not_summed_across_instances",
        }
    return summary


def run_research_campaign(cfg: CampaignConfig | None = None) -> dict[str, Any]:
    """Execute matched arms and write results under results/v2/campaigns/."""
    cfg = cfg or CampaignConfig()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = cfg.out_dir or (ROOT / "results" / "v2" / "campaigns" / f"campaign_{stamp}")
    out.mkdir(parents=True, exist_ok=True)
    panel = _load_panel(cfg)
    backend, model = _make_backend(cfg)
    all_rows: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    started = time.monotonic()

    if "classical" in cfg.arms:
        all_rows.extend(_run_classical(panel, cfg))
        runs.append(
            {
                "arm": "classical",
                "model": "none",
                "seed": cfg.seed,
                "llm_calls": 0,
                "llm_tokens": 0,
                "usage_scope": "run",
            }
        )
    need_llm = any(a in cfg.arms for a in ("single_agent", "five_agent", "five_agent_evolution"))
    if need_llm:
        if "single_agent" in cfg.arms:
            inst_rows, inst_runs = _run_single_agent(panel, cfg, backend, model, out)
            all_rows.extend(inst_rows)
            runs.extend(inst_runs)
        if "five_agent" in cfg.arms:
            inst_rows, inst_runs = _run_five_agent(panel, cfg, backend, model, out)
            all_rows.extend(inst_rows)
            runs.extend(inst_runs)
        if "five_agent_evolution" in cfg.arms:
            inst_rows, inst_runs = _run_evolution(panel, cfg, backend, model, out)
            all_rows.extend(inst_rows)
            runs.extend(inst_runs)

    aggregate = _aggregate(all_rows, runs)
    payload = {
        "experiment": "voltforge_research_campaign",
        "created_utc": stamp,
        "out_dir": str(out),
        "config": {
            **{k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(cfg).items()},
            "model": model,
            "panel": [
                {"family": spec.family, "instance_id": spec.instance_id} for _, spec in panel
            ],
        },
        "aggregate": aggregate,
        "runs": runs,
        "rows": all_rows,
        "wall_s": time.monotonic() - started,
        "disclaimer": (
            (
                "FakeBackend arms are plumbing checks, not research claims. "
                "Use --ollama for live open-weight comparisons. "
            )
            if cfg.fake
            else (
                "Live Ollama campaign. Report only measured rows; "
                "fallback/default heuristics are not LLM discoveries. "
            )
        )
        + "Development panel only; held-out never used.",
    }
    (out / "campaign.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    with (out / "rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, default=str) + "\n")
    with (out / "runs.jsonl").open("w", encoding="utf-8") as handle:
        for run in runs:
            handle.write(json.dumps(run, default=str) + "\n")
    with (out / "instance_results.jsonl").open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, default=str) + "\n")
    return payload
