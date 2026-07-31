"""Milestone 10A — equal-budget LLM attribution vs non-LLM evolution."""

from __future__ import annotations

import json
import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from evocharge.evolution.run import load_m9b_config, run_evolution

GenerationMethod = Literal[
    "llm_guided",
    "structured",
    "random_mutation",
    "random_composition",
]

Conclusion = Literal[
    "LLM_GUIDANCE_SUPPORTED",
    "LLM_GUIDANCE_PARTIALLY_SUPPORTED",
    "NO_CLEAR_LLM_ADVANTAGE",
    "NON_LLM_SEARCH_SUPERIOR",
    "INSUFFICIENT_EVIDENCE",
]

METHODS: list[GenerationMethod] = [
    "llm_guided",
    "structured",
    "random_mutation",
    "random_composition",
]


def _arm_summary(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("metrics") or {}
    return {
        "experiment_id": run.get("experiment_id"),
        "generation_method": run.get("generation_method"),
        "seed": run.get("seed"),
        "freeze_hash": run.get("freeze_hash"),
        "candidates_evaluated": metrics.get("candidates_evaluated"),
        "useful_offspring": metrics.get("useful_offspring"),
        "useful_per_evaluated": metrics.get("useful_per_evaluated"),
        "mean_effective_rate_archive": metrics.get("mean_effective_rate_archive"),
        "archive_size": len(run.get("archive") or []),
        "rejected_count": run.get("rejected_count"),
        "llm_calls": metrics.get("llm_calls"),
        "llm_plan_latency_seconds": metrics.get("llm_plan_latency_seconds"),
        "success_flags": run.get("success_flags"),
    }


def aggregate_method(arms: list[dict[str, Any]]) -> dict[str, Any]:
    useful_rates = [float(a.get("useful_per_evaluated") or 0.0) for a in arms]
    eff = [float(a.get("mean_effective_rate_archive") or 0.0) for a in arms]
    arch = [int(a.get("archive_size") or 0) for a in arms]
    evals = [int(a.get("candidates_evaluated") or 0) for a in arms]
    llm_lat = [float(a.get("llm_plan_latency_seconds") or 0.0) for a in arms]
    llm_calls = [int(a.get("llm_calls") or 0) for a in arms]

    def _mean(xs: list[float]) -> float:
        return float(statistics.mean(xs)) if xs else 0.0

    def _stdev(xs: list[float]) -> float:
        return float(statistics.stdev(xs)) if len(xs) > 1 else 0.0

    return {
        "n_seeds": len(arms),
        "mean_useful_per_evaluated": _mean(useful_rates),
        "stdev_useful_per_evaluated": _stdev(useful_rates),
        "mean_effective_rate_archive": _mean(eff),
        "stdev_effective_rate_archive": _stdev(eff),
        "mean_archive_size": _mean([float(x) for x in arch]),
        "total_candidates_evaluated": sum(evals),
        "total_llm_calls": sum(llm_calls),
        "total_llm_plan_latency_seconds": sum(llm_lat),
        "arms": arms,
    }


def draw_conclusion(by_method: dict[str, dict[str, Any]]) -> tuple[Conclusion, list[str]]:
    """Evidence-based attribution conclusion (no marketing claims)."""
    notes: list[str] = []
    required = ("llm_guided", "structured", "random_mutation", "random_composition")
    missing = [m for m in required if m not in by_method or by_method[m].get("n_seeds", 0) < 1]
    if missing:
        return "INSUFFICIENT_EVIDENCE", [f"missing_method_runs:{','.join(missing)}"]

    llm = by_method["llm_guided"]
    structured = by_method["structured"]
    rand_mut = by_method["random_mutation"]
    rand_comp = by_method["random_composition"]

    llm_u = float(llm.get("mean_useful_per_evaluated") or 0.0)
    st_u = float(structured.get("mean_useful_per_evaluated") or 0.0)
    rm_u = float(rand_mut.get("mean_useful_per_evaluated") or 0.0)
    rc_u = float(rand_comp.get("mean_useful_per_evaluated") or 0.0)
    llm_e = float(llm.get("mean_effective_rate_archive") or 0.0)
    st_e = float(structured.get("mean_effective_rate_archive") or 0.0)

    notes.append(f"llm_useful_per_eval={llm_u:.4f}")
    notes.append(f"structured_useful_per_eval={st_u:.4f}")
    notes.append(f"random_mutation_useful_per_eval={rm_u:.4f}")
    notes.append(f"random_composition_useful_per_eval={rc_u:.4f}")

    non_llm_best = max(st_u, rm_u, rc_u)
    # Clear LLM win vs all non-LLM usefulness (+ archive effective rate not worse)
    if llm_u > non_llm_best + 0.05 and llm_e >= st_e - 0.02:
        notes.append("llm_exceeds_all_non_llm_usefulness_margins")
        return "LLM_GUIDANCE_SUPPORTED", notes
    # Partial: beats random arms but not structured
    if llm_u > max(rm_u, rc_u) + 0.03 and llm_u <= st_u + 0.02:
        notes.append("llm_beats_random_but_not_structured")
        return "LLM_GUIDANCE_PARTIALLY_SUPPORTED", notes
    # Non-LLM superior
    if st_u > llm_u + 0.05 or (non_llm_best > llm_u + 0.05):
        notes.append("non_llm_higher_useful_rate")
        return "NON_LLM_SEARCH_SUPERIOR", notes
    # Tie / no clear advantage
    if abs(llm_u - st_u) <= 0.05:
        notes.append("llm_and_structured_within_margin")
        return "NO_CLEAR_LLM_ADVANTAGE", notes
    return "INSUFFICIENT_EVIDENCE", notes + ["ambiguous_margins"]


def run_attribution_study(
    *,
    project_root: Path,
    config_path: Path,
    experiment_id: str | None = None,
    freeze_path: Path | None = None,
    llm_backend: str = "ollama",
    methods: list[GenerationMethod] | None = None,
) -> dict[str, Any]:
    cfg = load_m9b_config(config_path)
    pop = dict(cfg.get("population") or {})
    seeds = list(pop.get("paired_evolution_seeds") or [2027, 2028, 2029])
    methods = methods or list(METHODS)
    eid = experiment_id or f"m10a_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    root_dir = project_root / "artifacts" / "evolution" / eid
    root_dir.mkdir(parents=True, exist_ok=True)

    freeze = freeze_path or (
        project_root / "artifacts" / "evolution" / "m9b_main_20260728" / "freeze_manifest.json"
    )

    runs: list[dict[str, Any]] = []
    for method in methods:
        for seed in seeds:
            run_id = f"{eid}_{method}_s{seed}"
            backend = llm_backend if method == "llm_guided" else "structured"
            summary = run_evolution(
                project_root=project_root,
                config_path=config_path,
                experiment_id=run_id,
                backend=backend,
                generation_method=method,
                freeze_path=freeze if Path(freeze).is_file() else None,
                seed_override=int(seed),
            )
            arm = _arm_summary(summary)
            runs.append(arm)
            (root_dir / f"{method}_s{seed}_summary.json").write_text(
                json.dumps(arm, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    by_method: dict[str, dict[str, Any]] = {}
    for method in methods:
        arms = [r for r in runs if r.get("generation_method") == method]
        by_method[method] = aggregate_method(arms)

    # Equal budget check
    totals = [by_method[m]["total_candidates_evaluated"] for m in methods]
    equal_budget = len(set(totals)) == 1

    conclusion, notes = draw_conclusion(by_method)
    out = {
        "experiment_id": eid,
        "freeze_path": str(freeze),
        "freeze_hash": (
            json.loads(Path(freeze).read_text(encoding="utf-8")).get("freeze_hash")
            if Path(freeze).is_file()
            else None
        ),
        "methods": methods,
        "paired_evolution_seeds": seeds,
        "equal_candidate_evaluation_budget": equal_budget,
        "candidate_eval_totals_by_method": {
            m: by_method[m]["total_candidates_evaluated"] for m in methods
        },
        "by_method": by_method,
        "conclusion": conclusion,
        "conclusion_notes": notes,
        "model": (cfg.get("model") or {}).get("name"),
        "model_limitation_note": (cfg.get("model") or {}).get("model_limitation_note"),
        "replay_note": (
            "LLM arm plans/responses under each run's llm_calls/; "
            "replay with stronger model by setting model.name without changing non-LLM arms."
        ),
        "hidden_test_evaluation": False,
        "schneider_transfer": False,
        "optimization_claim": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (root_dir / "m10a_attribution_summary.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_script = project_root / "scripts" / "write_m10a_report.py"
    if report_script.is_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location("write_m10a_report", report_script)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.write_m10a_report(
                root_dir / "m10a_attribution_summary.json",
                project_root / "docs" / "reports" / "m10a_report.md",
            )
    return out
