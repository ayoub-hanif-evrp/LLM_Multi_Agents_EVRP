"""Experiment B pilot: structured_synthesis on configured profiles/seeds."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.llm.registry import (  # noqa: E402
    SKIPPED_NO_CREDENTIAL,
    SKIPPED_NOT_INSTALLED,
    availability,
    make_backend,
    resolve_profile,
)
from evrptw_autolab.structured.run import (  # noqa: E402
    copy_structured_provenance,
    run_structured_synthesis,
)
from evrptw_autolab.synthesis.provenance import should_reuse_result, stamp_report  # noqa: E402

RESULTS = ROOT / "results" / "structured"


def _config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _ensure_layout() -> None:
    for sub in ("raw", "solvers"):
        (RESULTS / sub).mkdir(parents=True, exist_ok=True)
    readme = RESULTS / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Structured synthesis results (Experiment B)\n\n"
            "Pilot and campaign outputs for `structured_synthesis`.\n"
            "Never write Experiment A artifacts here; never write to `results/paper/`.\n",
            encoding="utf-8",
        )


def _append_runs_csv(row: dict) -> None:
    path = RESULTS / "runs.csv"
    fields = [
        "profile",
        "seed",
        "model",
        "ablation",
        "deepest_gate",
        "best_g4_feasible",
        "schneider_c5",
        "llm_calls",
        "tokens",
        "solver_hash",
        "failure_reason",
    ]
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({k: row.get(k) for k in fields})


def run_one(profile_id: str, seed: int, cfg: dict, *, ablation: str = "full") -> dict:
    _ensure_layout()
    block = cfg.get("structured_synthesis") or {}
    max_calls = int(block.get("max_llm_calls") or 400)
    token_ceiling = block.get("token_ceiling")
    token_ceiling_i = int(token_ceiling) if token_ceiling is not None else None
    dest = RESULTS / f"{profile_id}_seed{seed}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)

    profile = resolve_profile(profile_id)
    status = availability(profile)
    if status in {SKIPPED_NO_CREDENTIAL, SKIPPED_NOT_INSTALLED, "SKIPPED_OLLAMA_UNAVAILABLE"}:
        report = {
            "experiment": "structured_synthesis",
            "profile": profile_id,
            "seed": seed,
            "model": profile.model,
            "ablation": ablation,
            "failure_reason": status if status != SKIPPED_NOT_INSTALLED else status,
            "failure_category": status,
            "schneider_c5": False,
            "fully_feasible": False,
            "best_g4_feasible": 0,
            "llm_calls": 0,
            "tokens": 0,
            "executable": False,
        }
        if status == SKIPPED_NO_CREDENTIAL or "CREDENTIAL" in status:
            report["failure_reason"] = SKIPPED_NO_CREDENTIAL
            report["failure_category"] = SKIPPED_NO_CREDENTIAL
        report = stamp_report(report, ROOT)
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        _append_runs_csv(report)
        print(json.dumps(report), flush=True)
        return report

    backend = make_backend(profile)
    workspace = ROOT / "workspace" / "structured_synthesis" / profile_id / f"seed{seed}"
    report = run_structured_synthesis(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_calls=max_calls,
        token_ceiling=token_ceiling_i,
        max_generations=int(block.get("max_generations") or 12),
        archive_size=int(block.get("archive_size") or 8),
        offspring_per_generation=int(block.get("offspring_per_generation") or 12),
        repo_root=ROOT,
        seed=seed,
        ablation=ablation,
    )
    report["profile"] = profile_id
    report["seed"] = seed
    report["published_solver"] = ""
    if report.get("solver_hash"):
        solver_out = RESULTS / "solvers" / f"{profile_id}_seed{seed}"
        source = ROOT / str(report.get("solver_path") or "")
        if not source.exists():
            source = workspace / "committed" / "solver.py"
        if source.exists() and source.read_text(encoding="utf-8").strip():
            solver_out.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, solver_out / "solver.py")
            report["published_solver"] = _rel(solver_out / "solver.py")
    report = stamp_report(report, ROOT)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    copy_structured_provenance(
        workspace,
        RESULTS / "raw" / f"{profile_id}_seed{seed}",
        report,
    )
    _append_runs_csv(report)
    print(json.dumps({k: report.get(k) for k in (
        "profile", "seed", "deepest_gate", "best_g4_feasible", "schneider_c5",
        "llm_calls", "tokens", "failure_reason", "solver_hash",
    )}), flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--ablation", default="full")
    args = parser.parse_args()
    cfg = _config()
    block = cfg.get("structured_synthesis") or {}
    pilot = block.get("pilot") or {}
    seeds = [int(s) for s in (pilot.get("seeds") or [11, 22, 33])]
    profiles = list(pilot.get("profiles") or [])
    _ensure_layout()
    if args.all:
        for profile_id in profiles:
            for seed in seeds:
                dest = RESULTS / f"{profile_id}_seed{seed}.json"
                if should_reuse_result(dest, ROOT):
                    print(f"keep existing {dest.name}", flush=True)
                    continue
                if dest.exists():
                    dest.unlink()
                try:
                    run_one(str(profile_id), seed, cfg, ablation=args.ablation)
                except Exception as error:  # noqa: BLE001
                    crash = {
                        "experiment": "structured_synthesis",
                        "profile": profile_id,
                        "seed": seed,
                        "failure_reason": str(error)[:500],
                        "failure_category": "RUNTIME",
                        "schneider_c5": False,
                        "best_g4_feasible": 0,
                        "llm_calls": 0,
                        "tokens": 0,
                    }
                    dest.write_text(json.dumps(crash, indent=2), encoding="utf-8")
                    print(f"recorded crash {profile_id} seed {seed}: {error}", flush=True)
        return
    if not args.profile or not args.seed:
        raise SystemExit("pass --all or both --profile and --seed")
    run_one(args.profile, args.seed, cfg, ablation=args.ablation)


if __name__ == "__main__":
    main()
