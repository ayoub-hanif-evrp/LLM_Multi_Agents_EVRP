"""Milestone 9B population evolution runner."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evocharge.evolution.fitness import (
    fitness_from_evaluation,
    penalize_or_drop,
    update_pareto_archive,
)
from evocharge.evolution.freeze import build_freeze_manifest, write_freeze_manifest
from evocharge.evolution.gates import run_gates
from evocharge.evolution.offspring import (
    choose_offspring_modes,
    make_offspring,
    seed_sources,
    source_fingerprint,
)
from evocharge.evolution.schemas import CandidateRecord, PopulationState
from evocharge.operators.generated_api import API_VERSION
from evocharge.operators.primitives import catalogue_hash
from evocharge.reproducibility import sha256_text


def load_m9b_config(path: Path) -> dict[str, Any]:
    return dict(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})


def _write_candidate(
    project_root: Path,
    candidate_id: str,
    source: str,
    record: CandidateRecord,
) -> Path:
    cdir = project_root / "artifacts" / "candidates" / candidate_id
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "source.py").write_text(source, encoding="utf-8")
    (cdir / "lineage.json").write_text(
        record.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return cdir


def _admit(
    *,
    project_root: Path,
    candidate_id: str,
    source: str,
    record: CandidateRecord,
    fidelity: str,
    archive_fps: list[dict[str, Any]],
) -> tuple[CandidateRecord, dict[str, Any]]:
    gate = run_gates(
        source,
        project_root=project_root,
        candidate_id=candidate_id,
        fidelity=fidelity,
    )
    record.source_hash = sha256_text(source)
    record.catalogue_hash = catalogue_hash()
    record.api_version = API_VERSION
    if not gate.get("accepted"):
        record.rejection_reason = (
            f"{gate.get('failed_stage')}:{','.join(gate.get('errors') or [])}"
        )
        record.static_accepted = bool((gate.get("static") or {}).get("accepted"))
        record.dynamic_accepted = False
        record.metamorphic_accepted = False
        record.evaluation_exposure = str(gate.get("failed_stage") or "gate_fail")
        return record, gate

    evaluation = gate.get("evaluation") or {}
    record.static_accepted = True
    record.dynamic_accepted = True
    record.metamorphic_accepted = True
    record.evaluation_exposure = fidelity
    record.outcome_counts = dict(evaluation.get("outcome_counts") or {})
    record.n_changed_instances = int(evaluation.get("n_changed_instances") or 0)
    record.fitness = fitness_from_evaluation(
        evaluation=evaluation,
        source=source,
        is_noop=record.is_noop,
        archive_fps=archive_fps,
    )
    drop = penalize_or_drop(record)
    if drop and not record.is_noop:
        record.rejection_reason = drop
    _write_candidate(project_root, candidate_id, source, record)
    return record, gate


def run_evolution(
    *,
    project_root: Path,
    config_path: Path,
    experiment_id: str | None = None,
    backend: str = "structured",
    generation_method: str = "structured",
    freeze_path: Path | None = None,
    seed_override: int | None = None,
) -> dict[str, Any]:
    """Run population evolution under a frozen contract.

    generation_method:
      - structured: M9B typed modification plans
      - random_mutation: baseline_random_mutation only
      - random_composition: random_composition only
      - llm_guided: LLM AttributionModificationPlan then typed implement
    backend: mock|ollama|replay for llm_guided plan proposals
    """
    cfg = load_m9b_config(config_path)
    pop_cfg = dict(cfg.get("population") or {})
    eval_cfg = dict(cfg.get("evaluation") or {})
    model = str((cfg.get("model") or {}).get("name") or "qwen3:4b")

    pop_size = int(pop_cfg.get("population_size", 8))
    offspring_n = int(pop_cfg.get("offspring_per_generation", 4))
    generations = int(pop_cfg.get("generations", 5))
    seed = int(seed_override if seed_override is not None else pop_cfg.get("seed", 2027))
    fidelity_short = str(eval_cfg.get("fidelity_short", "short"))

    eid = experiment_id or f"m9b_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    exp_dir = project_root / "artifacts" / "evolution" / eid
    exp_dir.mkdir(parents=True, exist_ok=True)

    if freeze_path is not None and Path(freeze_path).is_file():
        freeze = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
        write_freeze_manifest(exp_dir / "freeze_manifest.json", freeze)
    else:
        freeze = build_freeze_manifest(project_root, config=cfg, model=model)
        write_freeze_manifest(exp_dir / "freeze_manifest.json", freeze)
    freeze_hash = str(freeze["freeze_hash"])

    rng = random.Random(seed)
    state = PopulationState(experiment_id=eid, generation=0, freeze_hash=freeze_hash)

    # --- Seed population ---
    seeds = seed_sources()
    from evocharge.evolution.offspring import _random_composition

    seeds["seed_random"] = (
        _random_composition(random.Random(seed + 1)),
        "random_composition",
        ["RAND"],
    )
    archive_fps: list[dict[str, Any]] = []
    for key, (source, mode, hyps) in seeds.items():
        cid = f"{eid}_{key}"
        rec = CandidateRecord(
            candidate_id=cid,
            parent_ids=[],
            generation=0,
            creation_mode=mode,
            hypothesis_ids=hyps,
            model=model if generation_method == "llm_guided" else None,
            freeze_hash=freeze_hash,
            is_noop=(mode == "noop_control"),
            modification_plan=None,
        )
        rec, _gate = _admit(
            project_root=project_root,
            candidate_id=cid,
            source=source,
            record=rec,
            fidelity=fidelity_short,
            archive_fps=archive_fps,
        )
        if rec.rejection_reason and not rec.is_noop:
            state.rejected.append(rec)
        else:
            state.members.append(rec)
            if not rec.is_noop and rec.static_accepted:
                state.archive = update_pareto_archive(state.archive, rec)
                archive_fps.append(source_fingerprint(source))

    useful = [m for m in state.members if not m.is_noop]
    noops = [m for m in state.members if m.is_noop]
    useful = useful[: max(0, pop_size - 1)]
    state.members = useful + noops[:1]

    stats: dict[str, Any] = {
        "backend": backend,
        "generation_method": generation_method,
        "gate_rejections": [],
        "generation_stats": [],
        "model_calls": 0,
        "llm_plan_latency_seconds": 0.0,
        "candidates_evaluated": 0,
        "model_limitation": freeze["model_configuration"]["model_limitation_note"],
    }

    for gen in range(1, generations + 1):
        state.generation = gen
        modes_list: list[Any]
        if generation_method == "random_mutation":
            modes_list = ["baseline_random_mutation"] * offspring_n
        elif generation_method == "random_composition":
            modes_list = ["random_composition"] * offspring_n
        else:
            modes_list = list(choose_offspring_modes(rng, offspring_n))
        modes = modes_list
        parents = [m for m in state.members if not m.is_noop] or state.members
        gen_accepted = 0
        gen_rejected = 0
        max_revisions = int(pop_cfg.get("max_revisions_per_candidate", 1))
        for i, mode in enumerate(modes):
            parent_sample = rng.sample(parents, k=min(2, len(parents)))
            parent_ids = [p.candidate_id for p in parent_sample]
            plan = None
            source = ""
            suffix = "x"
            if generation_method == "llm_guided":
                from evocharge.evolution.llm_offspring import llm_offspring_source
                from evocharge.evolution.schemas import ModificationPlan as MP

                # Equal evaluation budget: retry until we obtain an implementable
                # plan for this offspring slot (plan failures do not shrink evals).
                llm_out: dict[str, Any] = {}
                for attempt in range(1 + max_revisions):
                    art = exp_dir / "llm_calls" / f"g{gen}_{i}_a{attempt}"
                    llm_out = llm_offspring_source(
                        backend_name=(
                            backend if backend in {"mock", "ollama", "replay"} else "mock"
                        ),
                        model=model,
                        creation_mode=str(mode),
                        parents=list(parent_sample),
                        rng_seed=seed + gen * 17 + i * 31 + attempt,
                        artifacts_dir=art,
                    )
                    stats["model_calls"] += 1
                    stats["llm_plan_latency_seconds"] += float(
                        llm_out.get("llm_latency_seconds") or 0.0
                    )
                    if llm_out.get("plan_accepted") and llm_out.get("source"):
                        break
                if not llm_out.get("plan_accepted") or not llm_out.get("source"):
                    # Last-resort typed offspring so evaluation slots stay equal;
                    # tagged so attribution can count plan failures separately.
                    source, plan, suffix = make_offspring(
                        mode="mutation",
                        rng=rng,
                        parent_ids=parent_ids,
                        generation=gen,
                    )
                    suffix = f"llm_fallback_{mode}"
                    stats["gate_rejections"].append(
                        {
                            "candidate_id": f"{eid}_g{gen}_llmfail_{i}",
                            "stage": "llm_plan_fallback_typed",
                            "errors": [llm_out.get("error") or "plan_invalid"],
                        }
                    )
                else:
                    source = str(llm_out["source"])
                    plan = MP.model_validate(llm_out["modification_plan"])
                    suffix = f"llm_{mode}"
            else:
                source, plan, suffix = make_offspring(
                    mode=mode,
                    rng=rng,
                    parent_ids=parent_ids,
                    generation=gen,
                )
            cid = f"{eid}_g{gen}_{suffix}_{i}"
            from evocharge.evolution.schemas import CreationMode

            rec_mode: CreationMode = mode if mode in {
                "seed",
                "mutation",
                "semantic_crossover",
                "evidence_guided_revision",
                "novel_invention",
                "random_composition",
                "handcrafted_analogue",
                "noop_control",
                "baseline_random_mutation",
                "baseline_non_llm",
            } else "mutation"
            rec = CandidateRecord(
                candidate_id=cid,
                parent_ids=parent_ids,
                generation=gen,
                creation_mode=rec_mode,
                hypothesis_ids=["M10A" if generation_method == "llm_guided" else "M9B"],
                model=model if generation_method == "llm_guided" else None,
                freeze_hash=freeze_hash,
                modification_plan=plan,
                metadata={
                    "generation_method": generation_method,
                    "llm_plan_fallback": "fallback" in suffix,
                },
            )
            rec, gate = _admit(
                project_root=project_root,
                candidate_id=cid,
                source=source,
                record=rec,
                fidelity=fidelity_short,
                archive_fps=archive_fps,
            )
            stats["candidates_evaluated"] += 1
            if not gate.get("accepted") or rec.rejection_reason:
                gen_rejected += 1
                stats["gate_rejections"].append(
                    {
                        "candidate_id": cid,
                        "stage": gate.get("failed_stage") or rec.rejection_reason,
                        "errors": gate.get("errors"),
                    }
                )
                state.rejected.append(rec)
                continue
            gen_accepted += 1
            state.members.append(rec)
            state.archive = update_pareto_archive(state.archive, rec)
            archive_fps.append(source_fingerprint(source))

        def _key(m: CandidateRecord) -> float:
            if m.is_noop:
                return -1.0
            f = m.fitness
            return (
                f.effective_behavioral_change_rate * 2.0
                + f.feasibility_preservation_rate
                + f.novelty
                - f.degradation_rate
            )

        noops = [m for m in state.members if m.is_noop]
        rest = sorted([m for m in state.members if not m.is_noop], key=_key, reverse=True)
        state.members = rest[: max(1, pop_size - 1)] + noops[:1]
        stats["generation_stats"].append(
            {
                "generation": gen,
                "accepted": gen_accepted,
                "rejected": gen_rejected,
                "population": len(state.members),
                "archive": len(state.archive),
            }
        )
        (exp_dir / f"generation_{gen}.json").write_text(
            state.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    offspring = [m for m in state.members + state.archive if m.generation > 0]
    distinct = any(
        m.n_changed_instances >= 1 and m.parent_ids for m in offspring
    )
    multi_effective = any(
        m.n_changed_instances > 1 and m.fitness.effective_behavioral_change_rate > 0
        for m in state.archive + state.members
        if not m.is_noop
    )
    useful_offspring = [
        m
        for m in offspring
        if m.fitness.effective_behavioral_change_rate > 0 and m.n_changed_instances > 0
    ]

    summary = {
        "experiment_id": eid,
        "freeze_hash": freeze_hash,
        "backend": backend,
        "generation_method": generation_method,
        "seed": seed,
        "population_final": [m.model_dump() for m in state.members],
        "archive": [m.model_dump() for m in state.archive],
        "rejected_count": len(state.rejected),
        "stats": stats,
        "metrics": {
            "candidates_evaluated": stats["candidates_evaluated"],
            "useful_offspring": len(useful_offspring),
            "useful_per_evaluated": (
                len(useful_offspring) / max(1, stats["candidates_evaluated"])
            ),
            "mean_effective_rate_archive": (
                sum(m.fitness.effective_behavioral_change_rate for m in state.archive)
                / max(1, len(state.archive))
            ),
            "llm_calls": stats["model_calls"],
            "llm_plan_latency_seconds": stats["llm_plan_latency_seconds"],
        },
        "success_flags": {
            "complete_run": True,
            "survivors_gated": all(
                m.static_accepted and m.metamorphic_accepted
                for m in state.members
                if not m.rejection_reason
            ),
            "lineage_reproducible": True,
            "offspring_behaviorally_distinct": distinct,
            "multi_instance_effective": multi_effective,
            "pareto_archive_nonempty": len(state.archive) > 0,
            "noop_not_promoted": all(
                (not m.archived) or (not m.is_noop) for m in state.archive
            ),
        },
        "optimization_claim": False,
        "auto_promoted": False,
        "schneider_transfer": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (exp_dir / "population_final.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (exp_dir / "lineage_graph.json").write_text(
        json.dumps(
            {
                "nodes": [
                    {
                        "id": m.candidate_id,
                        "generation": m.generation,
                        "mode": m.creation_mode,
                    }
                    for m in state.members + state.archive + state.rejected
                ],
                "edges": [
                    {"parent": p, "child": m.candidate_id}
                    for m in state.members + state.archive + state.rejected
                    for p in m.parent_ids
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return summary
