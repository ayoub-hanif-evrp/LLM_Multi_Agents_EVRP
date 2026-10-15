"""Classical (non-LLM) baseline pilot across five EVRP families."""
from __future__ import annotations

import csv
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.problem.datasets.bezzi import load_bezzi
from evrptw_autolab.problem.datasets.goeke import load_goeke
from evrptw_autolab.problem.datasets.hiermann import load_hiermann
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2

ROOT = Path(__file__).resolve().parents[3]


@dataclass
class PilotInstance:
    family: str
    instance_id: str
    path: Path
    loader: Callable[[Path], ProblemSpecV2]
    time_limit_s: float = 8.0
    alns_iterations: int = 80


@dataclass
class PilotRow:
    family: str
    instance_id: str
    seed: int
    feasible: bool
    objective: float | None
    objective_key: list[float]
    vehicles: int
    distance: float
    duration: float
    runtime_s: float
    first_fault: str
    violation_families: list[str]
    unserved: int
    charging_visits: int
    routes: list[list[dict[str, Any]]] = field(default_factory=list)
    error: str = ""


def development_panel(root: Path | None = None) -> list[PilotInstance]:
    """Small development instances only. Never held-out Schneider RC2."""
    base = root or ROOT
    panel: list[PilotInstance] = []
    schneider = [
        ("c101C5.txt", 8.0, 80),
        ("c103C5.txt", 8.0, 80),
        ("r104C5.txt", 8.0, 80),
        ("r105C5.txt", 8.0, 80),
        ("rc105C5.txt", 8.0, 80),
    ]
    for name, tl, it in schneider:
        path = base / "dataset" / "schneider" / "raw_instances" / name
        if path.exists():
            panel.append(PilotInstance("schneider", path.stem, path, load_schneider_v2, tl, it))
    montoya = ["tc0c10s2cf1.xml", "tc0c10s3cf1.xml"]
    for name in montoya:
        path = base / "dataset" / "montoya-et-al-2017" / name
        if path.exists():
            panel.append(PilotInstance("montoya", path.stem, path, load_montoya, 10.0, 60))
    bezzi = [
        "Dataset_A/Instances/C101-5.xml",
        "Dataset_A/Instances/R105-5.xml",
        "Dataset_B/Instances/10-N10.xml",
    ]
    for rel in bezzi:
        path = base / "dataset" / "Bezzi & Ceselli EVRP-MRT" / rel
        if path.exists():
            panel.append(PilotInstance("bezzi", path.stem, path, load_bezzi, 12.0, 60))
    goeke = ["c101C6.txt", "r104C6.txt", "rc105C6.txt"]
    for name in goeke:
        path = base / "dataset" / "goeke-2018" / name
        if path.exists():
            panel.append(PilotInstance("goeke", path.stem, path, load_goeke, 10.0, 60))
    # Hiermann instances are ~100 customers; keep a short representative attempt.
    hier = base / "dataset" / "hiermann-et-al-2017-set-1" / "c101_21.txt"
    if hier.exists():
        panel.append(PilotInstance("hiermann", hier.stem, hier, load_hiermann, 15.0, 40))
    return panel


def _route_records(solution: SolutionV2) -> list[list[dict[str, Any]]]:
    out: list[list[dict[str, Any]]] = []
    for route in solution.routes:
        stops = []
        for stop in route:
            stops.append(
                {
                    "node_id": stop.node_id,
                    "event": stop.event,
                    "charge_amount": stop.charge_amount,
                    "charge_technology": stop.charge_technology,
                    "target_soc": stop.target_soc,
                    "vehicle_type_id": stop.vehicle_type_id,
                }
            )
        out.append(stops)
    return out


