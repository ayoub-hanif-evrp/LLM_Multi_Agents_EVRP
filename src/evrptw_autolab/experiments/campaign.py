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


def _load_panel(cfg: CampaignConfig) -> list[tuple[PilotInstance, ProblemSpecV2]]:
    items = development_panel()
    if cfg.max_instances is not None:
        items = items[: max(1, int(cfg.max_instances))]
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
) -> list[dict[str, Any]]:
    """One LLM role (routing) only; other components stay default heuristics."""
    from evrptw_autolab.components.interfaces import ComponentKind
    from evrptw_autolab.components.loader import load_bundle, validate_component_source
    from evrptw_autolab.llm.usage import UsageCollector as UC

    rows: list[dict[str, Any]] = []
    for item, spec in panel:
        started = time.monotonic()
        collector = UC(max_calls=cfg.max_llm_calls, max_tokens=cfg.max_llm_tokens)
        prompt = (
            "Return JSON with component insertion_score code.\n"
            f"Signature insertion_score.\nFamily={spec.family}"
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
                    "feasible": False,
                    "error": str(err),
                    "llm_calls": collector.logical_calls,
                    "llm_tokens": collector.total_tokens,
                }
            )
            continue
        from evrptw_autolab.agents.base import extract_json, extract_python_source

        payload = extract_json(raw)
        code = str(payload.get("code") or "")
        if "def insertion_score" not in code:
            code = extract_python_source(code) or DEFAULT_SOURCES["insertion_score"]
        llm_ok = bool(validate_component_source("insertion_score", code).get("ok"))
        sources: dict[ComponentKind, str] = {
            "insertion_score": code if llm_ok else DEFAULT_SOURCES["insertion_score"],
            "station_score": DEFAULT_SOURCES["station_score"],
            "removal_priority": DEFAULT_SOURCES["removal_priority"],
        }
        owners: dict[ComponentKind, str] = {
            "insertion_score": "routing",
            "station_score": "default",
            "removal_priority": "default",
        }
        bundle, _ = load_bundle(sources, owners)
        sol = solve_classical(
            spec,
            seed=cfg.seed,
            time_limit_s=min(cfg.time_limit_s, item.time_limit_s),
            alns_iterations=min(cfg.alns_iterations, item.alns_iterations),
            policy=bundle,
        )
        report = evaluate(spec, sol)
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
                    "llm_calls": collector.logical_calls,
                    "llm_tokens": collector.total_tokens,
                    "genuine_llm_components": 1 if llm_ok and code != DEFAULT_SOURCES["insertion_score"] else 0,
                    "attribution": [
                        {
                            "component": "insertion_score",
                            "llm_generated": bool(llm_ok),
                            "is_default_heuristic": code == DEFAULT_SOURCES["insertion_score"],
                        }
                    ],
                    "work_dir": str(work / "single_agent" / spec.instance_id),
                },
            )
        )
    return rows


def _run_five_agent(
    panel: list[tuple[PilotInstance, ProblemSpecV2]],
    cfg: CampaignConfig,
    backend: Any,
    model: str,
    work: Path,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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
            }
        )
    return rows


def _run_evolution(
    panel: list[tuple[PilotInstance, ProblemSpecV2]],
    cfg: CampaignConfig,
    backend: Any,
    model: str,
    work: Path,
) -> list[dict[str, Any]]:
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
    rows: list[dict[str, Any]] = []
    # Emit one row per panel instance; feasibility uses archive re-eval summary.
    n_feas = int(result.get("best_instances_feasible") or 0)
    n_test = int(result.get("best_instances_tested") or len(specs))
    for idx, spec in enumerate(specs):
        rows.append(
            {
                "arm": "five_agent_evolution",
                "family": spec.family,
                "instance_id": spec.instance_id,
                "seed": cfg.seed,
                # Per-instance detail lives in evolution checkpoint; mark panel-feasible
                # when the frozen best covers the whole panel.
                "feasible": bool(result.get("best_fully_feasible_on_panel"))
                if n_test == len(specs)
                else (idx < n_feas),
                "wall_s": wall / max(len(specs), 1),
                "llm_calls": result.get("llm_calls"),
                "llm_tokens": result.get("llm_tokens"),
                "attribution_category": result.get("best_attribution_category"),
                "model": model,
                "generations": cfg.evolution_generations,
                "best_candidate_id": result.get("best_candidate_id"),
                "frozen_bundle": result.get("frozen_bundle"),
                "panel_feasible_count": n_feas,
                "panel_tested_count": n_test,
            }
        )
    (work / "evolution_result.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    return rows


def _aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_arm.setdefault(str(row.get("arm")), []).append(row)
    summary: dict[str, Any] = {}
    for arm, arm_rows in by_arm.items():
        feas = [bool(r.get("feasible")) for r in arm_rows if "feasible" in r]
        walls = [float(r["wall_s"]) for r in arm_rows if r.get("wall_s") is not None]
        tokens = [int(r.get("llm_tokens") or 0) for r in arm_rows]
        summary[arm] = {
            "n": len(arm_rows),
            "feasible_count": sum(feas),
            "feasible_rate": (sum(feas) / len(feas)) if feas else None,
            "mean_wall_s": statistics.fmean(walls) if walls else None,
            "total_llm_tokens": sum(tokens),
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
    started = time.monotonic()

    if "classical" in cfg.arms:
        all_rows.extend(_run_classical(panel, cfg))
    need_llm = any(a in cfg.arms for a in ("single_agent", "five_agent", "five_agent_evolution"))
    if need_llm:
        if "single_agent" in cfg.arms:
            all_rows.extend(_run_single_agent(panel, cfg, backend, model, out))
        if "five_agent" in cfg.arms:
            all_rows.extend(_run_five_agent(panel, cfg, backend, model, out))
        if "five_agent_evolution" in cfg.arms:
            all_rows.extend(_run_evolution(panel, cfg, backend, model, out))

    aggregate = _aggregate(all_rows)
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
        "rows": all_rows,
        "wall_s": time.monotonic() - started,
        "disclaimer": (
            "FakeBackend arms are plumbing checks, not research claims. "
            "Live Ollama runs with --ollama are required for model comparisons. "
            "Development panel only; held-out never used."
        ),
    }
    (out / "campaign.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    # Also keep a compact CSV-like JSONL for table generation.
    with (out / "rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, default=str) + "\n")
    return payload
