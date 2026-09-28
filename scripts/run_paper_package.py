"""Run the VoltForge experimental package and store paper-facing results.

Does not open RC2. Records SKIPPED_NOT_INSTALLED for missing models.

Usage:
    python scripts/run_paper_package.py
"""
from __future__ import annotations

import csv
import json
import platform
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from evaluate_solver_quality import _write_csv, evaluate_large, evaluate_small  # noqa: E402
from evrptw_autolab.evaluation.fidelity import (  # noqa: E402
    by_customer_count,
    load_all,
    small_instances,
    split_instances,
    write_split_manifest,
)
from evrptw_autolab.evaluation.runner import check_f0, evaluate_fidelity  # noqa: E402
from evrptw_autolab.experiments.synthesis_campaign import run_campaign  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import (  # noqa: E402
    SKIPPED_NOT_INSTALLED,
    availability,
    resolve_profile,
)
from evrptw_autolab.orchestration.trajectory import load_trajectories  # noqa: E402
from evrptw_autolab.problem.hashes import write_instance_hashes  # noqa: E402
from evrptw_autolab.problem.schneider import SCHNEIDER_ROOT, discover_instances  # noqa: E402
from evrptw_autolab.sandbox.limits import limits_from_synthesis  # noqa: E402
from evrptw_autolab.sandbox.runner import run_solver  # noqa: E402

TAB = ROOT / "results" / "md" / "tables"
RAW = TAB / "raw_autolab"
RUNS = ROOT / "results" / "runs"
MD_SOLVERS = ROOT / "results" / "md" / "solvers"
FIG = ROOT / "results" / "md" / "figures"

# Three ~7B coding models from different families (Qwen / DeepSeek / CodeLlama).
MODEL_ORDER = [
    "qwen25_coder_7b",
    "deepseek_coder_67b",
    "codellama_7b",
]


def _dump(name: str, payload: object) -> Path:
    text = json.dumps(payload, indent=2, default=str)
    for folder in (RUNS, RAW):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
    return RUNS / name


