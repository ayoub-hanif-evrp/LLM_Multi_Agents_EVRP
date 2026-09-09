"""Equal-budget repair/evolution. Each model is isolated so one hang cannot stall the rest."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

from evrptw_autolab.evaluation.fidelity import by_customer_count, load_all, split_instances
from evrptw_autolab.evaluation.runner import check_f0, evaluate_fidelity
from evrptw_autolab.experiments.synthesis_campaign import run_campaign
from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.registry import SKIPPED_NOT_INSTALLED, availability, resolve_profile
from evrptw_autolab.sandbox.limits import RunLimits

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "runs"
TAB = ROOT / "results" / "md" / "tables"
MD_RAW = TAB / "raw_autolab"


def _write_row(row: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    MD_RAW.mkdir(parents=True, exist_ok=True)
    text = json.dumps(row, indent=2, default=str)
    (RAW / f"evolve_{row['model_id']}.json").write_text(text, encoding="utf-8")
    (MD_RAW / f"evolve_{row['model_id']}.json").write_text(text, encoding="utf-8")


def run_one(model_id: str, cycles: int) -> dict:
    profile = resolve_profile(model_id)
    ollama = OllamaBackend()
    status = availability(profile, ollama)
    row: dict = {
        "model_id": model_id,
        "model": profile.model,
        "team_mode": "five_agent",
        "status": status,
        "cycles": cycles,
        "wall_s": 0.0,
        "elite_id": "",
        "f0_ok": False,
        "f1_feasible_rate": "",
        "f1_crashes": "",
        "f2_feasible_rate": "",
        "error": "",
    }
    if status != "installed":
        print(f"{SKIPPED_NOT_INSTALLED}: {profile.model}", flush=True)
        _write_row(row)
        return row
    discovery = split_instances(load_all())["discovery"]
    smoke = by_customer_count(discovery, [5])
    t0 = time.monotonic()
    workspace = ROOT / "workspace" / "repair" / model_id
    backend = OllamaBackend(timeout_s=120.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    print(f"discover {model_id} cycles={cycles} ...", flush=True)
    try:
        state = run_campaign(
            model=profile.model,
            backend=backend,
            workspace=workspace,
            cycles=cycles,
            campaign_id="repair",
            model_id=model_id,
            temperatures=profile.temperatures,
        )
        elite_dir = workspace / "candidates" / str(state.elite_id)
        f0 = check_f0(elite_dir) if elite_dir.exists() else ["missing:elite"]
        f1 = evaluate_fidelity(
            elite_dir, smoke, "F1", seeds=[0], limits=RunLimits(wall_clock_s=8.0), max_instances=8
        )
        summary = f1.get("summary") or {}
        row.update(
            {
                "status": "ran",
                "wall_s": round(time.monotonic() - t0, 1),
                "elite_id": state.elite_id,
                "cycle": state.cycle,
                "f0_ok": not f0,
                "f0_errors": f0,
                "f1_feasible_rate": summary.get("feasible_rate"),
                "f1_crashes": summary.get("crashes"),
                "f1": f1,
                "activated_history": state.activated_history,
            }
        )
        if float(summary.get("feasible_rate") or 0) > 0:
            f2 = evaluate_fidelity(
                elite_dir,
                discovery,
                "F2",
                seeds=[0],
                limits=RunLimits(wall_clock_s=8.0),
                max_instances=8,
            )
            row["f2"] = f2
            row["f2_feasible_rate"] = (f2.get("summary") or {}).get("feasible_rate")
        print(
            f"  elite={state.elite_id} f0_ok={row['f0_ok']} "
            f"f1_feasible={row['f1_feasible_rate']} crashes={row['f1_crashes']}",
            flush=True,
        )
    except Exception as error:  # noqa: BLE001
        row["status"] = "failed"
        row["error"] = str(error)[-1500:]
        row["wall_s"] = round(time.monotonic() - t0, 1)
        print(f"FAILED {model_id}: {error}", flush=True)
    _write_row(row)
    return row


def write_summary(rows: list[dict], elapsed_s: float, cycles: int) -> None:
    TAB.mkdir(parents=True, exist_ok=True)
    keys = [
        "model_id",
        "model",
        "team_mode",
        "status",
        "cycles",
        "wall_s",
        "elite_id",
        "f0_ok",
        "f1_feasible_rate",
        "f1_crashes",
        "f2_feasible_rate",
    ]
    lines = [",".join(keys)]
    for row in rows:
        lines.append(",".join(str(row.get(k, "")).replace(",", ";") for k in keys))
    (TAB / "autolab_evolution.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {
        "elapsed_s": elapsed_s,
        "cycles": cycles,
        "timestamp": datetime.now(UTC).isoformat(),
        "n_models": len(rows),
    }
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "evolve_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (MD_RAW / "evolve_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="")
    parser.add_argument("--cycles", type=int, default=0)
    args = parser.parse_args()
    experiments = yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}
    cycles = args.cycles or int((experiments.get("discover") or {}).get("cycles") or 5)
    if args.model_id:
        run_one(args.model_id, cycles)
        return
    model_ids = list((experiments.get("model_comparison") or {}).get("model_ids") or [])
    started = time.monotonic()
    rows: list[dict] = []
    per_model_s = 1320
    for model_id in model_ids:
        profile = resolve_profile(model_id)
        ollama = OllamaBackend()
        status = availability(profile, ollama)
        if status != "installed":
            rows.append(run_one(model_id, cycles))
            continue
        print(f"spawn {model_id} timeout={per_model_s}s", flush=True)
        try:
            completed = subprocess.run(
                [sys.executable, str(Path(__file__)), "--model-id", model_id, "--cycles", str(cycles)],
                cwd=str(ROOT),
                env={**os.environ, "PYTHONPATH": "src", "PYTHONUNBUFFERED": "1"},
                timeout=per_model_s,
                check=False,
            )
            path = RAW / f"evolve_{model_id}.json"
            if path.exists():
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            else:
                rows.append(
                    {
                        "model_id": model_id,
                        "model": profile.model,
                        "status": "failed",
                        "error": f"no output file, exit={completed.returncode}",
                        "cycles": cycles,
                    }
                )
        except subprocess.TimeoutExpired:
            print(f"TIMEOUT {model_id} after {per_model_s}s", flush=True)
            path = RAW / f"evolve_{model_id}.json"
            if path.exists():
                row = json.loads(path.read_text(encoding="utf-8"))
                row["status"] = "timeout"
                row["error"] = f"per-model wall clock exceeded {per_model_s}s"
                _write_row(row)
                rows.append(row)
            else:
                row = {
                    "model_id": model_id,
                    "model": profile.model,
                    "status": "timeout",
                    "error": f"per-model wall clock exceeded {per_model_s}s",
                    "cycles": cycles,
                }
                _write_row(row)
                rows.append(row)
    write_summary(rows, round(time.monotonic() - started, 1), cycles)
    print("done", round(time.monotonic() - started, 1), "s")


if __name__ == "__main__":
    main()
