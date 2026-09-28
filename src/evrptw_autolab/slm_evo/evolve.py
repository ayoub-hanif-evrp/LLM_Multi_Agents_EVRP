"""SLM-Evo generation loop: parallel patches, beam, experimental repair."""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.slm_evo.evaluate import (
    all_c5_instances,
    evaluate_panel,
    experimental_battery_or_window,
    known_ids_for_panel,
    lex_better_panel,
    milestone_instances,
    panel_instances,
    source_hash,
    validate_source,
    vehicle_reduction_on_any,
    write_solver,
)
from evrptw_autolab.slm_evo.freeze import assert_not_immutable, freeze_dir_for
from evrptw_autolab.slm_evo.patch_apply import apply_proposal
from evrptw_autolab.slm_evo.propose import (
    build_patch_agents,
    focus_for_generation,
    proposal_seed,
    propose_charging_repair,
    propose_generation,
)
from evrptw_autolab.slm_evo.types import (
    CandidateRecord,
    GenerationReport,
    PanelMetrics,
    PatchProposal,
)


@dataclass
class EvoState:
    best_source: str
    best_metrics: PanelMetrics
    beam: list[tuple[str, PanelMetrics]] = field(default_factory=list)
    generations: list[GenerationReport] = field(default_factory=list)
    milestone_hit: bool = False
    milestone_instance: str = ""
    llm_calls: int = 0
    trajectory: list[dict[str, Any]] = field(default_factory=list)
    best_all_c5: PanelMetrics | None = None


def _usage_count(usage: UsageLog) -> int:
    if not usage.path.exists():
        return 0
    return sum(1 for line in usage.path.read_text(encoding="utf-8").splitlines() if line.strip())


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _rank_key(m: PanelMetrics) -> tuple[int, int, int, float]:
    infeas = 0 if m.fully_feasible else 1
    return (infeas, m.vehicles_sum if m.fully_feasible else 10**9, -m.feasible, m.distance_sum)


def _process_candidate(
    *,
    proposal: PatchProposal,
    parent_source: str,
    parent_metrics: PanelMetrics,
    parent_hash: str,
    focus: str,
    candidate_id: str,
    workspace: Path,
    probe: Any,
    known_ids: set[str],
    panel: list[Any],
    limits: RunLimits,
    agents: dict[str, Any],
    backend: Any,
    generation: int,
    seed_base: int,
    allow_experimental_repair: bool,
) -> CandidateRecord:
    rec = CandidateRecord(
        candidate_id=candidate_id,
        parent_hash=parent_hash,
        role=proposal.role,
        focus=focus,
        hypothesis=proposal.hypothesis,
        ops=[op.as_dict() for op in proposal.ops],
    )
    if not proposal.ops:
        rec.apply_ok = False
        rec.apply_error = "empty ops / propose failed"
        rec.reject_reason = "empty_ops"
        return rec

    applied = apply_proposal(parent_source, proposal)
    if not applied.ok:
        rec.apply_ok = False
        rec.apply_error = applied.error
        rec.reject_reason = "apply_failed"
        return rec

    ok, reason = validate_source(applied.source, probe=probe, known_ids=known_ids, limits=limits)
    if not ok:
        rec.apply_ok = False
        rec.apply_error = reason
        rec.reject_reason = "validate_failed"
        return rec

    rec.apply_ok = True
    rec.source_hash = source_hash(applied.source)
    cand_dir = workspace / "candidates" / candidate_id
    if cand_dir.exists():
        shutil.rmtree(cand_dir, ignore_errors=True)
    write_solver(cand_dir, applied.source)
    rec.path = str(cand_dir / "solver.py")

    metrics, _ = evaluate_panel(cand_dir, panel, limits=limits)
    rec.metrics = metrics

    if metrics.fully_feasible and lex_better_panel(parent_metrics, metrics):
        rec.accepted = True
        return rec

    if (
        allow_experimental_repair
        and not metrics.fully_feasible
        and experimental_battery_or_window(metrics)
        and vehicle_reduction_on_any(parent_metrics, metrics)
    ):
        rec.experimental = True
        repair_seed = proposal_seed(seed_base, generation, 99, 77)
        repair = propose_charging_repair(
            agents["charging"],
            backend=backend,
            current_source=applied.source,
            fault_detail=metrics.primary_fault,
            seed=repair_seed,
        )
        if repair and repair.ops:
            repaired = apply_proposal(applied.source, repair)
            if repaired.ok:
                rok, rreason = validate_source(
                    repaired.source, probe=probe, known_ids=known_ids, limits=limits
                )
                if rok:
                    repair_dir = workspace / "candidates" / f"{candidate_id}_repair"
                    if repair_dir.exists():
                        shutil.rmtree(repair_dir, ignore_errors=True)
                    write_solver(repair_dir, repaired.source)
                    rmetrics, _ = evaluate_panel(repair_dir, panel, limits=limits)
                    rec.repaired = True
                    rec.metrics = rmetrics
                    rec.source_hash = source_hash(repaired.source)
                    rec.path = str(repair_dir / "solver.py")
                    rec.ops = rec.ops + [op.as_dict() for op in repair.ops]
                    if rmetrics.fully_feasible and lex_better_panel(parent_metrics, rmetrics):
                        rec.accepted = True
                        rec.reject_reason = ""
                        return rec
                    rec.reject_reason = "repair_not_better"
                    return rec
                rec.reject_reason = f"repair_validate:{rreason}"[:200]
                return rec
        rec.reject_reason = "experimental_no_repair"
        return rec

    if metrics.fully_feasible:
        rec.reject_reason = "feasible_not_better"
    else:
        rec.reject_reason = f"infeasible:{metrics.primary_fault}"[:200]
    return rec


