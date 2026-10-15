"""Multi-generation CV-MAPE evolution over scoring components."""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from evrptw_autolab.agents.base import extract_json, extract_python_source
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.evolution.archive import BundleCandidate, CandidateArchive, hash_sources
from evrptw_autolab.components.evolution.fitness import fitness_from_report
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, SIGNATURES, ComponentKind
from evrptw_autolab.components.loader import load_bundle, validate_component_source, write_bundle
from evrptw_autolab.problem.v2.types import ProblemSpecV2

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[4]
PROMPTS = ROOT / "prompts" / "components"

ROLE_FOR: dict[ComponentKind, str] = {
    "insertion_score": "routing",
    "station_score": "charging",
    "removal_priority": "search",
}


@dataclass
class EvolutionConfig:
    archive_size: int = 10
    generations: int = 4
    seed: int = 0
    time_limit_s: float = 3.0
    alns_iterations: int = 30
    model: str = "fake"
    use_critic: bool = True
    use_cross_variant_memory: bool = True
    max_llm_calls: int = 40
    work_dir: Path | None = None


def _prompt(name: str) -> str:
    path = PROMPTS / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _call_code(
    backend: Any,
    *,
    role: str,
    kind: ComponentKind,
    model: str,
    extra: str = "",
) -> tuple[str, bool, int]:
    """Return (source, llm_generated, tokens). Never silently claim defaults as LLM."""
    raw = backend.complete(
        prompt=_prompt(role) + f"\n\nSignature:\n{SIGNATURES[kind]}\n{extra}",
        role=role,
        temperature=0.4,
        model=model,
        json_mode=True,
    )
    tokens = int(getattr(backend, "last_tokens", 0) or 0)
    try:
        payload = extract_json(raw)
        code = str(payload.get("code") or "")
        if f"def {kind}" not in code:
            recovered = extract_python_source(code) if code else ""
            code = recovered if f"def {kind}" in recovered else ""
        if code and validate_component_source(kind, code).get("ok"):
            return code, True, tokens
    except Exception as error:  # noqa: BLE001
        logger.warning("evolution codegen failed for %s: %s", kind, error)
    return DEFAULT_SOURCES[kind], False, tokens


def _evaluate_bundle(
    spec: ProblemSpecV2,
    sources: dict[str, str],
    owners: dict[str, str],
    *,
    seed: int,
    time_limit_s: float,
    alns_iterations: int,
) -> tuple[Any, Any, float]:
    started = time.monotonic()
    typed_sources: dict[ComponentKind, str] = {
        k: sources[k] for k in sources if k in DEFAULT_SOURCES  # type: ignore[misc]
    }
    typed_owners: dict[ComponentKind, str] = {
        k: owners.get(k, ROLE_FOR[k]) for k in typed_sources  # type: ignore[index]
    }
    bundle, _errors = load_bundle(typed_sources, typed_owners)
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=time_limit_s,
        alns_iterations=alns_iterations,
        policy=bundle,
    )
    report = evaluate(spec, solution)
    return solution, report, time.monotonic() - started


def _crossover(
    a: BundleCandidate,
    b: BundleCandidate,
    rng: random.Random,
) -> dict[str, str]:
    child: dict[str, str] = {}
    keys = sorted(set(a.sources) | set(b.sources))
    for key in keys:
        pick = a.sources.get(key) if rng.random() < 0.5 else b.sources.get(key)
        if pick is None:
            pick = a.sources.get(key) or b.sources.get(key) or DEFAULT_SOURCES[key]  # type: ignore[index]
        child[key] = pick
    return child


def _mutate_kind(rng: random.Random, kinds: list[ComponentKind]) -> ComponentKind:
    return rng.choice(kinds)


