"""Matched before/after classical solver comparison vs commit e6d94cf."""

from __future__ import annotations

import json
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "diagnostics" / "perf_before_after.json"
BASELINE_SHA = "e6d94cfd5b0766f833a73caf6ee680ecf2ffdd8d"
SEEDS = (7, 11, 22)

CASES = (
    ("schneider", "c101C5", "dataset/schneider/raw_instances/c101C5.txt", 5.0, 20, "schneider"),
    ("schneider", "c101_21", "dataset/schneider/raw_instances/c101_21.txt", 12.0, 30, "schneider"),
    ("hiermann", "c101_21", "dataset/hiermann-et-al-2017-set-1/c101_21.txt", 8.0, 10, "hiermann"),
    ("montoya", "tc0c10s2cf1", "dataset/montoya-et-al-2017/tc0c10s2cf1.xml", 8.0, 20, "montoya"),
    (
        "bezzi",
        "C101-5",
        "dataset/Bezzi & Ceselli EVRP-MRT/Dataset_A/Instances/C101-5.xml",
        10.0,
        15,
        "bezzi",
    ),
    ("goeke", "c101C6", "dataset/goeke-2018/c101C6.txt", 8.0, 15, "goeke"),
)

_LOADERS = {
    "schneider": load_schneider_v2,
    "hiermann": load_hiermann,
    "montoya": load_montoya,
    "bezzi": load_bezzi,
    "goeke": load_goeke,
}


def _solve_row(root: Path, family: str, instance_id: str, rel: str, limit: float, iters: int, loader_key: str, seed: int) -> dict:
    path = root / rel
    if not path.exists():
        return {"family": family, "instance_id": instance_id, "seed": seed, "status": "missing"}
    spec = _LOADERS[loader_key](path)
    started = time.perf_counter()
    solution = solve_classical(
        spec,
        seed=seed,
        time_limit_s=limit,
        alns_iterations=iters,
        hard_timeout=False,
        experiment_partition="development",
    )
    elapsed = time.perf_counter() - started
    report = evaluate(spec, solution)
    return {
        "family": family,
        "instance_id": instance_id,
        "seed": seed,
        "status": "ok",
        "runtime_s": round(elapsed, 4),
        "feasible": bool(report.feasible),
        "objective_key": [float(v) for v in report.objective_key],
        "vehicles": report.vehicles,
        "alns_iterations_done": solution.metadata.get("alns_iterations"),
        "time_to_first_feasible_s": solution.metadata.get("time_to_first_feasible_s"),
        "hard_timeout_triggered": bool(solution.metadata.get("hard_timeout_triggered")),
    }


def _run_current() -> list[dict]:
    rows = []
    for family, instance_id, rel, limit, iters, loader_key in CASES:
        for seed in SEEDS:
            row = _solve_row(ROOT, family, instance_id, rel, limit, iters, loader_key, seed)
            rows.append(row)
            print("current", family, instance_id, seed, row.get("runtime_s"), row.get("feasible"), flush=True)
    return rows


_BASELINE_DRIVER = r'''
import json, time, sys
from pathlib import Path
root = Path(sys.argv[1])
cases = json.loads(sys.argv[2])
seeds = json.loads(sys.argv[3])
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
loaders = {"schneider": load_schneider_v2, "hiermann": load_hiermann, "montoya": load_montoya, "bezzi": load_bezzi, "goeke": load_goeke}
rows = []
for family, instance_id, rel, limit, iters, loader_key in cases:
    for seed in seeds:
        path = root / rel
        if not path.exists():
            rows.append({"family": family, "instance_id": instance_id, "seed": seed, "status": "missing"})
            print("baseline", family, instance_id, seed, "missing", flush=True)
            continue
        spec = loaders[loader_key](path)
        started = time.perf_counter()
        solution = solve_classical(spec, seed=seed, time_limit_s=float(limit), alns_iterations=int(iters), hard_timeout=False, experiment_partition="development")
        elapsed = time.perf_counter() - started
        report = evaluate(spec, solution)
        row = {
            "family": family, "instance_id": instance_id, "seed": seed, "status": "ok",
            "runtime_s": round(elapsed, 4), "feasible": bool(report.feasible),
            "objective_key": [float(v) for v in report.objective_key], "vehicles": report.vehicles,
            "alns_iterations_done": solution.metadata.get("alns_iterations"),
            "time_to_first_feasible_s": solution.metadata.get("time_to_first_feasible_s"),
            "hard_timeout_triggered": bool(solution.metadata.get("hard_timeout_triggered")),
        }
        rows.append(row)
        print("baseline", family, instance_id, seed, row["runtime_s"], row["feasible"], flush=True)
print("RESULT_JSON::" + json.dumps(rows), flush=True)
'''


