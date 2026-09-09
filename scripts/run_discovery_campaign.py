"""Clean VoltForge discovery campaign: five agents, discovery partition only, no hidden solver.

Usage:
    python scripts/run_discovery_campaign.py
    python scripts/run_discovery_campaign.py --model qwen25_coder_7b --cycles 15
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evrptw_autolab.evaluation.fidelity import by_customer_count, load_all, split_instances
from evrptw_autolab.evaluation.runner import check_f0, evaluate_fidelity
from evrptw_autolab.experiments.synthesis_campaign import run_campaign
from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.registry import SKIPPED_NOT_INSTALLED, availability, resolve_profile
from evrptw_autolab.orchestration.trajectory import load_trajectories
from evrptw_autolab.sandbox.limits import limits_from_synthesis
from evrptw_autolab.sandbox.runner import run_solver

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen25_coder_7b")
    parser.add_argument("--cycles", type=int, default=None)
    parser.add_argument("--campaign-id", default="discovery")
    args = parser.parse_args()
    experiments = yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}
    cfg = experiments.get("discover") or {}
    cycles = int(args.cycles if args.cycles is not None else cfg.get("cycles") or 15)
    work_root = str(cfg.get("workspace") or "workspace/discovery")
    profile = resolve_profile(args.model)
    status = availability(profile)
    if status != "installed":
        raise SystemExit(f"{SKIPPED_NOT_INSTALLED}: {profile.model}")
    split = split_instances(load_all())
    discovery = split["discovery"]
    smoke = by_customer_count(discovery, [5])
    by_id = {i.instance_id: i for i in smoke}
    limits = limits_from_synthesis()
    workspace = ROOT / work_root / profile.id
    backend = OllamaBackend(timeout_s=150.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="15m")
    started = time.monotonic()
    print(f"discovery {profile.id} cycles={cycles} wall={limits.wall_clock_s}s", flush=True)
    state = run_campaign(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        cycles=cycles,
        campaign_id=args.campaign_id,
        model_id=profile.id,
        temperatures=profile.temperatures,
    )
    elite_dir = workspace / "candidates" / str(state.elite_id)
    f0 = check_f0(elite_dir) if elite_dir.exists() else ["missing:elite"]
    f1 = evaluate_fidelity(elite_dir, discovery, "F1", seeds=[0], limits=limits)
    c101 = run_solver(elite_dir, by_id["c101C5"], seed=0, limits=limits) if "c101C5" in by_id else None
    payload = {
        "campaign": args.campaign_id,
        "model_id": profile.id,
        "model": profile.model,
        "team_mode": "five_agent",
        "cycles": state.cycle,
        "elite_id": state.elite_id,
        "wall_s": round(time.monotonic() - started, 1),
        "f0_ok": not f0,
        "f1_feasible_rate": (f1.get("summary") or {}).get("feasible_rate"),
        "c101C5_feasible": None if c101 is None else c101.feasible,
        "c101C5_vehicles": None if c101 is None else c101.vehicles,
        "c101C5_distance": None if c101 is None else round(c101.total_distance, 2),
        "c101C5_first_fault": None if c101 is None else c101.first_fault,
        "timestamp": datetime.now(UTC).isoformat(),
        "trajectories": load_trajectories(workspace),
        "activated_history": state.activated_history,
    }
    out = ROOT / "results" / "runs" / f"{args.campaign_id}_{profile.id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in payload if k not in {"trajectories", "activated_history"}}, indent=2))
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
