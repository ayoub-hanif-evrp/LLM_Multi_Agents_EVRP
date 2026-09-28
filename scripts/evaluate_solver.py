"""Evaluate a frozen solver with zero LLM calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.sandbox.limits import RunLimits  # noqa: E402
from evrptw_autolab.slm_evo.evaluate import (  # noqa: E402
    all_c5_instances,
    evaluate_panel,
    literature_scale_instances,
    source_hash,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--sizes", default="5")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
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
