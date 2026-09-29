"""One coding agent synthesizes an EVRPTW solver from scratch. Baseline for the five-agent team."""
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


def paired_token_ceiling(profile_id: str, seed: int) -> int | None:
    path = ROOT / "results" / "paper" / "synthesis" / f"{profile_id}_seed{seed}.json"
    if not path.exists():
        return None
    row = json.loads(path.read_text(encoding="utf-8"))
    return int(row.get("tokens") or 0)


def run_one(profile_id: str, seed: int, max_llm_calls: int, token_ceiling: int | None) -> dict:
    profile = resolve_profile(profile_id)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 300.0),
        num_ctx=profile.num_ctx,
        keep_alive="20m",
        seed=seed,
    )
    dest = ROOT / "results" / "paper" / "single_agent" / f"{profile_id}_seed{seed}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if availability(profile, backend) != "installed":
        report = {
            "experiment": "single_agent_synthesis",
            "model": profile.model,
            "profile": profile_id,
            "seed": seed,
            "failure_reason": "SKIPPED_NOT_INSTALLED",
            "schneider_c5": False,
            "fully_feasible": False,
            "llm_calls": 0,
            "tokens": 0,
            "published_solver": "",
        }
        dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"profile": profile_id, "seed": seed, "failure_reason": "SKIPPED_NOT_INSTALLED"}))
        return report
    workspace = ROOT / "workspace" / "single_agent_synthesis" / profile_id / f"seed{seed}"
    report = run_from_scratch(
        mode="single_agent",
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_calls=max_llm_calls,
        token_ceiling=token_ceiling,
    )
    report["profile"] = profile_id
    report["seed"] = seed
    source = Path(report["solver_path"])
    solver_out = ROOT / "results" / "paper" / "solvers" / "single_agent" / f"{profile_id}_seed{seed}"
    if source.exists() and source.read_text(encoding="utf-8").strip():
        solver_out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, solver_out / "solver.py")
        report["published_solver"] = str(solver_out.relative_to(ROOT)).replace("\\", "/")
    else:
        report["published_solver"] = ""
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("profile", "seed", "schneider_c5", "failure_reason", "llm_calls")}))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    cfg = _config()
    profile_id = args.profile or cfg["single_agent_synthesis"]["profile"]
    paired = str(cfg["single_agent_synthesis"].get("paired_profile") or profile_id)
    budget = int(cfg.get("max_llm_calls") or 80)
    seeds = cfg["single_agent_synthesis"]["seeds"]
    if args.all:
        for seed in seeds:
            dest = ROOT / "results" / "paper" / "single_agent" / f"{profile_id}_seed{int(seed)}.json"
            if dest.exists():
                print(f"keep existing {dest.name}", flush=True)
                continue
            ceiling = paired_token_ceiling(paired, int(seed))
            if ceiling is None:
                raise SystemExit(f"missing five-agent tokens for {paired} seed {seed}")
            try:
                run_one(profile_id, int(seed), budget, ceiling)
            except Exception as error:  # noqa: BLE001
                dest.write_text(
                    json.dumps(
                        {
                            "experiment": "single_agent_synthesis",
                            "profile": profile_id,
                            "seed": int(seed),
                            "failure_reason": str(error)[:500],
                            "failure_category": "RUNTIME",
                            "schneider_c5": False,
                            "fully_feasible": False,
                            "llm_calls": 0,
                            "tokens": 0,
                            "token_ceiling": ceiling,
                        }
                    ),
                    encoding="utf-8",
                )
                print(f"recorded crash seed {seed}: {error}", flush=True)
        return
    if not args.seed:
        raise SystemExit("pass --all or --seed")
    ceiling = paired_token_ceiling(paired, args.seed)
    if ceiling is None:
        raise SystemExit(f"missing five-agent tokens for {paired} seed {args.seed}")
    run_one(profile_id, args.seed, budget, ceiling)


if __name__ == "__main__":
    main()
