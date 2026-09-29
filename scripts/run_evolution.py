"""Evolve a valid synthesized solver with small code patches. No named metaheuristic is prescribed."""
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


def _config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}


def _load_rows() -> list[dict]:
    rows = []
    for folder in ("synthesis", "single_agent"):
        directory = ROOT / "results" / "paper" / folder
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def best_parent(rows: list[dict]) -> dict | None:
    ranked = []
    for row in rows:
        published = row.get("published_solver") or ""
        solver = ROOT / published if published else Path(row.get("solver_path") or "")
        if not solver.exists():
            continue
        if not row.get("fully_feasible"):
            continue
        ranked.append((row, solver))
    if not ranked:
        return None
    ranked.sort(
        key=lambda item: (
            item[0].get("vehicles") if item[0].get("vehicles") is not None else 10**9,
            item[0].get("distance") if item[0].get("distance") is not None else 10**12,
        )
    )
    row, solver = ranked[0]
    return {**row, "parent_file": str(solver)}


def run_one(profile_id: str, seed: int, parent: Path, cfg: dict) -> dict:
    profile = resolve_profile(profile_id)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 300.0),
        num_ctx=profile.num_ctx,
        keep_alive="20m",
        seed=seed,
    )
    dest = ROOT / "results" / "paper" / "evolution" / f"{profile_id}_seed{seed}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if availability(profile, backend) != "installed":
        report = {"experiment": "solver_evolution", "profile": profile_id, "seed": seed, "failure_reason": "SKIPPED_NOT_INSTALLED"}
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report
    evo = cfg["solver_evolution"]
    workspace = ROOT / "workspace" / "solver_evolution" / profile_id / f"seed{seed}"
    result = run_evolution(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        parent_solver=parent,
        max_generations=int(evo.get("max_generations") or 8),
        candidates_per_role=int(evo.get("candidates_per_role") or 1),
        beam_size=int(evo.get("beam_size") or 2),
        max_llm_calls=int(evo.get("max_llm_calls") or cfg.get("max_llm_calls") or 80),
        seed_base=seed,
        campaign_id=f"seed{seed}",
    )
    solver_out = ROOT / "results" / "paper" / "solvers" / "evolution" / f"{profile_id}_seed{seed}"
    best = Path(result["best_path"])
    if best.exists():
        solver_out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(best, solver_out / "solver.py")
    all_c5 = result.get("all_c5") or {}
    fully = bool(all_c5.get("feasible") == all_c5.get("total") and all_c5.get("total"))
    report = {
        "experiment": "solver_evolution",
        "model": profile.model,
        "profile": profile_id,
        "seed": seed,
        "parent": str(parent),
        "improved": bool(result.get("improved_vs_parent")),
        "fully_feasible": fully,
        "feasible": all_c5.get("feasible"),
        "c5_total": all_c5.get("total"),
        "vehicles": all_c5.get("vehicles_sum") if fully else None,
        "distance": all_c5.get("distance_sum") if fully else None,
        "solver_hash": result.get("best_hash"),
        "llm_calls": result.get("llm_calls"),
        "prompt_tokens": result.get("prompt_tokens"),
        "completion_tokens": result.get("completion_tokens"),
        "tokens": result.get("tokens"),
        "wall_s": result.get("wall_s"),
        "trajectory_vehicles": result.get("trajectory_vehicles"),
        "failure_reason": "" if fully else "not fully feasible on all C5",
        "published_solver": str(solver_out.relative_to(ROOT)).replace("\\", "/") if best.exists() else "",
    }
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("profile", "seed", "improved", "vehicles", "fully_feasible")}))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--parent", type=Path, default=None)
    args = parser.parse_args()
    cfg = _config()
    profile_id = cfg["solver_evolution"]["profile"]
    parent_row = None
    parent = args.parent
    if parent is None:
        parent_row = best_parent(_load_rows())
        if parent_row is None:
            note = {
                "experiment": "solver_evolution",
                "failure_reason": "no valid synthesized solver to evolve",
            }
            dest = ROOT / "results" / "paper" / "evolution" / "no_parent.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(note, indent=2), encoding="utf-8")
            print(json.dumps(note))
            return
        parent = Path(parent_row["parent_file"])
    if args.all:
        for seed in cfg["solver_evolution"]["seeds"]:
            dest = ROOT / "results" / "paper" / "evolution" / f"{profile_id}_seed{int(seed)}.json"
            if dest.exists():
                print(f"keep existing {dest.name}", flush=True)
                continue
            try:
                run_one(profile_id, int(seed), parent, cfg)
            except Exception as error:  # noqa: BLE001
                dest.write_text(
                    json.dumps(
                        {
                            "experiment": "solver_evolution",
                            "profile": profile_id,
                            "seed": int(seed),
                            "failure_reason": str(error)[:500],
                            "failure_category": "RUNTIME",
                            "improved": False,
                            "fully_feasible": False,
                        }
                    ),
                    encoding="utf-8",
                )
                print(f"recorded crash seed {seed}: {error}", flush=True)
        return
    if not args.seed:
        raise SystemExit("pass --all or --seed")
    run_one(profile_id, args.seed, parent, cfg)


if __name__ == "__main__":
    main()
