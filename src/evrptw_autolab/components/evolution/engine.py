"""Multi-generation CV-MAPE evolution over scoring components."""
from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from evrptw_autolab.agents.base import extract_json, extract_python_source
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.evolution.archive import (
    BundleCandidate,
    CandidateArchive,
    apply_panel,
    classify_attribution,
    hash_sources,
    source_hash,
)
from evrptw_autolab.components.evolution.fitness import (
    build_panel_evaluation,
    instance_eval_from_report,
)
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, SIGNATURES, ComponentKind
from evrptw_autolab.components.loader import load_bundle, validate_component_source, write_bundle
from evrptw_autolab.llm.usage import BudgetExhausted, UsageCollector
from evrptw_autolab.problem.v2.types import ProblemSpecV2

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[4]
PROMPTS = ROOT / "prompts" / "components"

ROLE_FOR: dict[ComponentKind, str] = {
    "insertion_score": "routing",
    "station_score": "charging",
    "removal_priority": "search",
}

KINDS: list[ComponentKind] = ["insertion_score", "station_score", "removal_priority"]


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
    max_llm_tokens: int | None = None
    max_wall_s: float | None = None
    panel_seeds: list[int] = field(default_factory=lambda: [0])
    work_dir: Path | None = None


def _prompt(name: str) -> str:
    path = PROMPTS / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _typed_sources(sources: dict[str, str]) -> dict[ComponentKind, str]:
    out: dict[ComponentKind, str] = {}
    for kind in KINDS:
        if kind in sources:
            out[kind] = sources[kind]
    return out


def evaluate_candidate_on_panel(
    sources: dict[str, str],
    owners: dict[str, str],
    panel: list[ProblemSpecV2],
    *,
    seeds: list[int],
    time_limit_s: float,
    alns_iterations: int,
    validation_ok: bool = True,
) -> Any:
    """Evaluate one candidate on a frozen panel under matched budgets."""
    typed = _typed_sources(sources)
    typed_owners = {k: owners.get(k, ROLE_FOR[k]) for k in typed}
    bundle, errors = load_bundle(typed, typed_owners)
    rows = []
    for spec in panel:
        for seed in seeds:
            started = time.monotonic()
            solution = solve_classical(
                spec,
                seed=seed,
                time_limit_s=time_limit_s,
                alns_iterations=alns_iterations,
                policy=bundle,
            )
            report = evaluate(spec, solution)
            rows.append(
                instance_eval_from_report(
                    family=str(spec.family),
                    instance_id=str(spec.instance_id),
                    seed=int(seed),
                    report=report,
                    runtime_s=time.monotonic() - started,
                )
            )
    panel_eval = build_panel_evaluation(rows, validation_ok=validation_ok and not errors)
    return panel_eval, errors


def _generate_component(
    collector: UsageCollector,
    backend: Any,
    *,
    kind: ComponentKind,
    model: str,
    extra: str = "",
    candidate_id: str | None = None,
    generation: int | None = None,
) -> dict[str, Any]:
    """Return attribution dict including executed source (never silently LLM-claim defaults)."""
    role = ROLE_FOR[kind]
    generated = ""
    extract_status = "fallback_no_call"
    llm_generated = False
    fallback = True
    try:
        raw = collector.complete(
            backend,
            prompt=_prompt(role) + f"\n\nSignature:\n{SIGNATURES[kind]}\n{extra}",
            role=role,
            temperature=0.4,
            model=model,
            json_mode=True,
            candidate_id=candidate_id,
            generation=generation,
        )
        payload = extract_json(raw)
        generated = str(payload.get("code") or "")
        code = generated
        if f"def {kind}" not in code:
            recovered = extract_python_source(code) if code else ""
            if f"def {kind}" in recovered:
                code = recovered
                extract_status = "recovered_from_markdown"
            else:
                code = DEFAULT_SOURCES[kind]
                extract_status = "fallback_missing_def"
        else:
            extract_status = "ok"
        check = validate_component_source(kind, code)
        if check.get("ok") and extract_status in {"ok", "recovered_from_markdown"}:
            llm_generated = True
            fallback = False
            executed = code
        else:
            logger.warning("component %s invalid (%s); using default", kind, check.get("detail"))
            executed = DEFAULT_SOURCES[kind]
            extract_status = f"fallback_validation:{check.get('detail')}"
            fallback = True
            llm_generated = False
    except BudgetExhausted:
        raise
    except Exception as error:  # noqa: BLE001
        logger.warning("component %s generation failed: %s", kind, error)
        executed = DEFAULT_SOURCES[kind]
        extract_status = f"fallback_error:{error}"
        fallback = True
        llm_generated = False

    return {
        "kind": kind,
        "agent_role": role,
        "model": model,
        "generated_source_hash": source_hash(generated) if generated else "",
        "executed_source_hash": source_hash(executed),
        "mutation_accepted": llm_generated and not fallback,
        "fallback_applied": fallback,
        "human_default_used": executed.strip() == DEFAULT_SOURCES[kind].strip(),
        "successful_repair": False,
        "llm_generated": llm_generated and not fallback,
        "extract_status": extract_status,
        "executed_source": executed,
    }


