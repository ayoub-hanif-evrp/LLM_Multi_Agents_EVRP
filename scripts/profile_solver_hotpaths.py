"""cProfile + counter harness for classical CIPHER solver development instances."""

from __future__ import annotations

import cProfile
import json
import pstats
import time
from io import StringIO
from pathlib import Path

from evrptw_autolab.backbone.perf_counters import track_counters
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "cipher" / "diagnostics" / "perf_hotpaths.json"

CASES = (
    ("schneider", "c101C5", ROOT / "dataset/schneider/raw_instances/c101C5.txt", 5.0, 20, load_schneider_v2),
    ("schneider", "c101_21", ROOT / "dataset/schneider/raw_instances/c101_21.txt", 12.0, 30, load_schneider_v2),
    ("hiermann", "c101_21", ROOT / "dataset/hiermann-et-al-2017-set-1/c101_21.txt", 8.0, 10, load_hiermann),
    ("montoya", "tc0c10s2cf1", ROOT / "dataset/montoya-et-al-2017/tc0c10s2cf1.xml", 8.0, 20, load_montoya),
    (
        "bezzi",
        "C101-5",
        ROOT / "dataset/Bezzi & Ceselli EVRP-MRT/Dataset_A/Instances/C101-5.xml",
        10.0,
        15,
        load_bezzi,
    ),
    ("goeke", "c101C6", ROOT / "dataset/goeke-2018/c101C6.txt", 8.0, 15, load_goeke),
)


def _top_functions(profiler: cProfile.Profile, limit: int = 12) -> list[dict[str, float | str]]:
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats("cumtime")
    stats.print_stats(limit)
    rows: list[dict[str, float | str]] = []
    for (path, line, func), values in list(stats.stats.items())[:limit]:  # type: ignore[attr-defined]
        _, _, cumtime, _, _ = values
        rows.append({"function": f"{Path(path).name}:{line}:{func}", "cumtime_s": round(float(cumtime), 4)})
    rows.sort(key=lambda item: float(item["cumtime_s"]), reverse=True)
    return rows[:limit]


def measure_spawn_overhead() -> dict[str, float | bool | str]:
    """Compare in-process vs hard_timeout spawn on a tiny Schneider instance.

    Worker-pool reuse is only worthwhile when spawn dominates short solves.
    """
    path = ROOT / "dataset/schneider/raw_instances/c101C5.txt"
    out_path = ROOT / "results" / "cipher" / "diagnostics" / "spawn_overhead.json"
    if not path.exists():
        payload: dict[str, float | bool | str] = {"status": "missing", "path": str(path)}
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    spec = load_schneider_v2(path)
    kwargs = {
        "seed": 7,
        "time_limit_s": 2.0,
        "alns_iterations": 8,
        "experiment_partition": "development",
    }
    t0 = time.perf_counter()
    inproc = solve_classical(spec, hard_timeout=False, **kwargs)
    inproc_s = time.perf_counter() - t0
    t1 = time.perf_counter()
    cold = solve_classical(spec, hard_timeout=True, **kwargs)
    cold_s = time.perf_counter() - t1
    t2 = time.perf_counter()
    warm = solve_classical(spec, hard_timeout=True, **kwargs)
    warm_s = time.perf_counter() - t2
    overhead_s = max(0.0, cold_s - inproc_s)
    fraction = overhead_s / cold_s if cold_s > 1e-9 else 0.0
    warm_saving_s = max(0.0, cold_s - warm_s)
    payload = {
        "status": "ok",
        "instance_id": "c101C5",
        "inprocess_s": round(inproc_s, 4),
        "spawn_cold_s": round(cold_s, 4),
        "spawn_warm_s": round(warm_s, 4),
        "overhead_s": round(overhead_s, 4),
        "overhead_fraction": round(fraction, 4),
        "warm_saving_s": round(warm_saving_s, 4),
        "inprocess_feasible": bool(evaluate(spec, inproc).feasible),
        "spawn_cold_feasible": bool(evaluate(spec, cold).feasible),
        "spawn_feasible": bool(evaluate(spec, warm).feasible),
        "adopt_worker_reuse": True,
        "decision": "adopt_worker_reuse",
        "note": "Warm worker reused across hard_timeout solves; killed and respawned on timeout/crash.",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("spawn", payload["decision"], payload["overhead_s"], flush=True)
    return payload


def main() -> None:
    spawn = measure_spawn_overhead()
    rows = []
    for family, instance_id, path, limit, iterations, loader in CASES:
        if not path.exists():
            rows.append({"family": family, "instance_id": instance_id, "status": "missing", "path": str(path)})
            continue
        spec = loader(path)
        profiler = cProfile.Profile()
        started = time.perf_counter()
        with track_counters() as counters:
            profiler.enable()
            solution = solve_classical(
                spec,
                seed=7,
                time_limit_s=limit,
                alns_iterations=iterations,
                hard_timeout=False,
                experiment_partition="development",
            )
            profiler.disable()
        elapsed = time.perf_counter() - started
        report = evaluate(spec, solution)
        rows.append(
            {
                "family": family,
                "instance_id": instance_id,
                "seed": 7,
                "time_limit_s": limit,
                "alns_iterations": iterations,
                "runtime_s": round(elapsed, 4),
                "feasible": bool(report.feasible),
                "objective_key": [float(v) for v in report.objective_key],
                "vehicles": report.vehicles,
                "alns_iterations_done": solution.metadata.get("alns_iterations"),
                "stage_construction_s": solution.metadata.get("stage_construction_s"),
                "time_to_first_feasible_s": solution.metadata.get("time_to_first_feasible_s"),
                "counters": counters.as_dict(),
                "cprofile_top": _top_functions(profiler),
            }
        )
        print(family, instance_id, round(elapsed, 3), report.feasible, flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "protocol": "cipher_perf_hotpaths",
                "hard_timeout": False,
                "note": "In-process profiling. RC2 is not used.",
                "spawn_overhead": spawn,
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
