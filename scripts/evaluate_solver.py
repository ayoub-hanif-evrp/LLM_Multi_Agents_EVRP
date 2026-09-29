"""Evaluate a frozen solver with zero LLM calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.evolution.evaluate import (  # noqa: E402
    all_c5_instances,
    evaluate_panel,
    final_scale_sets,
    literature_scale_instances,
    source_hash,
)
from evrptw_autolab.sandbox.limits import RunLimits  # noqa: E402


def _load_rows(folder: str) -> list[dict]:
    directory = ROOT / "results" / "paper" / folder
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return rows


def _best_fully_feasible(rows: list[dict]) -> dict | None:
    pool = []
    for row in rows:
        published = row.get("published_solver") or ""
        if not published or not row.get("fully_feasible"):
            continue
        solver = ROOT / published
        if solver.exists():
            pool.append(row)
    if not pool:
        return None
    pool.sort(key=lambda row: (int(row.get("vehicles") or 10**9), float(row.get("distance") or 1e18)))
    return pool[0]


def evaluate_directory(solver: Path, *, wall_clock_s: float) -> dict:
    solver_dir = solver if solver.is_dir() else solver.parent
    source = (solver_dir / "solver.py").read_text(encoding="utf-8")
    limits = RunLimits(wall_clock_s=wall_clock_s)
    report: dict = {
        "solver": str(solver_dir / "solver.py"),
        "hash": source_hash(source),
        "llm_calls": 0,
        "sets": {},
    }
    for name, instances in final_scale_sets().items():
        metrics, _ = evaluate_panel(solver_dir, instances, limits=limits)
        report["sets"][name] = metrics.as_dict()
        print(f"{name}: {metrics.feasible}/{metrics.total}", flush=True)
    return report


def write_final() -> None:
    out = ROOT / "results" / "paper" / "evaluation"
    out.mkdir(parents=True, exist_ok=True)
    synthesis = _best_fully_feasible(_load_rows("synthesis") + _load_rows("single_agent"))
    evolution_rows = [row for row in _load_rows("evolution") if row.get("seed") is not None]
    evolved = _best_fully_feasible(evolution_rows)
    note = {
        "synthesis_solver": None if synthesis is None else synthesis.get("published_solver"),
        "evolution_solver": None if evolved is None else evolved.get("published_solver"),
        "evolution_started": not any(row.get("failure_reason") == "no valid synthesized solver to evolve" for row in _load_rows("evolution")),
    }
    if synthesis is None:
        note["synthesis_status"] = "no fully feasible synthesized solver"
    else:
        report = evaluate_directory(ROOT / str(synthesis["published_solver"]), wall_clock_s=45.0)
        report["origin"] = "synthesized"
        (out / "synthesized.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if evolved is None:
        note["evolution_status"] = "no fully feasible evolved solver"
    else:
        report = evaluate_directory(ROOT / str(evolved["published_solver"]), wall_clock_s=45.0)
        report["origin"] = "evolved"
        (out / "evolved.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "status.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
    print(json.dumps(note), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, default=None)
    parser.add_argument("--sizes", default="5")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--final", action="store_true")
    args = parser.parse_args()
    if args.final:
        write_final()
        return
    if args.solver is None:
        raise SystemExit("pass --solver or --final")
    solver = args.solver
    solver_dir = solver if solver.is_dir() else solver.parent
    source = (solver_dir / "solver.py").read_text(encoding="utf-8")
    limits = RunLimits(wall_clock_s=60.0)
    report: dict = {"solver": str(solver), "hash": source_hash(source), "sizes": {}}
    for raw in args.sizes.split(","):
        size = int(raw.strip())
        instances = all_c5_instances() if size == 5 else literature_scale_instances(customer_count=size)
        metrics, _ = evaluate_panel(solver_dir, instances, limits=limits)
        report["sizes"][str(size)] = metrics.as_dict()
    text = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