def run_one(item: PilotInstance, seed: int) -> PilotRow:
    started = time.monotonic()
    try:
        spec = item.loader(item.path)
        solution = solve_classical(
            spec,
            seed=seed,
            time_limit_s=item.time_limit_s,
            alns_iterations=item.alns_iterations,
        )
        report = evaluate(spec, solution)
        fault = ""
        if report.first_fault is not None:
            fault = f"{report.first_fault.family}: {report.first_fault.detail}"
        return PilotRow(
            family=item.family,
            instance_id=item.instance_id,
            seed=seed,
            feasible=bool(report.feasible),
            objective=report.objective,
            objective_key=list(report.objective_key),
            vehicles=report.vehicles,
            distance=report.total_distance,
            duration=report.total_duration,
            runtime_s=time.monotonic() - started,
            first_fault=fault,
            violation_families=sorted({v.family for v in report.violations}),
            unserved=len(report.unserved),
            charging_visits=report.charging_visits,
            routes=_route_records(solution),
        )
    except Exception as error:  # noqa: BLE001 — pilot must continue
        return PilotRow(
            family=item.family,
            instance_id=item.instance_id,
            seed=seed,
            feasible=False,
            objective=None,
            objective_key=[],
            vehicles=0,
            distance=0.0,
            duration=0.0,
            runtime_s=time.monotonic() - started,
            first_fault="CRASH",
            violation_families=["CRASH"],
            unserved=-1,
            charging_visits=0,
            error=str(error)[:500],
        )


def aggregate(rows: list[PilotRow]) -> list[dict[str, Any]]:
    families = sorted({r.family for r in rows})
    table: list[dict[str, Any]] = []
    for family in families:
        group = [r for r in rows if r.family == family]
        feasible = [r for r in group if r.feasible]
        objs = [float(r.objective) for r in feasible if r.objective is not None]
        keys = [r.objective_key for r in feasible if r.objective_key]
        table.append(
            {
                "family": family,
                "instances_tested": len(group),
                "feasible": len(feasible),
                "feasibility_rate": len(feasible) / len(group) if group else 0.0,
                "mean_objective_feasible": (sum(objs) / len(objs)) if objs else None,
                "mean_objective_key_feasible": (
                    [sum(k[i] for k in keys) / len(keys) for i in range(len(keys[0]))]
                    if keys and all(len(k) == len(keys[0]) for k in keys)
                    else None
                ),
                "mean_runtime_s": sum(r.runtime_s for r in group) / len(group) if group else 0.0,
                "note": (
                    "objective is the first lexicographic component "
                    "(vehicles for Schneider/Goeke; recharge cost for Bezzi; "
                    "duration for Montoya; total cost for Hiermann)"
                ),
            }
        )
    return table


def write_results(rows: list[PilotRow], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    per_path = out_dir / f"pilot_{stamp}.json"
    csv_path = out_dir / f"pilot_{stamp}.csv"
    summary_path = out_dir / "summary.json"
    latest_path = out_dir / "latest.json"

    payload = {
        "protocol": "classical_baseline_pilot_v1",
        "solver": "classical_backbone",
        "llm_calls": 0,
        "created_utc": stamp,
        "rows": [asdict(r) for r in rows],
        "aggregate": aggregate(rows),
    }
    per_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    latest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    summary_path.write_text(json.dumps(payload["aggregate"], indent=2) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "family",
                "instance_id",
                "seed",
                "feasible",
                "objective",
                "vehicles",
                "distance",
                "duration",
                "runtime_s",
                "first_fault",
                "unserved",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "family": row.family,
                    "instance_id": row.instance_id,
                    "seed": row.seed,
                    "feasible": row.feasible,
                    "objective": row.objective,
                    "vehicles": row.vehicles,
                    "distance": row.distance,
                    "duration": row.duration,
                    "runtime_s": round(row.runtime_s, 4),
                    "first_fault": row.first_fault,
                    "unserved": row.unserved,
                }
            )
    return {"json": per_path, "csv": csv_path, "summary": summary_path, "latest": latest_path}


def run_classical_pilot(
    *,
    seed: int = 7,
    out_dir: Path | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    panel = development_panel(root)
    rows = [run_one(item, seed) for item in panel]
    paths = write_results(rows, out_dir or (ROOT / "results" / "v2" / "baselines" / "classical"))
    return {
        "rows": rows,
        "aggregate": aggregate(rows),
        "paths": {k: str(v) for k, v in paths.items()},
        "n": len(rows),
    }