def _critic_diagnosis(
    collector: UsageCollector,
    backend: Any,
    *,
    model: str,
    panel_summary: dict[str, Any],
    candidate_id: str,
    generation: int,
) -> dict[str, Any]:
    prompt = (
        _prompt("critic")
        + "\n\nYou are the Critic agent. Ground the diagnosis in the evaluator summary below.\n"
        + "Return JSON with keys: verdict, reason, next_component, fault_families, hypothesis.\n"
        + f"\nPanel summary:\n{json.dumps(panel_summary)[:4000]}"
    )
    try:
        raw = collector.complete(
            backend,
            prompt=prompt,
            role="critic",
            temperature=0.2,
            model=model,
            json_mode=True,
            candidate_id=candidate_id,
            generation=generation,
        )
        data = extract_json(raw)
        return {
            "verdict": str(data.get("verdict") or "REVISE"),
            "reason": str(data.get("reason") or ""),
            "next_component": str(data.get("next_component") or "none"),
            "fault_families": list(data.get("fault_families") or []),
            "hypothesis": str(data.get("hypothesis") or ""),
            "llm_ok": True,
        }
    except BudgetExhausted:
        raise
    except Exception as error:  # noqa: BLE001
        return {
            "verdict": "REVISE",
            "reason": f"critic_fallback:{error}",
            "next_component": "station_score",
            "fault_families": [],
            "hypothesis": "",
            "llm_ok": False,
        }


def _architect_plan(
    collector: UsageCollector,
    backend: Any,
    *,
    model: str,
    families: list[str],
    candidate_id: str,
    generation: int,
) -> dict[str, Any]:
    prompt = (
        _prompt("architect")
        + f"\n\nDevelopment families={families}. Propose which components to mutate this generation.\n"
        + 'Return JSON: {"summary": str, "components": ["insertion_score"|"station_score"|"removal_priority"], '
        + '"hypothesis": str}'
    )
    try:
        raw = collector.complete(
            backend,
            prompt=prompt,
            role="architect",
            temperature=0.3,
            model=model,
            json_mode=True,
            candidate_id=candidate_id,
            generation=generation,
        )
        data = extract_json(raw)
        comps = [c for c in (data.get("components") or []) if c in KINDS]
        return {
            "summary": str(data.get("summary") or ""),
            "components": comps or ["insertion_score"],
            "hypothesis": str(data.get("hypothesis") or ""),
            "llm_ok": True,
        }
    except BudgetExhausted:
        raise
    except Exception as error:  # noqa: BLE001
        return {
            "summary": f"architect_fallback:{error}",
            "components": ["insertion_score"],
            "hypothesis": "",
            "llm_ok": False,
        }


def _crossover(a: BundleCandidate, b: BundleCandidate, rng: random.Random) -> dict[str, str]:
    child: dict[str, str] = {}
    for key in KINDS:
        left = a.sources.get(key)
        right = b.sources.get(key)
        pick = left if rng.random() < 0.5 else right
        child[key] = pick or DEFAULT_SOURCES[key]
    return child