def run_evolution(
    specs: list[ProblemSpecV2],
    backend: Any,
    config: EvolutionConfig | None = None,
) -> dict[str, Any]:
    """Evolve a population of component bundles on development specs only."""
    cfg = config or EvolutionConfig()
    if not specs:
        raise ValueError("evolution requires at least one development ProblemSpecV2")
    rng = random.Random(cfg.seed)
    work = cfg.work_dir or (ROOT / "workspace" / "evolution" / f"seed{cfg.seed}")
    work.mkdir(parents=True, exist_ok=True)
    checkpoint = work / "archive.json"
    history_path = work / "history.jsonl"

    archive = CandidateArchive.load(checkpoint) if checkpoint.exists() else CandidateArchive(cfg.archive_size)
    start_gen = 0
    if archive.members:
        start_gen = max(m.generation for m in archive.members) + 1

    llm_calls = 0
    tokens = 0
    history: list[dict[str, Any]] = []
    kinds: list[ComponentKind] = ["insertion_score", "station_score", "removal_priority"]

    # Seed archive with defaults + one LLM sample per role if empty.
    if not archive.members:
        default_sources = {k: DEFAULT_SOURCES[k] for k in kinds}
        owners = {k: ROLE_FOR[k] for k in kinds}
        for i, spec in enumerate(specs[:2]):
            _sol, report, runtime = _evaluate_bundle(
                spec,
                default_sources,
                owners,
                seed=cfg.seed + i,
                time_limit_s=cfg.time_limit_s,
                alns_iterations=cfg.alns_iterations,
            )
            cand = BundleCandidate(
                candidate_id=f"g0_default_{i}",
                sources=dict(default_sources),
                owners=dict(owners),
                generation=0,
                feasible=bool(report.feasible),
                objective_key=list(report.objective_key),
                runtime_s=runtime,
                fitness=fitness_from_report(report, runtime),
                llm_generated=False,
                model=cfg.model,
                source_hashes=hash_sources(default_sources),
                metadata={"seed_type": "default"},
            )
            archive.add(cand)

        if llm_calls < cfg.max_llm_calls:
            sources = dict(default_sources)
            llm_any = False
            for kind in kinds:
                if llm_calls >= cfg.max_llm_calls:
                    break
                code, ok, tok = _call_code(
                    backend, role=ROLE_FOR[kind], kind=kind, model=cfg.model
                )
                llm_calls += 1
                tokens += tok
                if ok:
                    sources[kind] = code
                    llm_any = True
            spec = specs[0]
            _sol, report, runtime = _evaluate_bundle(
                spec,
                sources,
                owners,
                seed=cfg.seed,
                time_limit_s=cfg.time_limit_s,
                alns_iterations=cfg.alns_iterations,
            )
            archive.add(
                BundleCandidate(
                    candidate_id="g0_llm_seed",
                    sources=sources,
                    owners=owners,
                    generation=0,
                    feasible=bool(report.feasible),
                    objective_key=list(report.objective_key),
                    runtime_s=runtime,
                    fitness=fitness_from_report(report, runtime),
                    llm_generated=llm_any,
                    model=cfg.model,
                    tokens=tokens,
                    source_hashes=hash_sources(sources),
                    metadata={"seed_type": "llm"},
                )
            )

    incumbent = archive.best()

    for gen in range(start_gen, start_gen + cfg.generations):
        if llm_calls >= cfg.max_llm_calls:
            break
        parents = archive.select_parents(rng, k=2)
        if len(parents) < 2:
            parents = list(archive.members)[:2]
        if len(parents) < 1:
            break

        # Crossover + specialist mutation.
        child_sources = _crossover(parents[0], parents[-1], rng)
        mutate_kind = _mutate_kind(rng, kinds)
        if llm_calls < cfg.max_llm_calls:
            code, ok, tok = _call_code(
                backend,
                role=ROLE_FOR[mutate_kind],
                kind=mutate_kind,
                model=cfg.model,
                extra=f"\nMutate component {mutate_kind}. Parent hash={parents[0].fingerprint()}.",
            )
            llm_calls += 1
            tokens += tok
            if ok:
                child_sources[mutate_kind] = code
            else:
                logger.warning("generation %s: mutation fell back to default for %s", gen, mutate_kind)

        # Optional critic-guided repair on a random development instance.
        eval_spec = rng.choice(specs)
        owners = {k: ROLE_FOR[k] for k in child_sources}  # type: ignore[index]
        _sol, report, runtime = _evaluate_bundle(
            eval_spec,
            child_sources,
            owners,
            seed=cfg.seed + gen,
            time_limit_s=cfg.time_limit_s,
            alns_iterations=cfg.alns_iterations,
        )

        if (
            cfg.use_critic
            and not report.feasible
            and llm_calls < cfg.max_llm_calls
            and report.first_fault is not None
        ):
            fault = report.first_fault.family
            target: ComponentKind
            if fault in {"BATTERY", "CHARGE_POLICY", "DURATION"}:
                target = "station_score"
            elif fault in {"WINDOW"}:
                target = "insertion_score"
            else:
                target = "removal_priority"
            code, ok, tok = _call_code(
                backend,
                role=ROLE_FOR[target],
                kind=target,
                model=cfg.model,
                extra=f"\nCounterexample fault={fault}: {report.first_fault.detail}",
            )
            llm_calls += 1
            tokens += tok
            if ok:
                child_sources[target] = code
                _sol, report, runtime = _evaluate_bundle(
                    eval_spec,
                    child_sources,
                    owners,
                    seed=cfg.seed + gen,
                    time_limit_s=cfg.time_limit_s,
                    alns_iterations=cfg.alns_iterations,
                )

        # Cross-variant memory: if enabled, also score on a second family when available.
        fitness = fitness_from_report(report, runtime)
        if cfg.use_cross_variant_memory and len(specs) > 1:
            other = next((s for s in specs if s.family != eval_spec.family), None)
            if other is not None:
                _s2, r2, rt2 = _evaluate_bundle(
                    other,
                    child_sources,
                    owners,
                    seed=cfg.seed + gen + 17,
                    time_limit_s=cfg.time_limit_s,
                    alns_iterations=cfg.alns_iterations,
                )
                fitness = 0.5 * fitness + 0.5 * fitness_from_report(r2, rt2)
                report = r2 if (r2.feasible and not report.feasible) else report

        child = BundleCandidate(
            candidate_id=f"g{gen}_{rng.randrange(1_000_000)}",
            sources=child_sources,
            owners=owners,
            generation=gen,
            parent_ids=[p.candidate_id for p in parents],
            feasible=bool(report.feasible),
            objective_key=list(report.objective_key),
            runtime_s=runtime,
            fitness=fitness,
            llm_generated=True,
            model=cfg.model,
            tokens=tokens,
            source_hashes=hash_sources(child_sources),
            metadata={"eval_instance": eval_spec.instance_id, "eval_family": eval_spec.family},
        )
        archive.add(child)
        if incumbent is None or (
            child.feasible and (not incumbent.feasible or child.fitness > incumbent.fitness)
        ):
            incumbent = child

        record = {
            "generation": gen,
            "candidate_id": child.candidate_id,
            "feasible": child.feasible,
            "fitness": child.fitness,
            "llm_calls": llm_calls,
            "tokens": tokens,
            "fingerprint": child.fingerprint(),
        }
        history.append(record)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
        archive.save(checkpoint)

    # Freeze best feasible (or best overall) for zero-LLM deployment.
    best = archive.best()
    frozen_dir = work / "frozen_bundle"
    if best is not None:
        bundle, _ = load_bundle(best.sources, best.owners)  # type: ignore[arg-type]
        write_bundle(bundle, frozen_dir)
        (work / "frozen_meta.json").write_text(
            json.dumps(
                {
                    "candidate_id": best.candidate_id,
                    "feasible": best.feasible,
                    "fitness": best.fitness,
                    "source_hashes": best.source_hashes,
                    "llm_generated": best.llm_generated,
                    "model": best.model,
                    "deployment_llm_calls": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    result = {
        "experiment": "cv_mape_evolution",
        "seed": cfg.seed,
        "model": cfg.model,
        "generations_requested": cfg.generations,
        "generations_completed": len({h["generation"] for h in history}),
        "archive_size": len(archive.members),
        "llm_calls": llm_calls,
        "llm_tokens": tokens,
        "use_critic": cfg.use_critic,
        "use_cross_variant_memory": cfg.use_cross_variant_memory,
        "best_feasible": bool(best.feasible) if best else False,
        "best_fitness": best.fitness if best else None,
        "best_candidate_id": best.candidate_id if best else None,
        "frozen_bundle": str(frozen_dir),
        "checkpoint": str(checkpoint),
        "history": history,
        "note": (
            "Fitness uses development instances only. Frozen bundle requires zero LLM calls at deploy time. "
            "Default heuristic fallbacks are logged and not counted as LLM discoveries."
        ),
    }
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


AblationName = Literal[
    "classical",
    "single_agent",
    "five_agent",
    "five_agent_evolution",
    "evolution_no_critic",
    "evolution_no_cross_memory",
]
