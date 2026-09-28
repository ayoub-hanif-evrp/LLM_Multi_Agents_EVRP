"""Run independent SLM-Evo seeds from a chosen parent (default: synthesized 60-veh)."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEEDS = (11, 22, 33, 44, 55)
DEFAULT_PARENT = (
    ROOT
    / "results"
    / "md"
    / "artifacts"
    / "mcb_v1"
    / "FEASIBLE_SYNTHESIZED_SOLVER_V0_qwen14b_seed33"
    / "solver.py"
)


def _result_path(profile: str, run_id: str) -> Path:
    return ROOT / "results" / "md" / "tables" / "raw_autolab" / f"slm_evo_{profile}_{run_id}.json"


def _load_result(profile: str, run_id: str) -> dict | None:
    path = _result_path(profile, run_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_repro_report(
    *,
    profile: str,
    seeds: list[int],
    results: list[dict],
    parent_label: str,
    report_name: str,
    baseline_veh: int | None,
) -> Path:
    md = ROOT / "results" / "md" / report_name
    lines = [
        f"# SLM-Evo — {report_name.replace('.md', '')}",
        "",
        f"**Parent:** {parent_label}",
        f"**Profile:** `{profile}` | **timestamp:** `{datetime.now(UTC).isoformat()}`",
        f"**Protocol:** full budget, `stop_on_milestone=False`, all-C5 12/12 gate, seeds `{seeds}`",
        "",
        "| Seed | Trajectory (all-C5 veh) | Final veh | Δ | First improve gen | 12/12? | Freeze | Mechanisms |",
        "| ---: | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    improved_n = 0
    for r in results:
        seed = r.get("seed_base")
        parent_v = (r.get("parent_all_c5") or {}).get("vehicles_sum")
        final_v = (r.get("all_c5") or {}).get("vehicles_sum")
        feas = (r.get("all_c5") or {}).get("feasible")
        total = (r.get("all_c5") or {}).get("total")
        delta = (final_v - parent_v) if (final_v is not None and parent_v is not None) else None
        valid = bool(r.get("improved_vs_parent")) and feas == total == 12
        if valid:
            improved_n += 1
        first_gen = ""
        mechs = []
        for step in r.get("trajectory") or []:
            if step.get("kind") == "accepted":
                if first_gen == "":
                    first_gen = str(step.get("gen"))
                ops = "+".join(
                    f"{o.get('action')}:{o.get('symbol')}" for o in (step.get("ops") or [])
                )
                mechs.append(f"g{step.get('gen')}/{step.get('role')}/{ops}")
        freeze = r.get("freeze_dir") or "—"
        if isinstance(freeze, str) and freeze != "—":
            freeze = Path(freeze).name
        lines.append(
            f"| {seed} | `{r.get('trajectory_vehicles')}` | {final_v} | {delta} | "
            f"{first_gen or '—'} | {feas}/{total} | `{freeze}` | {'; '.join(mechs) or '—'} |"
        )
    lines += [
        "",
        f"**Valid seeds with fleet reduction (12/12):** `{improved_n}/{len(results)}`",
        "",
    ]
    if baseline_veh is not None:
        lines.append(f"**Baseline parent vehicles:** `{baseline_veh}`")
        lines.append("")
    if improved_n >= 2:
        lines.append(
            "Verdict: **reproducible feasible improvement** below parent fleet "
            "→ freeze best and proceed to scale-aware evolution later."
        )
    elif improved_n == 1:
        lines.append(
            "Verdict: **single-seed feasible improvement** — freeze that solver; "
            "treat reproducibility as weak."
        )
    else:
        lines.append(
            "Verdict: **no feasible fleet improvement** below parent in this budget "
            "(negative but publishable)."
        )
    lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def _freeze_best_overall(results: list[dict], tag: str = "OPT_V2") -> Path | None:
    """Copy best valid improved solver to a stable tag (never OPT_V1)."""
    from evrptw_autolab.slm_evo.freeze import ARTIFACTS_SLM_EVO, assert_not_opt_v1

    candidates = []
    for r in results:
        a = r.get("all_c5") or {}
        if not r.get("improved_vs_parent"):
            continue
        if a.get("feasible") != a.get("total") or a.get("total") != 12:
            continue
        freeze = r.get("freeze_dir")
        if not freeze:
            continue
        candidates.append(
            (
                int(a.get("vehicles_sum") or 10**9),
                float(a.get("distance_sum") or 10**9),
                Path(freeze),
                r.get("best_hash"),
                r.get("seed_base"),
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    veh, dist, src, h, seed = candidates[0]
    dest = ARTIFACTS_SLM_EVO / f"{tag}_{h}"
    assert_not_opt_v1(dest)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "solver.py", dest / "solver.py")
    meta = {
        "tag": tag,
        "source_freeze": str(src),
        "best_hash": h,
        "seed_base": seed,
        "all_c5_vehicles": veh,
        "all_c5_distance": dist,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if (src / "meta.json").exists():
        meta["source_meta"] = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    (dest / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (dest / "FROZEN.md").write_text(
        f"# {tag}\n\nBest valid solver from OPT_V1 5-seed campaign.\n"
        f"- hash `{h}` seed `{seed}`\n"
        f"- all-C5 vehicles `{veh}` distance `{dist}`\n"
        f"- Do not overwrite OPT_V1.\n",
        encoding="utf-8",
    )
    return dest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen25_coder_14b")
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--seeds", default="11,22,33,44,55")
    parser.add_argument("--max-generations", type=int, default=20)
    parser.add_argument("--candidates-per-role", type=int, default=2)
    parser.add_argument("--beam", type=int, default=2)
    parser.add_argument("--max-llm-calls", type=int, default=400)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument(
        "--run-prefix",
        default="seed",
        help="Run id prefix; seed 11 -> {prefix}11 (use from53_s to avoid clobbering).",
    )
    parser.add_argument("--campaign-prefix", default="opt_seed")
    parser.add_argument("--report-name", default="SLM_EVO_OPT_REPRO_5SEED_REPORT.md")
    parser.add_argument("--summary-name", default="slm_evo_opt_repro_5seed.json")
    parser.add_argument("--parent-label", default="")
    parser.add_argument("--best-tag", default="", help="If set, copy best valid freeze to TAG_hash")
    args = parser.parse_args()

    seeds = [int(x.strip()) for x in args.seeds.split(",") if x.strip()]
    parent_label = args.parent_label or str(args.parent)
    py = sys.executable
    runner = ROOT / "scripts" / "run_slm_evo.py"
    results: list[dict] = []

    for seed in seeds:
        run_id = f"{args.run_prefix}{seed}"
        existing = _load_result(args.profile, run_id)
        if args.skip_existing and existing:
            print(f"SKIP seed={seed} run_id={run_id} (existing result)", flush=True)
            results.append(existing)
            continue
        cmd = [
            py,
            str(runner),
            "--profile",
            args.profile,
            "--parent",
            str(args.parent),
            "--run-id",
            run_id,
            "--seed",
            str(seed),
            "--campaign-id",
            f"{args.campaign_prefix}{seed}",
            "--max-generations",
            str(args.max_generations),
            "--candidates-per-role",
            str(args.candidates_per_role),
            "--beam",
            str(args.beam),
            "--max-llm-calls",
            str(args.max_llm_calls),
        ]
        print(f"=== START seed={seed} run_id={run_id} parent={args.parent} ===", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            print(f"FAILED seed={seed} exit={proc.returncode}", flush=True)
            sys.exit(proc.returncode or 1)
        loaded = _load_result(args.profile, run_id)
        if not loaded:
            print(f"FAILED: missing result json for run_id={run_id}", flush=True)
            sys.exit(2)
        results.append(loaded)
        print(
            f"=== DONE seed={seed} traj={loaded.get('trajectory_vehicles')!s} ===".encode(
                "ascii", "replace"
            ).decode("ascii"),
            flush=True,
        )

    baseline = None
    if results:
        baseline = (results[0].get("parent_all_c5") or {}).get("vehicles_sum")
    report = write_repro_report(
        profile=args.profile,
        seeds=seeds,
        results=results,
        parent_label=parent_label,
        report_name=args.report_name,
        baseline_veh=baseline,
    )
    summary = ROOT / "results" / "md" / "tables" / "raw_autolab" / args.summary_name
    best_overall = None
    if args.best_tag:
        sys.path.insert(0, str(ROOT / "src"))
        best_overall = _freeze_best_overall(results, tag=args.best_tag)
        if best_overall:
            print(f"froze best overall -> {best_overall}", flush=True)

    summary.write_text(
        json.dumps(
            {
                "seeds": seeds,
                "profile": args.profile,
                "parent": str(args.parent),
                "parent_label": parent_label,
                "best_overall": str(best_overall) if best_overall else None,
                "results": [
                    {
                        "seed": r.get("seed_base"),
                        "run_id": r.get("run_id"),
                        "trajectory_vehicles": r.get("trajectory_vehicles"),
                        "final_veh": (r.get("all_c5") or {}).get("vehicles_sum"),
                        "feasible": (r.get("all_c5") or {}).get("feasible"),
                        "total": (r.get("all_c5") or {}).get("total"),
                        "improved": r.get("improved_vs_parent"),
                        "freeze_dir": r.get("freeze_dir"),
                        "best_hash": r.get("best_hash"),
                    }
                    for r in results
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {report}")
    print(f"wrote {summary}")


if __name__ == "__main__":
    main()
