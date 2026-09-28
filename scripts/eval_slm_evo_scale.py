"""Evaluate a frozen SLM-Evo solver on C10 / C15 literature instances (no LLM)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.evaluation.literature import SCHNEIDER_2014_SMALL_CPLEX  # noqa: E402
from evrptw_autolab.sandbox.limits import RunLimits  # noqa: E402
from evrptw_autolab.slm_evo.evaluate import (  # noqa: E402
    evaluate_panel,
    literature_scale_instances,
    source_hash,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solver", type=Path, required=True)
    parser.add_argument("--sizes", default="10,15")
    parser.add_argument("--wall-clock-s", type=float, default=60.0)
    parser.add_argument("--tag", default="scale")
    args = parser.parse_args()

    solver = args.solver
    if solver.is_dir():
        solver_dir = solver
        src = (solver / "solver.py").read_text(encoding="utf-8")
    else:
        solver_dir = solver.parent
        src = solver.read_text(encoding="utf-8")

    limits = RunLimits(wall_clock_s=float(args.wall_clock_s))
    sizes = [int(x.strip()) for x in args.sizes.split(",") if x.strip()]
    report: dict = {
        "solver": str(solver),
        "hash": source_hash(src),
        "timestamp": datetime.now(UTC).isoformat(),
        "sizes": {},
    }
    md_lines = [
        f"# SLM-Evo scale eval — `{args.tag}`",
        "",
        f"**Solver:** `{solver}` | **hash:** `{report['hash']}`",
        "",
    ]

    for n in sizes:
        instances = literature_scale_instances(customer_count=n)
        metrics, _ = evaluate_panel(solver_dir, instances, limits=limits)
        rows = []
        for iid, row in (metrics.by_instance or {}).items():
            lit = SCHNEIDER_2014_SMALL_CPLEX.get(iid)
            rows.append(
                {
                    "instance": iid,
                    "ok": row.get("ok"),
                    "vehicles": row.get("vehicles"),
                    "distance": row.get("distance"),
                    "fault": row.get("fault"),
                    "lit_vehicles": lit[0] if lit else None,
                    "lit_distance": lit[1] if lit else None,
                }
            )
        report["sizes"][str(n)] = {
            "feasible": metrics.feasible,
            "total": metrics.total,
            "vehicles_sum": metrics.vehicles_sum,
            "distance_sum": metrics.distance_sum,
            "by_instance": rows,
        }
        md_lines += [
            f"## C{n}",
            "",
            f"**Feasible:** `{metrics.feasible}/{metrics.total}` | "
            f"**vehicles_sum:** `{metrics.vehicles_sum}` | "
            f"**distance_sum:** `{metrics.distance_sum}`",
            "",
            "| Instance | OK | Veh | Dist | Lit veh | Lit dist |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for r in rows:
            md_lines.append(
                f"| {r['instance']} | {r['ok']} | {r.get('vehicles')} | "
                f"{r.get('distance')} | {r.get('lit_vehicles')} | {r.get('lit_distance')} |"
            )
        md_lines.append("")

    out_json = ROOT / "results" / "md" / "tables" / "raw_autolab" / f"slm_evo_scale_{args.tag}.json"
    out_md = ROOT / "results" / "md" / f"SLM_EVO_SCALE_{args.tag.upper()}_REPORT.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(json.dumps({k: report["sizes"][k] for k in report["sizes"]}, indent=2, default=str))
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