def run_evolution(
    specs: list[ProblemSpecV2],
    backend: Any,
    config: EvolutionConfig | None = None,
) -> dict[str, Any]:
    """Evolve component bundles with panel-comparable fitness and five-role coordination."""
    cfg = config or EvolutionConfig()
    if not specs:
        raise ValueError("evolution requires at least one development ProblemSpecV2")
    rng = random.Random(cfg.seed)
    work = cfg.work_dir or (ROOT / "workspace" / "evolution" / f"seed{cfg.seed}")
    work.mkdir(parents=True, exist_ok=True)
    checkpoint = work / "archive.json"
    history_path = work / "history.jsonl"
    transfer_log = work / "transfer_log.jsonl"

    archive = CandidateArchive.load(checkpoint) if checkpoint.exists() else CandidateArchive(cfg.archive_size)
    start_gen = 0
    if archive.members:
        start_gen = max(m.generation for m in archive.members) + 1

    collector = UsageCollector(
        max_calls=cfg.max_llm_calls,
        max_tokens=cfg.max_llm_tokens,
        max_wall_s=cfg.max_wall_s,
    )
    # Resume budgets from checkpoint — never reset to zero.
    collector.restore(
        logical_calls=archive.llm_calls,
        total_tokens=archive.llm_tokens,
        wall_s=archive.wall_s,
    )

    history: list[dict[str, Any]] = []
    panel = list(specs)
    panel_seeds = list(cfg.panel_seeds) or [cfg.seed]
    families = sorted({str(s.family) for s in panel})

    # Seed archive with classical defaults evaluated on the full panel.
    if not archive.members:
        default_sources: dict[str, str] = {k: DEFAULT_SOURCES[k] for k in KINDS}
        owners: dict[str, str] = {k: ROLE_FOR[k] for k in KINDS}
        panel_eval, load_errors = evaluate_candidate_on_panel(
            default_sources,
            owners,
            panel,
            seeds=panel_seeds,
            time_limit_s=cfg.time_limit_s,
            alns_iterations=cfg.alns_iterations,
        )
        panel_eval.validation_ok = panel_eval.validation_ok and not load_errors
        cand = BundleCandidate(
            candidate_id="g0_default",
            sources=default_sources,
            owners=owners,
            generation=0,
            llm_generated=False,
            genuine_llm_components=0,
            attribution_category="pure_classical",
            model=cfg.model,
            source_hashes=hash_sources(default_sources),
            component_attribution=[
                {
                    "kind": k,
                    "agent_role": ROLE_FOR[k],
                    "llm_generated": False,
                    "human_default_used": True,
                    "fallback_applied": False,
                    "executed_source_hash": source_hash(DEFAULT_SOURCES[k]),
                }
                for k in KINDS
            ],
            metadata={"seed_type": "default", "load_errors": load_errors},
        )
        apply_panel(cand, panel_eval, validation_status="ok" if not load_errors else "invalid")
        archive.add(cand)

    for gen in range(start_gen, start_gen + cfg.generations):
        if collector.stopped or (
            cfg.max_llm_calls is not None and collector.logical_calls >= cfg.max_llm_calls
        ):
            break
        parents = archive.select_parents(rng, k=2)
        if not parents:
            break
        parent_a = parents[0]
        parent_b = parents[-1]
        child_id = f"g{gen}_{rng.randrange(1_000_000)}"

        try:
            plan = _architect_plan(
                collector,
                backend,
                model=cfg.model,
                families=families,
                candidate_id=child_id,
                generation=gen,
            )
        except BudgetExhausted as error:
            logger.warning("budget exhausted before architect: %s", error)
            break

        child_sources = _crossover(parent_a, parent_b, rng)
        attr_rows: list[dict[str, Any]] = []
        causal: list[dict[str, Any]] = [{"step": "architect", "plan": plan}]

        # Specialist mutations for components selected by Architect.
        for kind_name in plan["components"]:
            if kind_name not in KINDS:
                continue
            kind = cast(ComponentKind, kind_name)
            try:
                attr = _generate_component(
                    collector,
                    backend,
                    kind=kind,
                    model=cfg.model,
                    extra=(
                        f"\nHypothesis: {plan.get('hypothesis')}\n"
                        f"Mutate {kind}. Parent fingerprint={parent_a.fingerprint()}."
                    ),
                    candidate_id=child_id,
                    generation=gen,
                )
            except BudgetExhausted as error:
                logger.warning("budget exhausted during mutation: %s", error)
                break
            child_sources[kind] = attr["executed_source"]
            attr_rows.append(attr)
            causal.append({"step": "mutate", "component": kind, "attribution": {
                k: attr[k] for k in attr if k != "executed_source"
            }})

        # Ensure all three kinds exist.
        for kind in KINDS:
            if kind not in child_sources:
                child_sources[kind] = DEFAULT_SOURCES[kind]
                attr_rows.append(
                    {
                        "kind": kind,
                        "agent_role": ROLE_FOR[kind],
                        "llm_generated": False,
                        "human_default_used": True,
                        "fallback_applied": True,
                        "executed_source_hash": source_hash(DEFAULT_SOURCES[kind]),
                    }
                )

        owners = {str(k): ROLE_FOR[k] for k in KINDS}
        panel_eval, errors = evaluate_candidate_on_panel(
            child_sources,
            owners,
            panel,
            seeds=panel_seeds,
            time_limit_s=cfg.time_limit_s,
            alns_iterations=cfg.alns_iterations,
        )
        if errors:
            panel_eval.validation_ok = False
        causal.append({"step": "evaluate", "panel": {
            "instances_feasible": panel_eval.instances_feasible,
            "instances_tested": panel_eval.instances_tested,
            "fully_feasible_on_panel": panel_eval.fully_feasible_on_panel,
        }})

        # Real Critic-agent call grounded in evaluator summary.
        if cfg.use_critic and not panel_eval.fully_feasible_on_panel:
            summary = {
                "per_variant": panel_eval.per_variant,
                "faults": [
                    {"family": r.fault_family, "detail": r.fault_detail, "instance": r.instance_id}
                    for r in panel_eval.per_instance
                    if not r.feasible
                ][:12],
            }
            try:
                diagnosis = _critic_diagnosis(
                    collector,
                    backend,
                    model=cfg.model,
                    panel_summary=summary,
                    candidate_id=child_id,
                    generation=gen,
                )
            except BudgetExhausted as error:
                logger.warning("budget exhausted during critic: %s", error)
                diagnosis = {"verdict": "STOP", "reason": str(error), "next_component": "none", "llm_ok": False}
            causal.append({"step": "critic", "diagnosis": diagnosis})
            target = diagnosis.get("next_component")
            if target in KINDS and diagnosis.get("verdict") == "REVISE":
                repair_attr: dict[str, Any] | None
                try:
                    repair_attr = _generate_component(
                        collector,
                        backend,
                        kind=cast(ComponentKind, target),
                        model=cfg.model,
                        extra=(
                            f"\nCritic diagnosis: {diagnosis.get('reason')}\n"
                            f"Hypothesis: {diagnosis.get('hypothesis')}\n"
                            f"Fault families: {diagnosis.get('fault_families')}"
                        ),
                        candidate_id=child_id,
                        generation=gen,
                    )
                except BudgetExhausted:
                    repair_attr = None
                if repair_attr is not None:
                    attr = repair_attr
                    attr["successful_repair"] = attr.get("llm_generated", False)
                    child_sources[target] = attr["executed_source"]
                    attr_rows.append(attr)
                    panel_eval, errors = evaluate_candidate_on_panel(
                        child_sources,
                        owners,
                        panel,
                        seeds=panel_seeds,
                        time_limit_s=cfg.time_limit_s,
                        alns_iterations=cfg.alns_iterations,
                    )
                    if errors:
                        panel_eval.validation_ok = False
                    causal.append({"step": "repair_eval", "component": target, "feasible": panel_eval.fully_feasible_on_panel})

        # Cross-variant memory: log transfer attempts from parent components of other families.
        if cfg.use_cross_variant_memory and parent_a.metadata.get("source_families"):
            with transfer_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "generation": gen,
                            "child_id": child_id,
                            "source_families": parent_a.metadata.get("source_families"),
                            "target_families": families,
                            "before_feasible": parent_a.instances_feasible,
                            "after_feasible": panel_eval.instances_feasible,
                            "fingerprint": hash_sources(child_sources),
                        }
                    )
                    + "\n"
                )

        category, genuine = classify_attribution(attr_rows, child_sources)
        child = BundleCandidate(
            candidate_id=child_id,
            sources=child_sources,
            owners=owners,
            generation=gen,
            parent_ids=[p.candidate_id for p in parents],
            llm_generated=genuine > 0,
            genuine_llm_components=genuine,
            attribution_category=category,
            model=cfg.model,
            tokens=collector.total_tokens,
            source_hashes=hash_sources(child_sources),
            component_attribution=[{k: v for k, v in row.items() if k != "executed_source"} for row in attr_rows],
            metadata={
                "causal": causal,
                "source_families": families,
                "load_errors": errors,
                "panel_seeds": panel_seeds,
            },
        )
        apply_panel(child, panel_eval, validation_status="ok" if not errors else "invalid")
        archive.add(child)

        archive.llm_calls = collector.logical_calls
        archive.llm_tokens = collector.total_tokens
        archive.wall_s = collector.wall_s
        archive.save(checkpoint)

        record = {
            "generation": gen,
            "candidate_id": child.candidate_id,
            "fully_feasible_on_panel": child.fully_feasible_on_panel,
            "instances_feasible": child.instances_feasible,
            "instances_tested": child.instances_tested,
            "attribution_category": category,
            "genuine_llm_components": genuine,
            "llm_calls": collector.logical_calls,
            "llm_tokens": collector.total_tokens,
            "fingerprint": child.fingerprint(),
        }
        history.append(record)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

        if collector.stopped:
            break

    # Re-evaluate the best fully-feasible candidate on the full panel before freeze.
    best = archive.best()
    frozen_dir = work / "frozen_bundle"
    if best is not None:
        panel_eval, errors = evaluate_candidate_on_panel(
            best.sources,
            best.owners,
            panel,
            seeds=panel_seeds,
            time_limit_s=cfg.time_limit_s,
            alns_iterations=cfg.alns_iterations,
        )
        apply_panel(best, panel_eval, validation_status="ok" if not errors else "invalid")
        if best.fully_feasible_on_panel:
            typed = _typed_sources(best.sources)
            typed_owners = {k: best.owners.get(k, ROLE_FOR[k]) for k in typed}
            bundle, _ = load_bundle(typed, typed_owners)
            write_bundle(bundle, frozen_dir)
            (work / "frozen_meta.json").write_text(
                json.dumps(
                    {
                        "candidate_id": best.candidate_id,
                        "fully_feasible_on_panel": best.fully_feasible_on_panel,
                        "instances_tested": best.instances_tested,
                        "instances_feasible": best.instances_feasible,
                        "panel_instance_ids": [s.instance_id for s in panel],
                        "panel_seeds": panel_seeds,
                        "source_hashes": best.source_hashes,
                        "attribution_category": best.attribution_category,
                        "genuine_llm_components": best.genuine_llm_components,
                        "model": best.model,
                        "deployment_llm_calls": 0,
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        else:
            best = None

    archive.llm_calls = collector.logical_calls
    archive.llm_tokens = collector.total_tokens
    archive.wall_s = collector.wall_s
    archive.save(checkpoint)
    (work / "usage.json").write_text(json.dumps(collector.as_dict(), indent=2) + "\n", encoding="utf-8")

    result = {
        "experiment": "cv_mape_evolution",
        "seed": cfg.seed,
        "model": cfg.model,
        "generations_requested": cfg.generations,
        "generations_completed": len({h["generation"] for h in history}),
        "archive_size": len(archive.members),
        "llm_calls": collector.logical_calls,
        "llm_tokens": collector.total_tokens,
        "http_attempts": collector.http_attempts,
        "budget": collector.as_dict(),
        "use_critic": cfg.use_critic,
        "use_cross_variant_memory": cfg.use_cross_variant_memory,
        "panel_instance_ids": [s.instance_id for s in panel],
        "panel_seeds": panel_seeds,
        "best_fully_feasible_on_panel": bool(best.fully_feasible_on_panel) if best else False,
        "best_feasible": bool(best.fully_feasible_on_panel) if best else False,
        "best_instances_feasible": best.instances_feasible if best else 0,
        "best_instances_tested": best.instances_tested if best else 0,
        "best_candidate_id": best.candidate_id if best else None,
        "best_attribution_category": best.attribution_category if best else None,
        "frozen_bundle": str(frozen_dir) if best else "",
        "checkpoint": str(checkpoint),
        "history": history,
        "note": (
            "Panel-comparable fitness; lexicographic per-instance keys; "
            "best_feasible means fully_feasible_on_panel after re-evaluation. "
            "Default fallbacks are never counted as LLM discoveries."
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
