"""Experiment B — empty-workspace five-agent EVRPTW synthesis (DeepSeek first).

Starts from an EMPTY model workspace (no Qwen seed, no DeepSeek repair artifact).
Reuses the frozen P1 cooperative curriculum G0→G4. Optimization remains locked.

Success levels (predefined, immutable):
  B0  executable solve()
  B1  G1–G3 all feasible
  B2  ≥1/4 G4
  B3  4/4 G4
  B4  frozen solver ≥10/12 all Schneider C5
  Strong B  12/12 all C5

Usage:
  python scripts/run_p1_b_empty_workspace.py --profile deepseek_coder_67b --run-id synth01
"""
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

from evrptw_autolab.build.p1_minimal import (  # noqa: E402
    _code_hash,
    run_p1_minimal,
)
from evrptw_autolab.evaluation.fidelity import by_customer_count, load_all  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402
from evrptw_autolab.sandbox.limits import RunLimits  # noqa: E402
from evrptw_autolab.sandbox.runner import run_solver  # noqa: E402

NODE_LIT_RE = re.compile(r"""['"]([CDS]\d+)['"]""")
FORBIDDEN_MARKERS = ("C78", "r105C5", "r104C5", "c101C5", "c103C5", "FEASIBLE_SOLVER")


def _safe_run_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip())
    if not cleaned:
        raise ValueError("empty --run-id")
    return cleaned


def _assert_empty_start(workspace: Path) -> dict:
    """Workspace must not contain a prior solver seed."""
    existed = workspace.exists()
    if existed:
        shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    current = workspace / "current"
    current.mkdir(parents=True, exist_ok=True)
    leftover = list(current.glob("*.py"))
    return {
        "workspace_cleared": bool(existed),
        "empty_at_start": len(leftover) == 0,
        "solver_py_present_at_start": False,
        "path": str(workspace),
    }


def _eval_all_schneider_c5(solver_dir: Path) -> dict:
    limits = RunLimits(wall_clock_s=20.0)
    c5 = sorted(by_customer_count(load_all(None), [5]), key=lambda i: i.instance_id)
    by: dict[str, str] = {}
    ok = 0
    for inst in c5:
        r = run_solver(solver_dir, inst, seed=0, limits=limits)
        if r.feasible and not r.crashed:
            ok += 1
            by[inst.instance_id] = "OK"
        else:
            by[inst.instance_id] = str((r.first_fault or {}).get("family") or r.error or "fail")[:80]
    return {"feasible": ok, "total": len(c5), "by_instance": by}


def _audit_solver(source: str) -> dict:
    lits = sorted(set(NODE_LIT_RE.findall(source)))
    hard = [x for x in lits if re.match(r"^(C|S)\d+$", x)]  # customers/stations only
    markers = [m for m in FORBIDDEN_MARKERS if m in source]
    return {
        "instance_specific_constants": "NONE" if not hard and not markers else "FOUND",
        "hardcoded_customer_or_station_literals": hard,
        "forbidden_markers_found": markers,
        "basic_mechanism_notes": _infer_mechanism(source),
    }


def _infer_mechanism(source: str) -> str:
    notes = []
    if "for cid in instance.customer_ids" in source or "for customer" in source.lower():
        notes.append("iterates customers")
    if "depot" in source and "customer" in source.lower():
        notes.append("likely dedicated or constructive routes")
    if "propagate_route" in source:
        notes.append("uses propagate_route for feasibility checks")
    if "station" in source.lower() and ("insert" in source.lower() or "+ [" in source or "station_id" in source):
        notes.append("inserts charging stations when needed")
    if "while True" in source:
        notes.append("contains while True (risk)")
    return "; ".join(notes) or "see solver.py"


