"""CLI for SLM-Evo verifier-guided parallel solver evolution."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import FakeBackend, availability, resolve_profile  # noqa: E402
from evrptw_autolab.slm_evo.evolve import run_slm_evo  # noqa: E402

DEFAULT_PARENT = (
    ROOT
    / "results"
    / "md"
    / "artifacts"
    / "mcb_v1"
    / "FEASIBLE_SYNTHESIZED_SOLVER_V0_qwen14b_seed33"
    / "solver.py"
)


def _safe_run_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip())
    if not cleaned:
        raise ValueError("empty --run-id")
    return cleaned


def _fake_backend_for_smoke() -> FakeBackend:
    good = json.dumps(
        {
            "hypothesis": "add unused helper (smoke)",
            "ops": [
                {
                    "action": "ADD",
                    "symbol": "smoke_helper",
                    "code": "def smoke_helper(x):\n    return x\n",
                }
            ],
        }
    )
    bad = "not-json"
    return FakeBackend(
        {
            "architect": [good, bad],
            "routing": [good, bad],
            "charging": [good, bad],
            "search": [good, bad],
            "critic_inventor": [good, bad],
            "slm_evo_patcher": [good, bad],
        }
    )


def write_run_report(result: dict, *, model: str, parent: Path, profile_id: str, run_id: str) -> Path:
    md = ROOT / "results" / "md" / f"SLM_EVO_{profile_id}_{run_id}_REPORT.md"
    if run_id.startswith("seed") or "seed" in run_id:
        md = ROOT / "results" / "md" / f"SLM_EVO_{run_id.upper()}_REPORT.md"
        # prefer SLM_EVO_SEED{N}_REPORT.md
        seed = result.get("seed_base")
        if seed:
            md = ROOT / "results" / "md" / f"SLM_EVO_SEED{seed}_REPORT.md"

    lines = [
        f"# SLM-Evo — `{run_id}`",
        "",
        f"**Model:** `{model}` | **parent:** `{parent}`",
        f"**seed_base:** `{result.get('seed_base')}` | **campaign:** `{result.get('campaign_id')}`",
        f"**trajectory (all-C5 vehicles):** `{result.get('trajectory_vehicles')}`",
        f"**improved_vs_parent:** `{result.get('improved_vs_parent')}`",
        f"**milestone_hit:** `{result.get('milestone_hit')}` "
        f"(`{result.get('milestone_instance')}`)",
        f"**best_hash:** `{result.get('best_hash')}`",
        f"**panel vehicles_sum:** `{(result.get('best_panel') or {}).get('vehicles_sum')}`",
        f"**all_c5:** `{(result.get('all_c5') or {}).get('feasible')}/"
        f"{(result.get('all_c5') or {}).get('total')}` "
        f"vehicles=`{(result.get('all_c5') or {}).get('vehicles_sum')}` "
        f"(parent vehicles=`{(result.get('parent_all_c5') or {}).get('vehicles_sum')}`)",
        f"**generations:** `{result.get('generations')}` | **llm_calls:** `{result.get('llm_calls')}` "
        f"| **wall_s:** `{result.get('wall_s')}`",
        f"**freeze:** `{result.get('freeze_dir')}`",
        "",
        "## Trajectory",
        "",
    ]
    for step in result.get("trajectory") or []:
        ops = ", ".join(
            f"{o.get('action')} `{o.get('symbol')}`" for o in (step.get("ops") or [])
        )
        lines.append(
            f"- gen=`{step.get('gen')}` c5_veh=`{step.get('all_c5_veh')}` "
            f"panel_veh=`{step.get('panel_veh')}` feas=`{step.get('all_c5_feasible')}` "
            f"role=`{step.get('role')}` — {step.get('hypothesis')} — {ops}"
        )
    lines.append("")
    accepted = [
        c
        for g in (result.get("generation_reports") or [])
        for c in (g.get("candidates") or [])
        if c.get("accepted")
    ]
    if accepted:
        lines += ["## Accepted mechanisms", ""]
        for cand in accepted:
            ops = ", ".join(
                f"{o.get('action')} `{o.get('symbol')}`" for o in (cand.get("ops") or [])
            )
            lines.append(f"- `{cand.get('candidate_id')}` role=`{cand.get('role')}`: "
                         f"{cand.get('hypothesis')} — {ops}")
        lines.append("")
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen25_coder_14b")
    parser.add_argument("--parent", type=Path, default=DEFAULT_PARENT)
    parser.add_argument("--run-id", default="evo01")
    parser.add_argument("--max-generations", type=int, default=20)
    parser.add_argument("--candidates-per-role", type=int, default=2)
    parser.add_argument("--beam", type=int, default=2)
    parser.add_argument("--max-llm-calls", type=int, default=400)
    parser.add_argument("--seed", type=int, default=0, help="seed_base for proposal RNG")
    parser.add_argument("--campaign-id", default="", help="campaign tag for freeze naming")
    parser.add_argument(
        "--stop-on-milestone",
        action="store_true",
        help="Stop at first panel 5→4 win (legacy V0). Default: run full budget.",
    )
    parser.add_argument("--continuation", action="store_true", help="Freeze as OPT_BEST_CONT_*")
    parser.add_argument("--fake", action="store_true", help="Use FakeBackend smoke (no Ollama)")
    args = parser.parse_args()

    run_id = _safe_run_id(args.run_id)
    parent = args.parent
    if not parent.exists():
        print(f"FAILED: missing parent solver {parent}")
        sys.exit(2)

    if args.fake:
        backend: object = _fake_backend_for_smoke()
        model = "fake"
        profile_id = "fake"
    else:
        profile = resolve_profile(args.profile)
        backend = OllamaBackend(
            timeout_s=float(profile.timeout_s or 300.0),
            num_ctx=min(profile.num_ctx, 4096),
            keep_alive="10m",
            seed=int(args.seed),
        )
        if availability(profile, backend) != "installed":
            print(f"FAILED: model not installed ({args.profile})")
            sys.exit(2)
        model = profile.model
        profile_id = profile.id

    workspace = ROOT / "workspace" / "slm_evo" / profile_id / run_id
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    print(
        f"SLM_EVO model={model} run_id={run_id} seed={args.seed} parent={parent} "
        f"gens={args.max_generations} per_role={args.candidates_per_role} "
        f"stop_on_milestone={args.stop_on_milestone}",
        flush=True,
    )
    result = run_slm_evo(
        model=model,
        backend=backend,
        workspace=workspace,
        parent_solver=parent,
        max_generations=1 if args.fake else args.max_generations,
        candidates_per_role=1 if args.fake else args.candidates_per_role,
        beam_size=args.beam,
        max_llm_calls=20 if args.fake else args.max_llm_calls,
        seed_base=int(args.seed),
        stop_on_milestone=bool(args.stop_on_milestone),
        campaign_id=args.campaign_id or run_id,
        continuation=bool(args.continuation),
    )
    result["run_id"] = run_id
    result["profile"] = profile_id
    result["timestamp"] = datetime.now(UTC).isoformat()
    result["fake"] = bool(args.fake)

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / f"slm_evo_{profile_id}_{run_id}.json"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    md = write_run_report(result, model=model, parent=parent, profile_id=profile_id, run_id=run_id)
    print(json.dumps({k: result.get(k) for k in (
        "seed_base", "improved_vs_parent", "trajectory_vehicles", "milestone_hit",
        "best_hash", "generations", "llm_calls", "wall_s", "freeze_dir",
    )}, indent=2))
    print(f"wrote {json_path}")
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