def _usage_summary(workspace: Path) -> dict:
    path = workspace / "llm_calls.jsonl"
    if not path.exists():
        return {"n_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "latency_s": 0.0}
    n = 0
    prompt = 0
    completion = 0
    latency = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        n += 1
        prompt += int(row.get("prompt_tokens") or 0)
        completion += int(row.get("completion_tokens") or 0)
        latency += float(row.get("latency_s") or 0.0)
    return {"n_calls": n, "prompt_tokens": prompt, "completion_tokens": completion, "latency_s": round(latency, 1)}


def _copy_elite(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest, dirs_exist_ok=True)


def _write_csv_rows(path: Path, rows: list[dict], keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(keys)]
    for row in rows:
        lines.append(",".join(str(row.get(k, "")).replace(",", ";").replace("\n", " ") for k in keys))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _hardware() -> dict:
    import subprocess

    ollama = ""
    try:
        ollama = subprocess.check_output(["ollama", "--version"], text=True, timeout=10).strip()
    except Exception:  # noqa: BLE001
        ollama = "unknown"
    return {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "ollama": ollama,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def validate() -> dict:
    paths = discover_instances(ROOT / SCHNEIDER_ROOT)
    instances = load_all(ROOT / SCHNEIDER_ROOT)
    split = split_instances(instances)
    manifest = write_split_manifest(ROOT / "results" / "manifests" / "split.json", split)
    hashes = write_instance_hashes(ROOT / "results" / "manifests" / "instance_hashes.json")
    small = small_instances(instances)
    payload = {
        "n_files": len(paths),
        "n_discovery": len(split["discovery"]),
        "n_confirmation": len(split["confirmation"]),
        "n_heldout": len(split["heldout"]),
        "n_small": len(small),
        "n_small_discovery": len(small_instances(split["discovery"])),
        "n_small_confirmation": len(small_instances(split["confirmation"])),
        "n_small_heldout": len(small_instances(split["heldout"])),
        "manifest": str(manifest),
        "hashes": str(hashes),
    }
    print("validate", payload, flush=True)
    return payload


def run_one(model_id: str, *, cycles: int, campaign_id: str) -> dict:
    profile = resolve_profile(model_id)
    row: dict = {
        "model_id": model_id,
        "model": profile.model,
        "team_mode": "five_agent",
        "status": "",
        "cycles": cycles,
        "wall_s": 0.0,
        "elite_id": "",
        "f0_ok": False,
        "f1_feasible_rate": "",
        "f1_crashes": "",
        "f2_feasible_rate": "",
        "c101C5_feasible": "",
        "c101C5_vehicles": "",
        "c101C5_distance": "",
        "c101C5_first_fault": "",
        "small_feasible": "",
        "small_exact_fleet": "",
        "large_feasible": "",
        "n_calls": "",
        "prompt_tokens": "",
        "error": "",
    }
    ollama = OllamaBackend()
    status = availability(profile, ollama)
    row["status"] = status
    if status != "installed":
        print(f"{SKIPPED_NOT_INSTALLED}: {profile.model}", flush=True)
        _dump(f"{campaign_id}_{model_id}.json", row)
        return row
    split = split_instances(load_all())
    discovery = split["discovery"]
    smoke = by_customer_count(discovery, [5])
    by_id = {i.instance_id: i for i in smoke}
    limits = limits_from_synthesis()
    workspace = ROOT / "workspace" / "discovery_p0_clean" / model_id
    backend = OllamaBackend(timeout_s=180.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    t0 = time.monotonic()
    print(f"discovery {model_id} cycles={cycles} wall={limits.wall_clock_s}s", flush=True)
    try:
        state = run_campaign(
            model=profile.model,
            backend=backend,
            workspace=workspace,
            cycles=cycles,
            campaign_id=campaign_id,
            model_id=model_id,
            temperatures=profile.temperatures,
        )
        elite_dir = workspace / "candidates" / str(state.elite_id)
        f0 = check_f0(elite_dir) if elite_dir.exists() else ["missing:elite"]
        f1 = evaluate_fidelity(elite_dir, discovery, "F1", seeds=[0], limits=limits) if elite_dir.exists() else {}
        f1_summary = f1.get("summary") or {}
        f1_rate = float(f1_summary.get("feasible_rate") or 0.0)
        f2 = None
        if f1_rate > 0 and elite_dir.exists():
            f2 = evaluate_fidelity(elite_dir, discovery, "F2", seeds=[0], limits=limits)
        c101 = run_solver(elite_dir, by_id["c101C5"], seed=0, limits=limits) if elite_dir.exists() else None
        usage = _usage_summary(workspace)
        small_rows: list[dict] = []
        large_rows: list[dict] = []
        if elite_dir.exists() and not f0:
            print(f"  evaluating 36 small on {state.elite_id}", flush=True)
            small_rows = evaluate_small(elite_dir, wall_clock_s=limits.wall_clock_s)
            _write_csv(TAB / f"voltforge_quality_small_{model_id}.csv", small_rows)
            if any(r["feasible"] for r in small_rows):
                print(f"  evaluating 56 large on {state.elite_id}", flush=True)
                large_rows = evaluate_large(elite_dir, wall_clock_s=limits.wall_clock_s)
                _write_csv(TAB / f"voltforge_quality_large_{model_id}.csv", large_rows)
            _copy_elite(elite_dir, MD_SOLVERS / campaign_id / model_id)
            shutil.copy2(workspace / "trajectories.jsonl", RAW / f"{campaign_id}_{model_id}_trajectories.jsonl") if (
                workspace / "trajectories.jsonl"
            ).exists() else None
        row.update(
            {
                "status": "ran",
                "wall_s": round(time.monotonic() - t0, 1),
                "elite_id": state.elite_id,
                "cycle": state.cycle,
                "f0_ok": not f0,
                "f0_errors": f0,
                "f1_feasible_rate": f1_summary.get("feasible_rate"),
                "f1_crashes": f1_summary.get("crashes"),
                "f1": f1,
                "f2_feasible_rate": (f2 or {}).get("summary", {}).get("feasible_rate") if f2 else "",
                "f2": f2,
                "c101C5_feasible": None if c101 is None else c101.feasible,
                "c101C5_vehicles": None if c101 is None else c101.vehicles,
                "c101C5_distance": None if c101 is None else round(c101.total_distance, 2),
                "c101C5_first_fault": None if c101 is None else c101.first_fault,
                "small_feasible": sum(1 for r in small_rows if r["feasible"]),
                "small_n": len(small_rows),
                "small_exact_fleet": sum(1 for r in small_rows if r.get("exact_fleet")),
                "large_feasible": sum(1 for r in large_rows if r["feasible"]),
                "large_n": len(large_rows),
                "n_calls": usage["n_calls"],
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "llm_latency_s": usage["latency_s"],
                "activated_history": state.activated_history,
                "trajectories": load_trajectories(workspace),
            }
        )
        print(
            f"  elite={state.elite_id} f0={row['f0_ok']} f1={row['f1_feasible_rate']} "
            f"c101C5={row['c101C5_feasible']}/{row['c101C5_vehicles']}/{row['c101C5_distance']} "
            f"small_feasible={row['small_feasible']}",
            flush=True,
        )
    except Exception as error:  # noqa: BLE001
        row["status"] = "failed"
        row["error"] = str(error)[-1500:]
        row["wall_s"] = round(time.monotonic() - t0, 1)
        print(f"FAILED {model_id}: {error}", flush=True)
    _dump(f"{campaign_id}_{model_id}.json", row)
    return row


def write_report(rows: list[dict], *, meta: dict) -> None:
    lines = [
        "# VoltForge discovery package",
        "",
        f"**Date:** {datetime.now(UTC).date().isoformat()}",
        "**Protocol:** five agents, homogeneous model, discovery families C1+R1 only.",
        "**Not opened:** confirmation (C2, R2, RC1) for evolution; RC2 held-out.",
        "",
        "## Environment",
        "",
        f"- Python: `{meta['hardware']['python'].splitlines()[0]}`",
        f"- Platform: `{meta['hardware']['platform']}`",
        f"- Ollama: `{meta['hardware']['ollama']}`",
        f"- Cycles: {meta['cycles']}",
        f"- Solver wall-clock: {meta['wall_clock_s']} s",
        "",
        "## Model comparison",
        "",
        "| Model | Status | Compile-valid | F1 feasible | c101C5 vehicles | c101C5 distance | Small feasible / 36 | Exact fleet | LLM calls | Wall s |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {model} | {status} | {f0} | {f1} | {veh} | {dist} | {small} | {exact} | {calls} | {wall} |".format(
                model=row.get("model") or row.get("model_id"),
                status=row.get("status"),
                f0=row.get("f0_ok"),
                f1=row.get("f1_feasible_rate"),
                veh=row.get("c101C5_vehicles"),
                dist=row.get("c101C5_distance"),
                small=row.get("small_feasible"),
                exact=row.get("small_exact_fleet"),
                calls=row.get("n_calls"),
                wall=row.get("wall_s"),
            )
        )
    lines += [
        "",
        "Spark-era F1=1.0 results are **not** in this table. Those used a hidden stitch.",
        "",
        "Raw JSON: `tables/raw_autolab/discovery_p0_clean_*.json`. Elite solvers: `solvers/discovery_p0_clean/<model_id>/`.",
        "",
    ]
    path = ROOT / "results" / "md" / "DISCOVERY.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path}", flush=True)


def write_figure(rows: list[dict]) -> None:
    ran = [r for r in rows if r.get("status") == "ran"]
    if not ran:
        return
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    FIG.mkdir(parents=True, exist_ok=True)
    labels = [str(r["model_id"]).replace("qwen25_coder_", "qwen ").replace("llama32_", "llama ") for r in ran]
    f1 = [float(r["f1_feasible_rate"] or 0) for r in ran]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.bar(labels, f1, color="#2c5f8a")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("F1 feasible rate")
    ax.set_title("VoltForge discovery F1 (C1+R1 five-customer cases)")
    fig.tight_layout()
    fig.savefig(FIG / "voltforge_discovery_f1.png", dpi=140)
    plt.close(fig)


def _completed_row(campaign_id: str, model_id: str, *, cycles: int) -> dict | None:
    """Reuse a finished model JSON so a killed package run can continue."""
    for folder in (RAW, RUNS):
        path = folder / f"{campaign_id}_{model_id}.json"
        if not path.exists():
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        status = str(row.get("status") or "")
        if status == SKIPPED_NOT_INSTALLED or status.startswith("SKIPPED"):
            return row
        done_cycles = int(row.get("cycle") or 0)
        if status == "ran" and done_cycles >= cycles:
            return row
    return None


def _workspace_ready(campaign_id: str, model_id: str, *, cycles: int) -> bool:
    """True when the campaign already finished even if the JSON dump failed."""
    state_path = ROOT / "workspace" / "discovery_p0_clean" / model_id / "campaigns" / f"{campaign_id}.json"
    if not state_path.exists():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return int(state.get("cycle") or 0) >= cycles and bool(state.get("elite_id"))


def main() -> None:
    experiments = yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}
    cycles = int((experiments.get("discover") or {}).get("cycles") or 5)
    configured = list((experiments.get("model_comparison") or {}).get("model_ids") or MODEL_ORDER)
    model_ids = [m for m in MODEL_ORDER if m in configured] + [m for m in configured if m not in MODEL_ORDER]
    started = time.monotonic()
    hardware = _hardware()
    print("hardware", hardware, flush=True)
    print(f"fast package models={model_ids} cycles={cycles}", flush=True)
    dataset = validate()
    limits = limits_from_synthesis()
    rows: list[dict] = []
    campaign_id = "discovery_p0_clean"
    for model_id in model_ids:
        existing = _completed_row(campaign_id, model_id, cycles=cycles)
        if existing is not None:
            print(f"skip {model_id} status={existing.get('status')} cycle={existing.get('cycle')}", flush=True)
            rows.append(existing)
        else:
            if _workspace_ready(campaign_id, model_id, cycles=cycles):
                print(f"resume-eval {model_id} (workspace already at {cycles}+ cycles)", flush=True)
            rows.append(run_one(model_id, cycles=cycles, campaign_id=campaign_id))
        keys = [
            "model_id",
            "model",
            "status",
            "cycles",
            "wall_s",
            "elite_id",
            "f0_ok",
            "f1_feasible_rate",
            "f1_crashes",
            "c101C5_feasible",
            "c101C5_vehicles",
            "c101C5_distance",
            "small_feasible",
            "small_exact_fleet",
            "large_feasible",
            "n_calls",
            "prompt_tokens",
        ]
        _write_csv_rows(TAB / "voltforge_discovery.csv", rows, keys)
    meta = {
        "elapsed_s": round(time.monotonic() - started, 1),
        "cycles": cycles,
        "campaign": "discovery_p0_clean",
        "wall_clock_s": limits.wall_clock_s,
        "hardware": hardware,
        "dataset": dataset,
        "timestamp": datetime.now(UTC).isoformat(),
        "held_out_opened": False,
        "models": model_ids,
        "note": "P0 clean autonomous lab; Qwen 7B only; no recovery injection",
    }
    _dump("discovery_meta.json", meta)
    write_report(rows, meta=meta)
    write_figure(rows)
    print("done", meta["elapsed_s"], "s", flush=True)


if __name__ == "__main__":
    main()