def _run_baseline() -> list[dict]:
    work = Path(tempfile.mkdtemp(prefix="cipher-baseline-"))
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(work), BASELINE_SHA],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        proc = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "-c",
                _BASELINE_DRIVER,
                str(ROOT),
                json.dumps(list(CASES)),
                json.dumps(list(SEEDS)),
            ],
            cwd=work,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"baseline failed: {(proc.stderr or '')[-800:]}")
        marker = "RESULT_JSON::"
        lines = [ln for ln in (proc.stdout or "").splitlines() if ln.startswith(marker)]
        if not lines:
            # Forward progress logs for debugging.
            print(proc.stdout, flush=True)
            raise RuntimeError("baseline produced no RESULT_JSON marker")
        for ln in (proc.stdout or "").splitlines():
            if not ln.startswith(marker):
                print(ln, flush=True)
        return json.loads(lines[-1][len(marker) :])
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(work)], cwd=ROOT, check=False)


def _summarize(label: str, rows: list[dict]) -> dict:
    ok = [r for r in rows if r.get("status") == "ok"]
    by_case: dict[str, list[dict]] = {}
    for row in ok:
        key = f"{row['family']}/{row['instance_id']}"
        by_case.setdefault(key, []).append(row)
    summary = {}
    for key, group in by_case.items():
        runtimes = [float(r["runtime_s"]) for r in group]
        summary[key] = {
            "n": len(group),
            "median_runtime_s": round(statistics.median(runtimes), 4),
            "mean_runtime_s": round(statistics.mean(runtimes), 4),
            "feasible_count": sum(1 for r in group if r.get("feasible")),
            "objective_keys": [r.get("objective_key") for r in group],
            "alns_iterations_done": [r.get("alns_iterations_done") for r in group],
            "time_to_first_feasible_s": [r.get("time_to_first_feasible_s") for r in group],
        }
    return {"label": label, "rows": rows, "by_case": summary}


def main() -> None:
    current = _summarize("master", _run_current())
    baseline = _summarize(BASELINE_SHA[:7], _run_baseline())
    comparisons = {}
    for key, cur in current["by_case"].items():
        base = baseline["by_case"].get(key)
        if not base:
            comparisons[key] = {"status": "missing_baseline"}
            continue
        speedup = (
            None
            if cur["median_runtime_s"] <= 0
            else round(base["median_runtime_s"] / cur["median_runtime_s"], 3)
        )
        comparisons[key] = {
            "baseline_median_runtime_s": base["median_runtime_s"],
            "current_median_runtime_s": cur["median_runtime_s"],
            "speedup_x": speedup,
            "baseline_feasible": base["feasible_count"],
            "current_feasible": cur["feasible_count"],
            "objective_keys_match_seed_order": base["objective_keys"] == cur["objective_keys"],
        }
    payload = {
        "protocol": "cipher_perf_before_after",
        "baseline_sha": BASELINE_SHA,
        "current_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "seeds": list(SEEDS),
        "hard_timeout": False,
        "baseline": baseline,
        "current": current,
        "comparisons": comparisons,
        "note": "Native objectives are reported per family; never average across families.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