def _write_freeze(
    *,
    dest: Path,
    source: str,
    parent_solver: Path,
    panel: PanelMetrics,
    all_c5: PanelMetrics,
    milestone_instance: str,
    generations: int,
    seed_base: int | None,
    campaign_id: str,
    trajectory: list[dict[str, Any]],
) -> Path:
    assert_not_immutable(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "solver.py").write_text(source, encoding="utf-8")
    (dest / "meta.json").write_text(
        json.dumps(
            {
                "parent": str(parent_solver),
                "best_hash": source_hash(source),
                "panel": panel.as_dict(),
                "all_c5": all_c5.as_dict(),
                "milestone_instance": milestone_instance,
                "generations": generations,
                "seed_base": seed_base,
                "campaign_id": campaign_id,
                "trajectory": trajectory,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dest


def run_slm_evo(
    *,
    model: str,
    backend: Any,
    workspace: Path,
    parent_solver: Path,
    max_generations: int = 20,
    candidates_per_role: int = 2,
    beam_size: int = 2,
    max_llm_calls: int = 400,
    data_root: Path | None = None,
    seed_base: int = 0,
    stop_on_milestone: bool = False,
    campaign_id: str = "",
    continuation: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    workspace.mkdir(parents=True, exist_ok=True)
    usage = UsageLog(workspace / "llm_calls.jsonl")
    log_path = workspace / "generations.jsonl"
    if log_path.exists():
        log_path.unlink()

    parent_source = parent_solver.read_text(encoding="utf-8")
    panel = panel_instances(data_root)
    if not panel:
        raise RuntimeError("empty SLM-Evo panel")
    known_ids = known_ids_for_panel(data_root)
    limits = RunLimits(wall_clock_s=20.0)
    probe = panel[0]
    c5 = all_c5_instances(data_root)

    best_dir = workspace / "best"
    write_solver(best_dir, parent_source)
    best_metrics, _ = evaluate_panel(best_dir, panel, limits=limits)
    if not best_metrics.fully_feasible:
        raise RuntimeError(f"parent not panel-feasible: {best_metrics.primary_fault}")
    parent_c5, _ = evaluate_panel(best_dir, c5, limits=limits)

    state = EvoState(
        best_source=parent_source,
        best_metrics=best_metrics,
        beam=[(parent_source, best_metrics)],
        best_all_c5=parent_c5,
    )
    traj0 = {
        "gen": -1,
        "kind": "parent",
        "panel_veh": best_metrics.vehicles_sum,
        "all_c5_veh": parent_c5.vehicles_sum,
        "all_c5_dist": parent_c5.distance_sum,
        "all_c5_feasible": f"{parent_c5.feasible}/{parent_c5.total}",
        "hash": source_hash(parent_source),
        "ops": [],
        "hypothesis": "parent",
        "role": "",
        "candidate_id": "parent",
    }
    state.trajectory.append(traj0)
    _append_jsonl(log_path, {"kind": "trajectory", **traj0})

    agents = build_patch_agents(backend, model=model, usage_log=usage)

    for gen in range(max_generations):
        state.llm_calls = _usage_count(usage)
        if state.llm_calls >= max_llm_calls:
            break
        focus = focus_for_generation(gen)
        parents_to_expand = state.beam[:1]
        if len(state.beam) > 1:
            parents_to_expand = state.beam[:2]

        gen_candidates: list[CandidateRecord] = []
        accepted_sources: list[tuple[str, PanelMetrics, CandidateRecord]] = []

        for p_ix, (psrc, pmet) in enumerate(parents_to_expand):
            phash = source_hash(psrc)
            proposals = propose_generation(
                agents,
                backend=backend,
                focus=focus,
                current_source=psrc,
                parent_metrics=pmet.as_dict(),
                generation=gen,
                candidates_per_role=candidates_per_role if p_ix == 0 else 1,
                seed_base=seed_base,
            )
            for ix, prop in enumerate(proposals):
                if _usage_count(usage) >= max_llm_calls:
                    break
                cid = f"g{gen}_p{p_ix}_{prop.role}_{ix}"
                rec = _process_candidate(
                    proposal=prop,
                    parent_source=psrc,
                    parent_metrics=pmet,
                    parent_hash=phash,
                    focus=focus,
                    candidate_id=cid,
                    workspace=workspace,
                    probe=probe,
                    known_ids=known_ids,
                    panel=panel,
                    limits=limits,
                    agents=agents,
                    backend=backend,
                    generation=gen,
                    seed_base=seed_base,
                    allow_experimental_repair=True,
                )
                gen_candidates.append(rec)
                _append_jsonl(log_path, {"generation": gen, **rec.as_dict()})
                if rec.accepted and rec.path:
                    src = Path(rec.path).read_text(encoding="utf-8")
                    assert rec.metrics is not None
                    accepted_sources.append((src, rec.metrics, rec))

        for src, met, rec in accepted_sources:
            if not lex_better_panel(state.best_metrics, met):
                continue
            # Hold as provisional panel elite only after all-C5 stays fully feasible
            write_solver(best_dir, src)
            c5_met, _ = evaluate_panel(best_dir, c5, limits=limits)
            if not c5_met.fully_feasible:
                # Revert best_dir to previous BEST; keep panel beam candidate only if panel-ok
                write_solver(best_dir, state.best_source)
                rec.reject_reason = f"all_c5_infeasible:{c5_met.feasible}/{c5_met.total}"
                rec.accepted = False
                continue
            state.best_source = src
            state.best_metrics = met
            state.best_all_c5 = c5_met
            step = {
                "gen": gen,
                "kind": "accepted",
                "panel_veh": met.vehicles_sum,
                "all_c5_veh": c5_met.vehicles_sum,
                "all_c5_dist": c5_met.distance_sum,
                "all_c5_feasible": f"{c5_met.feasible}/{c5_met.total}",
                "hash": source_hash(src),
                "ops": rec.ops,
                "hypothesis": rec.hypothesis,
                "role": rec.role,
                "candidate_id": rec.candidate_id,
            }
            state.trajectory.append(step)
            _append_jsonl(log_path, {"kind": "trajectory", **step})

        pool: list[tuple[str, PanelMetrics]] = [(state.best_source, state.best_metrics)]
        for src, met, rec in accepted_sources:
            if rec.accepted and met.fully_feasible:
                pool.append((src, met))
        uniq: dict[str, tuple[str, PanelMetrics]] = {}
        for src, met in pool:
            uniq[source_hash(src)] = (src, met)
        ranked = sorted(uniq.values(), key=lambda x: _rank_key(x[1]))
        state.beam = ranked[:beam_size]

        milestone = False
        milestone_iid = ""
        if state.best_metrics.fully_feasible:
            for iid in milestone_instances(state.best_metrics, threshold=4):
                row = (state.best_metrics.by_instance or {}).get(iid) or {}
                if int(row.get("vehicles") or 99) < 5:
                    milestone = True
                    milestone_iid = iid
                    break
        if milestone and not state.milestone_hit:
            state.milestone_hit = True
            state.milestone_instance = milestone_iid

        report = GenerationReport(
            generation=gen,
            focus=focus,
            parent_hash=source_hash(parents_to_expand[0][0]),
            candidates=gen_candidates,
            beam_hashes=[source_hash(s) for s, _ in state.beam],
            best_hash=source_hash(state.best_source),
            best_vehicles_sum=state.best_metrics.vehicles_sum,
            best_distance_sum=state.best_metrics.distance_sum,
            milestone_hit=state.milestone_hit,
            milestone_instance=state.milestone_instance,
        )
        state.generations.append(report)
        _append_jsonl(log_path, {"kind": "generation_summary", **report.as_dict()})
        all_c5_veh = state.best_all_c5.vehicles_sum if state.best_all_c5 else None
        print(
            f"evolution gen={gen} focus={focus} accepted="
            f"{sum(1 for c in gen_candidates if c.accepted)}/"
            f"{len(gen_candidates)} best_panel_veh={state.best_metrics.vehicles_sum} "
            f"best_c5_veh={all_c5_veh} milestone={state.milestone_hit} "
            f"({state.milestone_instance})",
            flush=True,
        )
        if stop_on_milestone and milestone:
            break

    write_solver(best_dir, state.best_source)
    c5_metrics, _ = evaluate_panel(best_dir, c5, limits=limits)
    state.best_all_c5 = c5_metrics

    freeze_dir = None
    improved = (
        c5_metrics.fully_feasible
        and parent_c5.fully_feasible
        and c5_metrics.vehicles_sum < parent_c5.vehicles_sum
    )
    if improved or (stop_on_milestone and state.milestone_hit and c5_metrics.fully_feasible):
        dest = freeze_dir_for(
            source_hash=source_hash(state.best_source),
            seed_base=seed_base if (seed_base or campaign_id) else None,
            campaign_id=campaign_id,
            continuation=continuation,
        )
        freeze_dir = str(
            _write_freeze(
                dest=dest,
                source=state.best_source,
                parent_solver=parent_solver,
                panel=state.best_metrics,
                all_c5=c5_metrics,
                milestone_instance=state.milestone_instance,
                generations=len(state.generations),
                seed_base=seed_base,
                campaign_id=campaign_id,
                trajectory=state.trajectory,
            )
        )

    traj_line = " -> ".join(
        str(s.get("all_c5_veh")) for s in state.trajectory if s.get("all_c5_veh") is not None
    )

    return {
        "protocol": "solver_evolution",
        "model": model,
        "parent": str(parent_solver),
        "parent_hash": source_hash(parent_source),
        "seed_base": seed_base,
        "campaign_id": campaign_id,
        "stop_on_milestone": stop_on_milestone,
        "best_hash": source_hash(state.best_source),
        "best_panel": state.best_metrics.as_dict(),
        "parent_all_c5": parent_c5.as_dict(),
        "all_c5": c5_metrics.as_dict(),
        "trajectory": state.trajectory,
        "trajectory_vehicles": traj_line,
        "improved_vs_parent": bool(improved),
        "milestone_hit": state.milestone_hit,
        "milestone_instance": state.milestone_instance,
        "generations": len(state.generations),
        "generation_reports": [g.as_dict() for g in state.generations],
        "llm_calls": _usage_count(usage),
        "wall_s": round(time.monotonic() - started, 1),
        "best_path": str(best_dir / "solver.py"),
        "freeze_dir": freeze_dir,
        "log_path": str(log_path),
    }
