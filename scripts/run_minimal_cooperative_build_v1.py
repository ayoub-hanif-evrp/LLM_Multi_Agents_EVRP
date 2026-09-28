"""Run MINIMAL_COOPERATIVE_BUILD_V1 empty-workspace synthesis.

Usage:
  python scripts/run_minimal_cooperative_build_v1.py --profile deepseek_coder_67b --run-id synth04
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

from evrptw_autolab.build.code_integrity import ast_valid  # noqa: E402
from evrptw_autolab.build.minimal_cooperative_build_v1 import (  # noqa: E402
    run_minimal_cooperative_build_v1,
)
from evrptw_autolab.build.p1_minimal import _code_hash  # noqa: E402
from evrptw_autolab.build.runtime_integrity import find_hardcoded_node_ids  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402


def _safe_run_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip())
    if not cleaned:
        raise ValueError("empty --run-id")
    return cleaned


def _mechanism_diversity(agent_log: list) -> dict:
    """Post-hoc reporting only — does not affect synthesis behavior."""
    algo = [x for x in agent_log if x.get("kind") == "algo_draft"]
    hashes = []
    for x in agent_log:
        if x.get("kind") == "campaign_summary":
            hashes = list(x.get("committed_hashes") or [])
    charging_rounds = sum(1 for x in algo if x.get("agent") == "charging")
    families = sorted({str(x.get("family") or "") for x in algo if x.get("family")})
    return {
        "algo_drafts": len(algo),
        "charging_algo_drafts": charging_rounds,
        "feasibility_families_seen": families,
        "committed_hash_count": len(hashes),
        "distinct_committed_hashes": len(set(hashes)),
    }


def _levels(gates: dict, g4: str, all_c5: dict | None) -> dict:
    g0 = bool(gates.get("G0", {}).get("passed"))
    g1 = bool(gates.get("G1", {}).get("passed"))
    g2 = bool(gates.get("G2", {}).get("passed"))
    g3 = bool(gates.get("G3", {}).get("passed"))
    g4p = bool(gates.get("G4", {}).get("passed"))
    try:
        g4_ok = int(str(g4).split("/")[0])
    except (ValueError, IndexError):
        g4_ok = 0
    c5_ok = int((all_c5 or {}).get("feasible") or 0)
    c5_tot = int((all_c5 or {}).get("total") or 0)
    return {
        "B0_executable": g0,
        "B1_G1_G3": g0 and g1 and g2 and g3,
        "B2_at_least_1_of_4_G4": g4_ok >= 1,
        "B3_G4_4_of_4": g4p,
        "B4_all_C5_ge_10_of_12": c5_tot >= 12 and c5_ok >= 10,
        "Strong_B_12_of_12": c5_tot >= 12 and c5_ok == 12,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="deepseek_coder_67b")
    parser.add_argument("--run-id", default="synth04")
    parser.add_argument("--max-llm-budget", type=int, default=80)
    parser.add_argument(
        "--llm-seed",
        type=int,
        default=None,
        help="Ollama generation seed (experimental RNG only; does not change MCB V1)",
    )
    args = parser.parse_args()
    run_id = _safe_run_id(args.run_id)
    if run_id in {"synth01", "synth02", "synth03"}:
        print(f"REFUSED: {run_id} is a permanent prior record. Use synth04+.")
        sys.exit(2)

    profile = resolve_profile(args.profile)
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 180.0),
        num_ctx=min(profile.num_ctx, 4096),
        keep_alive="10m",
        seed=args.llm_seed,
    )
    if availability(profile, backend) != "installed":
        print(f"FAILED: model not installed ({args.profile})")
        sys.exit(2)

    workspace = ROOT / "workspace" / "discovery_mcb_v1" / profile.id / run_id
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    print(
        f"MINIMAL_COOPERATIVE_BUILD_V1 model={profile.model} run_id={run_id} "
        f"llm_seed={args.llm_seed} budget={args.max_llm_budget}",
        flush=True,
    )
    report = run_minimal_cooperative_build_v1(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_budget=args.max_llm_budget,
    )

    solver_path = Path(report.solver_path)
    source = solver_path.read_text(encoding="utf-8") if solver_path.exists() else ""
    gates = {
        name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
        for name, g in report.gates.items()
    }
    summary = next((x for x in report.agent_log if x.get("kind") == "campaign_summary"), {})
    all_c5 = report.c5_generalization or None
    levels = _levels(gates, report.g4_progress, all_c5)
    primary = summary.get("primary_failure")

    if report.gates.get("G4") and report.gates["G4"].passed and source:
        art = ROOT / "results" / "md" / "artifacts" / "mcb_v1" / profile.id / run_id
        art.mkdir(parents=True, exist_ok=True)
        (art / "solver.py").write_text(source, encoding="utf-8")
        freeze = ROOT / "results" / "md" / "artifacts" / "mcb_v1" / "FEASIBLE_SOLVER_DEEPSEEK_V0"
        freeze.mkdir(parents=True, exist_ok=True)
        (freeze / "solver.py").write_text(source, encoding="utf-8")
        (freeze / "meta.json").write_text(
            json.dumps(
                {
                    "protocol": "MINIMAL_COOPERATIVE_BUILD_V1",
                    "model": profile.model,
                    "run_id": run_id,
                    "hash": _code_hash(source)[:16],
                    "G4": report.g4_progress,
                    "all_c5": all_c5,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    out = {
        "protocol": "MINIMAL_COOPERATIVE_BUILD_V1",
        "experiment": "empty_workspace_synthesis",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "profile": profile.id,
        "run_id": run_id,
        "empty_at_start": True,
        "seed_provided": args.llm_seed is not None,
        "llm_seed": args.llm_seed,
        "stopped_reason": report.stopped_reason,
        "gates": gates,
        "G4_progress": report.g4_progress,
        "G4_PASS": bool(report.gates.get("G4") and report.gates["G4"].passed),
        "success_levels": levels,
        "llm_calls": report.llm_calls,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "wall_s": report.wall_s,
        "solver_hash": _code_hash(source)[:16] if source else None,
        "solver_path": report.solver_path,
        "roles_invoked": summary.get("roles_invoked") or [],
        "team_incomplete_orchestration": summary.get("team_incomplete_orchestration"),
        "primary_failure": primary,
        "taxonomy_counts": summary.get("taxonomy") or {},
        "committed_hashes": summary.get("committed_hashes") or [],
        "mechanism_diversity": _mechanism_diversity(report.agent_log),
        "all_c5_unchanged": all_c5,
        "ast_valid": ast_valid(source)[0] if source else False,
        "agent_log": report.agent_log,
        "checkpoints": str(workspace / "checkpoints"),
        "protocol_freeze": "results/md/MCB_V1_PROTOCOL_FREEZE.md",
    }

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / f"discovery_mcb_v1_{profile.id}_{run_id}.json"
    json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / f"MCB_V1_{profile.id}_{run_id}_REPORT.md"
    lines = [
        "# MINIMAL_COOPERATIVE_BUILD_V1",
        "",
        f"**Model:** `{profile.model}` | **run_id:** `{run_id}` | **llm_seed:** `{args.llm_seed}`",
        f"**Stopped:** {report.stopped_reason}",
        f"**G4:** {report.g4_progress} | **PASS:** {out['G4_PASS']}",
        f"**Calls:** {report.llm_calls} | **tokens:** {report.prompt_tokens}/{report.completion_tokens} | "
        f"**wall:** {report.wall_s}s",
        f"**Roles invoked:** {out['roles_invoked']}",
        f"**Team incomplete orchestration:** {out['team_incomplete_orchestration']}",
        f"**Primary failure:** {primary}",
        f"**Taxonomy:** {out['taxonomy_counts']}",
        f"**Mechanism diversity (reporting):** {out['mechanism_diversity']}",
        "",
        "## Success levels",
        "",
    ]
    for k, v in levels.items():
        lines.append(f"- **{k}:** {v}")
    lines.extend(["", "## Gates", ""])
    for name, g in gates.items():
        lines.append(f"- **{name}:** {'PASS' if g['passed'] else 'FAIL'} — {g['detail']}")
    if all_c5:
        lines.extend(["", f"## All C5: {all_c5['feasible']}/{all_c5['total']}", ""])
        for iid, st in all_c5["by_instance"].items():
            lines.append(f"- `{iid}`: {st}")
    lines.extend(["", f"**Committed hashes:** {out['committed_hashes']}", ""])
    md.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "stopped_reason",
                    "G4_progress",
                    "G4_PASS",
                    "llm_seed",
                    "success_levels",
                    "llm_calls",
                    "wall_s",
                    "roles_invoked",
                    "team_incomplete_orchestration",
                    "primary_failure",
                    "taxonomy_counts",
                    "mechanism_diversity",
                    "all_c5_unchanged",
                )
            },
            indent=2,
        )
    )
    print(f"wrote {md}", flush=True)
    print(f"wrote {json_path}", flush=True)


if __name__ == "__main__":
    main()
