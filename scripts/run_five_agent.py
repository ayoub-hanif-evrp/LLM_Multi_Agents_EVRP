"""Five agents, one local model, synthesize an EVRPTW solver from scratch."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402
from evrptw_autolab.synthesis.from_scratch import run_from_scratch  # noqa: E402


def _config() -> dict:
    return yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}


def _publish(report: dict, profile_id: str, seed: int) -> dict:
    dest = ROOT / "results" / "paper" / "synthesis" / f"{profile_id}_seed{seed}.json"
    solver_out = ROOT / "results" / "paper" / "solvers" / "five_agent" / f"{profile_id}_seed{seed}"
    source = Path(report["solver_path"])
    if source.exists() and source.read_text(encoding="utf-8").strip():
        solver_out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, solver_out / "solver.py")
        report["published_solver"] = str(solver_out.relative_to(ROOT)).replace("\\", "/")
    else:
        report["published_solver"] = ""
    report["profile"] = profile_id
    report["seed"] = seed
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("profile", "seed", "schneider_c5", "failure_reason", "llm_calls")}))
    return report


def run_one(profile_id: str, seed: int, max_llm_calls: int) -> dict:
    profile = resolve_profile(profile_id)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 300.0),
        num_ctx=profile.num_ctx,
        keep_alive="20m",
        seed=seed,
    )
    if availability(profile, backend) != "installed":
        report = {
            "experiment": "five_agent_synthesis",
            "model": profile.model,
            "profile": profile_id,
            "seed": seed,
            "executable": False,
            "routing": False,
            "charging": False,
            "multi_customer": False,
            "schneider_c5": False,
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "tokens": 0,
            "failure_reason": "SKIPPED_NOT_INSTALLED",
            "feasible": 0,
            "c5_total": 0,
            "fully_feasible": False,
            "vehicles": None,
            "distance": None,
            "solver_hash": "",
            "wall_s": 0,
            "solver_path": "",
            "published_solver": "",
        }
        dest = ROOT / "results" / "paper" / "synthesis" / f"{profile_id}_seed{seed}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"profile": profile_id, "seed": seed, "failure_reason": report["failure_reason"]}))
        return report
    workspace = ROOT / "workspace" / "five_agent_synthesis" / profile_id / f"seed{seed}"
    report = run_from_scratch(
        mode="five_agent",
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_calls=max_llm_calls,
    )
    return _publish(report, profile_id, seed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    cfg = _config()
    budget = int(cfg.get("max_llm_calls") or 80)
    if args.all:
        for spec in cfg["five_agent_synthesis"]["runs"]:
            profile_id = str(spec["profile"])
            for seed in spec["seeds"]:
                dest = ROOT / "results" / "paper" / "synthesis" / f"{profile_id}_seed{int(seed)}.json"
                if dest.exists():
                    print(f"keep existing {dest.name}", flush=True)
                    continue
                try:
                    run_one(profile_id, int(seed), budget)
                except Exception as error:  # noqa: BLE001
                    dest.write_text(
                        json.dumps(
                            {
                                "experiment": "five_agent_synthesis",
                                "profile": profile_id,
                                "seed": int(seed),
                                "failure_reason": str(error)[:500],
                                "failure_category": "RUNTIME",
                                "schneider_c5": False,
                                "fully_feasible": False,
                                "llm_calls": 0,
                                "tokens": 0,
                            }
                        ),
                        encoding="utf-8",
                    )
                    print(f"recorded crash {profile_id} seed {seed}: {error}", flush=True)
        return
    if not args.profile or not args.seed:
        raise SystemExit("pass --all or both --profile and --seed")
    run_one(args.profile, args.seed, budget)


if __name__ == "__main__":
    main()
