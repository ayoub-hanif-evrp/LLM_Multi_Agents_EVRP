"""Small optimization pilot after from-scratch G4=4/4 unlock.

Starts from a frozen feasible synthesized solver. Does NOT modify MCB V1.
Unlock instruction only (no named metaheuristics in the pilot instruction).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.agents import build_team  # noqa: E402
from evrptw_autolab.build.code_integrity import code_hash  # noqa: E402
from evrptw_autolab.build.minimal_cooperative_build_v1 import (  # noqa: E402
    _all_c5,
    _panel_instances,
    _read,
    _write,
)
from evrptw_autolab.build.p1_minimal import API_SNIPPET, _usage_totals  # noqa: E402
from evrptw_autolab.build.runtime_integrity import (  # noqa: E402
    collect_union_node_ids,
    find_hardcoded_node_ids,
    validate_candidate,
)
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402
from evrptw_autolab.llm.usage import UsageLog  # noqa: E402
from evrptw_autolab.sandbox.limits import RunLimits  # noqa: E402
from evrptw_autolab.sandbox.runner import run_solver  # noqa: E402

UNLOCK = (
    "The current solver is feasible. Improve the lexicographic EVRPTW objective: "
    "first minimize number of vehicles, then total distance. Preserve feasibility. "
    "You choose the algorithm."
)


def _metrics(solver_dir: Path, instances, limits: RunLimits) -> dict:
    by = {}
    ok = 0
    vehicles = 0
    distance = 0.0
    for inst in instances:
        r = run_solver(solver_dir, inst, seed=0, limits=limits)
        if r.feasible and not r.crashed:
            ok += 1
            vehicles += int(r.vehicles or 0)
            distance += float(r.total_distance or 0.0)
            by[inst.instance_id] = {
                "ok": True,
                "vehicles": r.vehicles,
                "distance": r.total_distance,
            }
        else:
            by[inst.instance_id] = {
                "ok": False,
                "fault": str((r.first_fault or {}).get("family") or r.error or "fail")[:80],
            }
    return {
        "feasible": ok,
        "total": len(instances),
        "vehicles_sum": vehicles,
        "distance_sum": round(distance, 4),
        "by_instance": by,
    }


def _ask(agent, current: str, instruction: str) -> str:
    return agent.write_python(
        {
            "optimization_unlocked": True,
            "api_reference": API_SNIPPET,
            "current_solver_py": current,
            "instruction": instruction,
        },
        filename="solver.py",
        marker="def solve",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen25_coder_14b")
    parser.add_argument(
        "--seed-solver",
        default=str(
            ROOT
            / "results"
            / "md"
            / "artifacts"
            / "mcb_v1"
            / "FEASIBLE_SYNTHESIZED_SOLVER_V0_qwen14b_seed33"
            / "solver.py"
        ),
    )
    parser.add_argument("--llm-seed", type=int, default=33)
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument("--max-llm-calls", type=int, default=24)
    args = parser.parse_args()

    profile = resolve_profile(args.profile)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 300.0),
        num_ctx=min(profile.num_ctx, 4096),
        keep_alive="10m",
        seed=args.llm_seed,
    )
    if availability(profile, backend) != "installed":
        print(f"FAILED: model not installed ({args.profile})")
        sys.exit(2)

    seed_solver = Path(args.seed_solver)
    if not seed_solver.exists():
        print(f"FAILED: missing seed solver {seed_solver}")
        sys.exit(2)

    workspace = ROOT / "workspace" / "discovery_opt_pilot" / profile.id / f"seed{args.llm_seed}"
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    current = workspace / "current"
    draft = workspace / "draft"
    current.mkdir(parents=True, exist_ok=True)
    draft.mkdir(parents=True, exist_ok=True)
    shutil.copy2(seed_solver, current / "solver.py")

    usage = UsageLog(workspace / "llm_calls.jsonl")
    team = build_team(backend, model=profile.model, usage_log=usage)
    limits = RunLimits(wall_clock_s=20.0)
    panel = _panel_instances(None)
    c5 = _all_c5(None)
    known = collect_union_node_ids(panel + c5)

    initial_panel = _metrics(current, panel, limits)
    initial_c5 = _metrics(current, c5, limits)
    history = []
    started = time.monotonic()
    print(
        f"OPT_PILOT model={profile.model} seed={args.llm_seed} "
        f"initial_panel_veh={initial_panel['vehicles_sum']} "
        f"initial_c5_veh={initial_c5['vehicles_sum']}",
        flush=True,
    )

    best_src = _read(current)
    best_panel = initial_panel
    best_c5 = initial_c5

    for round_i in range(args.max_rounds):
        n, _, _ = _usage_totals(usage)
        if n >= args.max_llm_calls:
            break
        src = _read(current)
        # Architect brief plan
        try:
            plan = team["architect"].run(
                {
                    "task": "OPTIMIZE_PILOT",
                    "instruction": UNLOCK,
                    "current_metrics": {
                        "panel": best_panel,
                        "c5_vehicles_sum": best_c5["vehicles_sum"],
                        "c5_distance_sum": best_c5["distance_sum"],
                    },
                }
            )
            hyp = getattr(plan, "hypothesis", "") or ""
        except Exception as err:  # noqa: BLE001 — pilot bookkeeping
            hyp = f"architect_failed:{err}"
        # Search owns integrated rewrite (single coding pass + optional charging assist)
        instruction = (
            f"{UNLOCK}\nArchitect hypothesis: {hyp}\n"
            f"Current C5 vehicles_sum={best_c5['vehicles_sum']} "
            f"distance_sum={best_c5['distance_sum']}.\n"
            f"{API_SNIPPET}\nReturn complete solver.py only."
        )
        new_src = _ask(team["search"], src, instruction)
        if "def solve" not in (new_src or ""):
            history.append({"round": round_i, "status": "no_solve"})
            continue
        hard = find_hardcoded_node_ids(new_src, known_ids=known)
        if hard:
            history.append({"round": round_i, "status": "hardcoded_blocked", "ids": hard})
            continue
        probe = panel[0]
        val = validate_candidate(new_src, probe=probe, limits=limits, known_ids=known)
        if not val.ok:
            # one mechanical repair
            n, _, _ = _usage_totals(usage)
            if n < args.max_llm_calls:
                new_src = _ask(
                    team["search"],
                    new_src,
                    f"CODING REPAIR only. {val.reason}\n{API_SNIPPET}\nReturn complete solver.py.",
                )
                hard = find_hardcoded_node_ids(new_src, known_ids=known)
                if hard or "def solve" not in (new_src or ""):
                    history.append({"round": round_i, "status": "repair_failed", "reason": val.reason[:200]})
                    continue
                val = validate_candidate(new_src, probe=probe, limits=limits, known_ids=known)
                if not val.ok:
                    history.append({"round": round_i, "status": "runtime_fail", "reason": val.reason[:200]})
                    continue
        _write(draft, new_src)
        trial_dir = workspace / f"trial_{round_i}"
        if trial_dir.exists():
            shutil.rmtree(trial_dir, ignore_errors=True)
        trial_dir.mkdir(parents=True)
        _write(trial_dir, new_src)
        panel_m = _metrics(trial_dir, panel, limits)
        c5_m = _metrics(trial_dir, c5, limits)
        # Accept only if all panel feasible and lex better on C5 (vehicles then distance)
        improved = False
        if panel_m["feasible"] == panel_m["total"] and c5_m["feasible"] == c5_m["total"]:
            if c5_m["vehicles_sum"] < best_c5["vehicles_sum"] or (
                c5_m["vehicles_sum"] == best_c5["vehicles_sum"]
                and c5_m["distance_sum"] + 1e-6 < best_c5["distance_sum"]
            ):
                improved = True
                best_src = new_src
                best_panel = panel_m
                best_c5 = c5_m
                _write(current, new_src)
        history.append(
            {
                "round": round_i,
                "hypothesis": hyp[:240],
                "improved": improved,
                "panel": panel_m,
                "c5": {"feasible": c5_m["feasible"], "vehicles_sum": c5_m["vehicles_sum"], "distance_sum": c5_m["distance_sum"]},
                "hash": code_hash(new_src)[:16],
            }
        )
        print(
            f"round={round_i} improved={improved} "
            f"c5_veh={c5_m['vehicles_sum']} c5_dist={c5_m['distance_sum']} "
            f"feas={c5_m['feasible']}/{c5_m['total']}",
            flush=True,
        )

    n, p, c = _usage_totals(usage)
    out = {
        "protocol": "OPTIMIZATION_PILOT_V0",
        "unlock_instruction": UNLOCK,
        "model": profile.model,
        "profile": profile.id,
        "llm_seed": args.llm_seed,
        "seed_solver": str(seed_solver),
        "initial_panel": initial_panel,
        "initial_c5": initial_c5,
        "final_panel": best_panel,
        "final_c5": best_c5,
        "vehicles_initial": initial_c5["vehicles_sum"],
        "vehicles_final": best_c5["vehicles_sum"],
        "distance_initial": initial_c5["distance_sum"],
        "distance_final": best_c5["distance_sum"],
        "improved": best_c5["vehicles_sum"] < initial_c5["vehicles_sum"]
        or best_c5["distance_sum"] + 1e-6 < initial_c5["distance_sum"],
        "history": history,
        "llm_calls": n,
        "prompt_tokens": p,
        "completion_tokens": c,
        "wall_s": round(time.monotonic() - started, 1),
        "final_solver_hash": code_hash(best_src)[:16],
        "timestamp": datetime.now(UTC).isoformat(),
    }
    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / f"opt_pilot_{profile.id}_seed{args.llm_seed}.json"
    json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    art = ROOT / "results" / "md" / "artifacts" / "opt_pilot" / profile.id / f"seed{args.llm_seed}"
    art.mkdir(parents=True, exist_ok=True)
    (art / "solver.py").write_text(best_src, encoding="utf-8")
    (art / "meta.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / "OPTIMIZATION_PILOT_REPORT.md"
    md.write_text(
        "\n".join(
            [
                "# Optimization pilot (post from-scratch 4/4)",
                "",
                f"**Model:** `{profile.model}` | seed=`{args.llm_seed}`",
                f"**Unlock:** {UNLOCK}",
                "",
                f"- initial C5 vehicles_sum=`{initial_c5['vehicles_sum']}` distance=`{initial_c5['distance_sum']}`",
                f"- final C5 vehicles_sum=`{best_c5['vehicles_sum']}` distance=`{best_c5['distance_sum']}`",
                f"- improved=`{out['improved']}`",
                f"- llm_calls=`{n}` wall_s=`{out['wall_s']}`",
                f"- final hash=`{out['final_solver_hash']}`",
                "",
                "## Rounds",
                "",
            ]
            + [
                f"- round {h.get('round')}: improved={h.get('improved')} "
                f"c5_veh={(h.get('c5') or {}).get('vehicles_sum')} status={h.get('status', 'ok')}"
                for h in history
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({k: out[k] for k in (
        "vehicles_initial", "vehicles_final", "distance_initial", "distance_final",
        "improved", "llm_calls", "wall_s", "final_solver_hash",
    )}, indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
