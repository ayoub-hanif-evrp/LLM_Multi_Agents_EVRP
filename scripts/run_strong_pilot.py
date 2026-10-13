"""Strong local coding-model selection pilot (development instances only)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.evolution import run_evolution  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402
from evrptw_autolab.synthesis.from_scratch import (  # noqa: E402
    copy_run_provenance,
    run_from_scratch,
)
from evrptw_autolab.synthesis.provenance import (  # noqa: E402
    should_reuse_result,
    stamp_report,
)


def _config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _maybe_evolve(report: dict, profile_id: str, seed: int, cfg: dict) -> dict | None:
    """If G4 is 4/4, evolve the frozen parent with the same strong local model."""
    if not report.get("schneider_c5"):
        return None
    published = report.get("published_solver") or ""
    parent = ROOT / published if published else ROOT / str(report.get("solver_path") or "")
    if not parent.exists():
        return None
    profile = resolve_profile(profile_id)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 600.0),
        num_ctx=profile.num_ctx or 8192,
        keep_alive="20m",
        seed=seed,
    )
    evo_cfg = cfg.get("solver_evolution") or {}
    workspace = ROOT / "workspace" / "strong_pilot_evolution" / profile_id / f"seed{seed}"
    result = run_evolution(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        parent_solver=parent,
        max_generations=int(evo_cfg.get("max_generations") or 8),
        candidates_per_role=int(evo_cfg.get("candidates_per_role") or 2),
        beam_size=int(evo_cfg.get("beam_size") or 2),
        max_llm_calls=int(evo_cfg.get("max_llm_calls") or 80),
        seed_base=seed,
        campaign_id=f"strong_pilot_seed{seed}",
    )
    solver_out = ROOT / "results" / "strong_pilot" / "evolution" / f"{profile_id}_seed{seed}"
    best = Path(result["best_path"])
    if best.exists():
        solver_out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best, solver_out / "solver.py")
    all_c5 = result.get("all_c5") or {}
    fully = bool(all_c5.get("feasible") == all_c5.get("total") and all_c5.get("total"))
    evo_report = {
        "experiment": "strong_pilot_evolution",
        "profile": profile_id,
        "seed": seed,
        "model": profile.model,
        "parent": _rel(parent),
        "improved": bool(result.get("improved_vs_parent")),
        "fully_feasible": fully,
        "feasible": all_c5.get("feasible"),
        "c5_total": all_c5.get("total"),
        "vehicles": all_c5.get("vehicles_sum") if fully else None,
        "distance": all_c5.get("distance_sum") if fully else None,
        "solver_hash": result.get("best_hash"),
        "llm_calls": result.get("llm_calls"),
        "tokens": result.get("tokens"),
        "wall_s": result.get("wall_s"),
        "published_solver": _rel(solver_out / "solver.py") if best.exists() else "",
    }
    dest = ROOT / "results" / "strong_pilot" / f"{profile_id}_seed{seed}_evolution.json"
    dest.write_text(json.dumps(evo_report, indent=2), encoding="utf-8")
    print(json.dumps({"evolution": {k: evo_report[k] for k in ("profile", "seed", "vehicles", "fully_feasible", "improved")}}), flush=True)
    return evo_report


def run_one(profile_id: str, seed: int, max_llm_calls: int, token_ceiling: int, cfg: dict) -> dict:
    profile = resolve_profile(profile_id)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 600.0),
        num_ctx=profile.num_ctx or 8192,
        keep_alive="20m",
        seed=seed,
    )
    dest = ROOT / "results" / "strong_pilot" / f"{profile_id}_seed{seed}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if availability(profile, backend) != "installed":
        report = {
            "experiment": "strong_model_pilot",
            "profile": profile_id,
            "seed": seed,
            "model": profile.model,
            "failure_reason": "SKIPPED_NOT_INSTALLED",
            "schneider_c5": False,
            "fully_feasible": False,
            "best_g4_feasible": 0,
            "llm_calls": 0,
            "tokens": 0,
            "label": "stronger local coding-model anchor",
        }
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
        return report
    workspace = ROOT / "workspace" / "strong_pilot" / profile_id / f"seed{seed}"
    report = run_from_scratch(
        mode="five_agent",
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_calls=max_llm_calls,
        token_ceiling=token_ceiling,
        repo_root=ROOT,
    )
    report["experiment"] = "strong_model_pilot"
    report["profile"] = profile_id
    report["seed"] = seed
    report["label"] = "stronger local coding-model anchor"
    report.setdefault("model_tag", report.get("model") or "")
    report.setdefault("model_digest", report.get("model_digest") or "")
    report["published_solver"] = ""
    if report.get("solver_hash"):
        solver_out = ROOT / "results" / "strong_pilot" / "solvers" / f"{profile_id}_seed{seed}"
        source = ROOT / str(report.get("solver_path") or "")
        if not source.exists():
            source = workspace / "committed" / "solver.py"
        if source.exists() and source.read_text(encoding="utf-8").strip():
            solver_out.mkdir(parents=True, exist_ok=True)
            solver_out.joinpath("solver.py").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            report["published_solver"] = _rel(solver_out / "solver.py")
    if report.get("solver_path"):
        report["solver_path"] = str(report["solver_path"]).replace("\\", "/")
    report = stamp_report(report, ROOT)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    copy_run_provenance(
        workspace,
        ROOT / "results" / "strong_pilot" / "raw" / f"{profile_id}_seed{seed}",
        report,
    )
    summary = {
        k: report.get(k)
        for k in (
            "profile",
            "seed",
            "deepest_gate",
            "curriculum_g4_best",
            "best_g4_feasible",
            "posthoc_g4_score",
            "g4_feasible",
            "schneider_c5",
            "confirmation_feasible",
            "confirmation_total",
            "fully_feasible",
            "failure_category",
            "failure_reason",
            "llm_calls",
            "tokens",
            "solver_hash",
        )
    }
    print(json.dumps(summary), flush=True)
    if report.get("schneider_c5"):
        evo = _maybe_evolve(report, profile_id, seed, cfg)
        if evo is not None:
            report["evolution"] = {
                "vehicles": evo.get("vehicles"),
                "fully_feasible": evo.get("fully_feasible"),
                "improved": evo.get("improved"),
                "solver_hash": evo.get("solver_hash"),
            }
            dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _write_summary(profiles: list[str], seeds: list[int]) -> None:
    rows = []
    for profile_id in profiles:
        for seed in seeds:
            path = ROOT / "results" / "strong_pilot" / f"{profile_id}_seed{int(seed)}.json"
            if path.exists():
                rows.append(json.loads(path.read_text(encoding="utf-8")))
    summary = {
        "experiment": "strong_model_pilot",
        "label": "stronger local coding-model anchors",
        "n_runs": len(rows),
        "runs": [
            {
                "profile": r.get("profile"),
                "model": r.get("model"),
                "seed": r.get("seed"),
                "deepest_gate": r.get("deepest_gate"),
                "curriculum_g4_best": r.get("curriculum_g4_best"),
                "best_g4_feasible": r.get("best_g4_feasible"),
                "posthoc_g4_score": r.get("posthoc_g4_score"),
                "g4_feasible": r.get("g4_feasible"),
                "schneider_c5": r.get("schneider_c5"),
                "confirmation_feasible": r.get("confirmation_feasible"),
                "confirmation_total": r.get("confirmation_total"),
                "fully_feasible": r.get("fully_feasible"),
                "llm_calls": r.get("llm_calls"),
                "tokens": r.get("tokens"),
                "solver_hash": r.get("solver_hash"),
                "evolution": r.get("evolution"),
                "failure_reason": (r.get("failure_reason") or "")[:200],
            }
            for r in rows
        ],
    }
    out = ROOT / "results" / "strong_pilot" / "SUMMARY.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({"summary_written": _rel(out), "n_runs": len(rows)}), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    cfg = _config()
    pilot = cfg.get("strong_model_pilot") or {}
    max_calls = int(pilot.get("max_llm_calls") or 120)
    token_ceiling = int(pilot.get("token_ceiling") or 300000)
    seeds = [int(s) for s in (pilot.get("seeds") or [11, 22, 33])]
    profiles = list(pilot.get("profiles") or ["devstral_small_2_24b", "qwen3_coder_30b"])
    if args.all:
        for profile_id in profiles:
            for seed in seeds:
                dest = ROOT / "results" / "strong_pilot" / f"{profile_id}_seed{seed}.json"
                if should_reuse_result(dest, ROOT):
                    print(f"keep existing {dest.name}", flush=True)
                    continue
                if dest.exists():
                    dest.unlink()
                try:
                    run_one(str(profile_id), seed, max_calls, token_ceiling, cfg)
                except Exception as error:  # noqa: BLE001
                    dest.write_text(
                        json.dumps(
                            {
                                "experiment": "strong_model_pilot",
                                "profile": profile_id,
                                "seed": seed,
                                "failure_reason": str(error)[:500],
                                "failure_category": "RUNTIME",
                                "schneider_c5": False,
                                "best_g4_feasible": 0,
                                "llm_calls": 0,
                                "tokens": 0,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    print(f"recorded crash {profile_id} seed {seed}: {error}", flush=True)
        _write_summary(profiles, seeds)
        return
    if not args.profile or not args.seed:
        raise SystemExit("pass --all or both --profile and --seed")
    run_one(args.profile, args.seed, max_calls, token_ceiling, cfg)
    _write_summary(profiles, seeds)


if __name__ == "__main__":
    main()