def _success_levels(gates: dict, g4_progress: str, all_c5: dict | None) -> dict:
    g0 = bool(gates.get("G0", {}).get("passed"))
    g1 = bool(gates.get("G1", {}).get("passed"))
    g2 = bool(gates.get("G2", {}).get("passed"))
    g3 = bool(gates.get("G3", {}).get("passed"))
    g4 = bool(gates.get("G4", {}).get("passed"))
    try:
        g4_ok = int(str(g4_progress).split("/")[0])
    except (ValueError, IndexError):
        g4_ok = 0
    c5_ok = int((all_c5 or {}).get("feasible") or 0)
    c5_tot = int((all_c5 or {}).get("total") or 12)
    return {
        "B0_executable": g0,
        "B1_G1_G3": g0 and g1 and g2 and g3,
        "B2_at_least_1_of_4_G4": g4_ok >= 1,
        "B3_G4_4_of_4": g4,
        "B4_all_C5_ge_10_of_12": bool(all_c5) and c5_ok >= 10 and c5_tot >= 12,
        "Strong_B_12_of_12": bool(all_c5) and c5_ok == 12 and c5_tot == 12,
        "g4_feasible": g4_ok,
        "all_c5_feasible": c5_ok,
        "all_c5_total": c5_tot,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="deepseek_coder_67b")
    parser.add_argument("--run-id", default="synth01")
    parser.add_argument("--max-llm-budget", type=int, default=80)
    args = parser.parse_args()
    run_id = _safe_run_id(args.run_id)

    profile = resolve_profile(args.profile)
    backend = OllamaBackend(timeout_s=180.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    if availability(profile, backend) != "installed":
        print(f"FAILED: model not installed ({args.profile})")
        sys.exit(2)

    workspace = ROOT / "workspace" / "discovery_p1_b" / profile.id / run_id
    empty_meta = _assert_empty_start(workspace)

    print(
        f"EXPERIMENT_B_EMPTY_WORKSPACE model={profile.model} profile={profile.id} "
        f"run_id={run_id} empty={empty_meta['empty_at_start']} budget={args.max_llm_budget}",
        flush=True,
    )

    report = run_p1_minimal(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_budget=args.max_llm_budget,
    )

    solver_path = Path(report.solver_path)
    source = solver_path.read_text(encoding="utf-8") if solver_path.exists() else ""
    audit = _audit_solver(source) if source else {"instance_specific_constants": "N/A"}

    all_c5 = None
    frozen_path = None
    if report.gates.get("G4") and report.gates["G4"].passed and solver_path.exists():
        freeze_ws = workspace / "FEASIBLE_SOLVER_DEEPSEEK_V0"
        if freeze_ws.exists():
            shutil.rmtree(freeze_ws, ignore_errors=True)
        shutil.copytree(workspace / "current", freeze_ws)
        art = ROOT / "results" / "md" / "artifacts" / "p1_b" / profile.id / run_id
        art.mkdir(parents=True, exist_ok=True)
        (art / "solver.py").write_text(source, encoding="utf-8")
        frozen_global = ROOT / "results" / "md" / "artifacts" / "p1_b" / "FEASIBLE_SOLVER_DEEPSEEK_V0"
        frozen_global.mkdir(parents=True, exist_ok=True)
        (frozen_global / "solver.py").write_text(source, encoding="utf-8")
        frozen_path = str(frozen_global / "solver.py")
        all_c5 = _eval_all_schneider_c5(freeze_ws)
        (frozen_global / "ALL_C5.json").write_text(json.dumps(all_c5, indent=2), encoding="utf-8")
        (frozen_global / "AUDIT.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
        (frozen_global / "meta.json").write_text(
            json.dumps(
                {
                    "experiment": "B_empty_workspace_synthesis",
                    "model": profile.model,
                    "profile": profile.id,
                    "run_id": run_id,
                    "hash": _code_hash(source)[:16],
                    "G4": report.g4_progress,
                    "all_c5": f"{all_c5['feasible']}/{all_c5['total']}",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    elif solver_path.exists():
        # Still evaluate all-C5 on the final (possibly partial) solver for diagnostics only
        all_c5 = _eval_all_schneider_c5(workspace / "current")

    gates_dict = {
        name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
        for name, g in report.gates.items()
    }
    levels = _success_levels(gates_dict, report.g4_progress, all_c5)

    out = {
        "protocol": "EXPERIMENT_B_EMPTY_WORKSPACE",
        "experiment": "empty_workspace_five_agent_synthesis",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "profile": profile.id,
        "run_id": run_id,
        "empty_workspace": empty_meta,
        "seed_provided": False,
        "qwen_seed_used": False,
        "deepseek_repair_artifact_used": False,
        "stopped_reason": report.stopped_reason,
        "gates": gates_dict,
        "G4_progress": report.g4_progress,
        "G4_PASS": bool(report.gates.get("G4") and report.gates["G4"].passed),
        "success_levels": levels,
        "llm_calls": report.llm_calls,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "wall_s": report.wall_s,
        "solver_path": report.solver_path,
        "solver_hash": _code_hash(source)[:16] if source else None,
        "frozen_path": frozen_path,
        "all_c5_unchanged": all_c5,
        "audit": audit,
        "agent_log": report.agent_log,
    }

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / f"discovery_p1_b_{profile.id}_{run_id}.json"
    json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / f"P1_B_{profile.id}_{run_id}_REPORT.md"
    lines = [
        "# Experiment B — Empty-workspace five-agent synthesis",
        "",
        f"**Model:** `{profile.model}` (`{profile.id}`)",
        f"**Run id:** `{run_id}`",
        f"**Empty at start:** {empty_meta['empty_at_start']} | **Seed provided:** False",
        f"**Stopped:** {report.stopped_reason}",
        f"**G4:** {report.g4_progress} | **G4 PASS:** {out['G4_PASS']}",
        f"**Wall:** {report.wall_s}s | **LLM calls:** {report.llm_calls} | "
        f"**prompt_tokens:** {report.prompt_tokens} | **completion_tokens:** {report.completion_tokens}",
        f"**Solver hash:** `{out['solver_hash']}`",
        "",
        "## Success levels (predefined)",
        "",
    ]
    for k, v in levels.items():
        if k.startswith("B") or k.startswith("Strong"):
            lines.append(f"- **{k}:** {v}")
    lines.extend(["", "## Gates", ""])
    for name, g in gates_dict.items():
        lines.append(f"- **{name}:** {'PASS' if g['passed'] else 'FAIL'} — {g['detail']}")
    if all_c5:
        lines.extend(
            [
                "",
                f"## All Schneider C5 (unchanged): {all_c5['feasible']}/{all_c5['total']}",
                "",
            ]
        )
        for iid, st in all_c5["by_instance"].items():
            lines.append(f"- `{iid}`: {st}")
    lines.extend(
        [
            "",
            "## Instance-specific audit",
            "",
            f"- constants: **{audit.get('instance_specific_constants')}**",
            f"- hardcoded C/S literals: {audit.get('hardcoded_customer_or_station_literals')}",
            f"- mechanism: {audit.get('basic_mechanism_notes')}",
            "",
            f"**solver:** `{report.solver_path}`",
            "",
        ]
    )
    if frozen_path:
        lines.append(f"**frozen:** `{frozen_path}`")
    md.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "stopped_reason": report.stopped_reason,
                "G4_progress": report.g4_progress,
                "G4_PASS": out["G4_PASS"],
                "success_levels": levels,
                "llm_calls": report.llm_calls,
                "wall_s": report.wall_s,
                "all_c5": all_c5,
                "audit": audit.get("instance_specific_constants"),
            },
            indent=2,
        )
    )
    print(f"wrote {md}", flush=True)
    print(f"wrote {json_path}", flush=True)


if __name__ == "__main__":
    main()
