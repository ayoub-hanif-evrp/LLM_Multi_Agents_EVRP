"""Run P1.5 runtime-safe empty-workspace synthesis (DeepSeek).

Usage:
  python scripts/run_p1_5_empty_workspace.py --profile deepseek_coder_67b --run-id synth03
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
from evrptw_autolab.build.p1_5_runtime_safe import run_p1_5_empty_workspace  # noqa: E402
from evrptw_autolab.build.p1_minimal import _code_hash  # noqa: E402
from evrptw_autolab.build.runtime_integrity import find_hardcoded_node_ids  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402
from evrptw_autolab.problem.micro import micro_g1_one_customer  # noqa: E402


def _safe_run_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip())
    if not cleaned:
        raise ValueError("empty --run-id")
    return cleaned


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
    parser.add_argument("--run-id", default="synth03")
    parser.add_argument("--max-llm-budget", type=int, default=80)
    args = parser.parse_args()
    run_id = _safe_run_id(args.run_id)
    if run_id in {"synth01", "synth02"}:
        print(f"REFUSED: {run_id} is a permanent prior record. Use synth03+.")
        sys.exit(2)

    profile = resolve_profile(args.profile)
    backend = OllamaBackend(timeout_s=180.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    if availability(profile, backend) != "installed":
        print(f"FAILED: model not installed ({args.profile})")
        sys.exit(2)

    workspace = ROOT / "workspace" / "discovery_p1_5" / profile.id / run_id
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "current").mkdir(parents=True, exist_ok=True)
    empty = not any((workspace / "current").glob("*.py"))

    print(
        f"P1.5_RUNTIME_SAFE model={profile.model} run_id={run_id} empty={empty} "
        f"budget={args.max_llm_budget}",
        flush=True,
    )
    report = run_p1_5_empty_workspace(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_budget=args.max_llm_budget,
    )

    solver_path = Path(report.solver_path)
    source = solver_path.read_text(encoding="utf-8") if solver_path.exists() else ""
    hard = find_hardcoded_node_ids(source, micro_g1_one_customer()) if source else []
    gates = {
        name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
        for name, g in report.gates.items()
    }
    all_c5 = report.c5_generalization or None
    levels = _levels(gates, report.g4_progress, all_c5)
    taxonomy = next((x for x in report.agent_log if x.get("kind") == "taxonomy"), {})
    integrity = next((x for x in report.agent_log if x.get("kind") == "integrity_log"), {})

    if report.gates.get("G4") and report.gates["G4"].passed and source:
        art = ROOT / "results" / "md" / "artifacts" / "p1_5" / profile.id / run_id
        art.mkdir(parents=True, exist_ok=True)
        (art / "solver.py").write_text(source, encoding="utf-8")
        freeze = ROOT / "results" / "md" / "artifacts" / "p1_5" / "FEASIBLE_SOLVER_DEEPSEEK_V0"
        freeze.mkdir(parents=True, exist_ok=True)
        (freeze / "solver.py").write_text(source, encoding="utf-8")
        (freeze / "meta.json").write_text(
            json.dumps(
                {
                    "protocol": "P1.5_RUNTIME_SAFE",
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
        "protocol": "P1.5_RUNTIME_SAFE",
        "experiment": "empty_workspace_synthesis",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "profile": profile.id,
        "run_id": run_id,
        "empty_at_start": empty,
        "seed_provided": False,
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
        "all_c5_unchanged": all_c5,
        "hardcoded_id_audit": hard,
        "ast_valid": ast_valid(source)[0] if source else False,
        "taxonomy_counts": taxonomy.get("counts") or {},
        "committed_hashes": taxonomy.get("committed_hashes") or [],
        "mechanical_repair_total": taxonomy.get("mechanical_repair_total"),
        "integrity_entries": integrity.get("entries") or [],
        "agent_log": report.agent_log,
        "checkpoints": str(workspace / "checkpoints"),
        "protocol_freeze": "results/md/P1_5_PROTOCOL_FREEZE.md",
    }

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    json_path = dest / f"discovery_p1_5_{profile.id}_{run_id}.json"
    json_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / f"P1_5_{profile.id}_{run_id}_REPORT.md"
    lines = [
        "# P1.5 Runtime-Safe Synthesis",
        "",
        f"**Model:** `{profile.model}` | **run_id:** `{run_id}`",
        f"**Empty:** {empty} | **Seed:** none",
        f"**Stopped:** {report.stopped_reason}",
        f"**G4:** {report.g4_progress} | **PASS:** {out['G4_PASS']}",
        f"**Calls:** {report.llm_calls} | **tokens:** {report.prompt_tokens}/{report.completion_tokens} | "
        f"**wall:** {report.wall_s}s",
        f"**Mechanical repairs:** {out['mechanical_repair_total']}",
        f"**Taxonomy:** {out['taxonomy_counts']}",
        f"**Hardcoded IDs (final):** {hard or 'NONE'}",
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
    lines.extend(
        [
            "",
            f"**Committed hashes:** {out['committed_hashes']}",
            f"**Checkpoints:** `{workspace / 'checkpoints'}`",
            "",
        ]
    )
    md.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "stopped_reason",
                    "G4_progress",
                    "G4_PASS",
                    "success_levels",
                    "llm_calls",
                    "wall_s",
                    "taxonomy_counts",
                    "mechanical_repair_total",
                    "hardcoded_id_audit",
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
