"""Run P1.3 regression-safe repair on the fixed 3/4 seed (cross-model Experiment A).

Usage:
    python scripts/run_p1_3_regression_safe.py --profile deepseek_coder_67b --run-id repair01
    python scripts/run_p1_3_regression_safe.py --profile codellama_7b --run-id repair01

Protocol logic is frozen in p1_3_regression_safe.py. This script only bookkeeping.
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

from evrptw_autolab.build.p1_3_regression_safe import (  # noqa: E402
    DEFAULT_MAX_LLM_CALLS,
    run_p1_3_regression_safe,
)
from evrptw_autolab.build.p1_minimal import _code_hash  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402


def _find_seed() -> Path:
    candidates = [
        ROOT / "results" / "md" / "artifacts" / "p1_minimal" / "FEASIBLE_SOLVER_V0_solver.py",
        ROOT / "results" / "md" / "artifacts" / "p1_minimal" / "solver.py",
        ROOT / "workspace" / "discovery_p1_minimal" / "qwen25_coder_7b" / "FEASIBLE_SOLVER_V0" / "solver.py",
    ]
    for path in candidates:
        if path.exists() and "def solve" in path.read_text(encoding="utf-8"):
            return path
    raise FileNotFoundError("No P1 3/4 seed solver found")


def _safe_run_id(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw.strip())
    if not cleaned:
        raise ValueError("empty --run-id")
    return cleaned


def _summarize(report_dict: dict) -> dict:
    provenance = report_dict.get("provenance") or []
    agent_log = report_dict.get("agent_log") or []
    non_noop = [
        p
        for p in provenance
        if not p.get("noop") and p.get("hash") and p.get("hash") != p.get("parent_hash")
    ]
    distinct_hashes = sorted({p.get("hash") for p in non_noop if p.get("hash")})
    architect = any(x.get("kind") == "architect_escalation" for x in agent_log)
    regressions = sum(1 for x in agent_log if x.get("kind") == "regression_transaction")
    promote = next((x for x in agent_log if x.get("kind") == "promote"), None)
    baseline = next((x for x in agent_log if x.get("kind") == "best_baseline"), None)
    best_path = report_dict.get("best_path") or report_dict.get("solver_path")
    best_hash = None
    if best_path and Path(best_path).exists():
        best_hash = _code_hash(Path(best_path).read_text(encoding="utf-8"))[:16]
    return {
        "model": report_dict.get("model"),
        "profile": report_dict.get("profile"),
        "run_id": report_dict.get("run_id"),
        "initial_score": (baseline or {}).get("score") or "3/4",
        "final_best_score": report_dict.get("G4_progress"),
        "success_4of4": bool(report_dict.get("G4_PASS")),
        "llm_calls": report_dict.get("llm_calls"),
        "prompt_tokens": report_dict.get("prompt_tokens"),
        "completion_tokens": report_dict.get("completion_tokens"),
        "distinct_non_noop_patches": len(distinct_hashes),
        "architect_called": architect,
        "regressions_generated": regressions,
        "winning_agent": (promote or {}).get("via") or ((promote or {}).get("agent") if promote else None),
        "final_solver_hash": best_hash,
        "stopped_reason": report_dict.get("stopped_reason"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen25_coder_7b")
    parser.add_argument("--run-id", default="repair01", help="Non-behavioral experiment id for paths only")
    parser.add_argument("--max-llm-calls", type=int, default=DEFAULT_MAX_LLM_CALLS)
    parser.add_argument(
        "--llm-seed",
        type=int,
        default=None,
        help="Ollama generation seed (experimental RNG only; does not change P1.3 protocol)",
    )
    args = parser.parse_args()
    run_id = _safe_run_id(args.run_id)

    profile = resolve_profile(args.profile)
    backend = OllamaBackend(
        timeout_s=180.0,
        num_ctx=min(profile.num_ctx, 4096),
        keep_alive="10m",
        seed=args.llm_seed,
    )
    if availability(profile, backend) != "installed":
        print(f"FAILED: model not installed ({args.profile})")
        sys.exit(2)

    seed = _find_seed()
    workspace = ROOT / "workspace" / "discovery_p1_3" / profile.id / run_id
    if workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)

    print(
        f"P1.3_REGRESSION_SAFE model={profile.model} profile={profile.id} "
        f"run_id={run_id} llm_seed={args.llm_seed} seed_solver={seed} "
        f"max_calls={args.max_llm_calls}",
        flush=True,
    )
    report = run_p1_3_regression_safe(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        seed_solver=seed,
        temperatures=profile.temperatures,
        max_llm_calls=args.max_llm_calls,
    )

    provenance = []
    for row in report.agent_log:
        if row.get("kind") == "provenance":
            provenance = row.get("entries") or []

    out = {
        "protocol": "P1.3_REGRESSION_SAFE",
        "experiment": "cross_model_repair_common_seed",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "profile": profile.id,
        "run_id": run_id,
        "llm_seed": args.llm_seed,
        "seed_provided": args.llm_seed is not None,
        "seed": str(seed),
        "stopped_reason": report.stopped_reason,
        "gates": {
            name: {"passed": g.passed, "detail": g.detail}
            for name, g in report.gates.items()
        },
        "G4_progress": report.g4_progress,
        "G4_PASS": bool(report.gates.get("G4") and report.gates["G4"].passed),
        "llm_calls": report.llm_calls,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "wall_s": report.wall_s,
        "solver_path": report.solver_path,
        "best_path": str(workspace / "best" / "solver.py"),
        "provenance": provenance,
        "agent_log": report.agent_log,
        "c5_generalization": report.c5_generalization,
    }

    artifact_dir = ROOT / "results" / "md" / "artifacts" / "p1_3" / profile.id / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    best_py = Path(report.solver_path)
    if best_py.exists():
        (artifact_dir / "best_solver.py").write_text(best_py.read_text(encoding="utf-8"), encoding="utf-8")
        out["solver_artifact"] = str(artifact_dir / "best_solver.py")
        # Preserve historical FIRST_4OF4 freeze; seeded replicates get per-run freeze only.
        if out["G4_PASS"]:
            per_freeze = artifact_dir / "FROZEN_4OF4"
            per_freeze.mkdir(parents=True, exist_ok=True)
            (per_freeze / "solver.py").write_text(best_py.read_text(encoding="utf-8"), encoding="utf-8")
            (per_freeze / "meta.json").write_text(
                json.dumps(
                    {
                        "model": profile.model,
                        "profile": profile.id,
                        "run_id": run_id,
                        "llm_seed": args.llm_seed,
                        "hash": _code_hash(best_py.read_text(encoding="utf-8"))[:16],
                        "G4_progress": report.g4_progress,
                        "c5": report.c5_generalization,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            out["frozen_4of4_run"] = str(per_freeze / "solver.py")
            freeze = ROOT / "results" / "md" / "artifacts" / "p1_3" / "P1_3_FIRST_4OF4_SOLVER"
            if run_id == "repair01" or not (freeze / "solver.py").exists():
                freeze.mkdir(parents=True, exist_ok=True)
                (freeze / "solver.py").write_text(best_py.read_text(encoding="utf-8"), encoding="utf-8")
                (freeze / "meta.json").write_text(
                    json.dumps(
                        {
                            "model": profile.model,
                            "profile": profile.id,
                            "run_id": run_id,
                            "llm_seed": args.llm_seed,
                            "hash": _code_hash(best_py.read_text(encoding="utf-8"))[:16],
                            "G4_progress": report.g4_progress,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                out["frozen_4of4"] = str(freeze / "solver.py")

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"discovery_p1_3_{profile.id}_{run_id}.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    summary = _summarize(out)
    out["summary"] = summary
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / f"P1_3_{profile.id}_{run_id}_REPORT.md"
    lines = [
        "# P1.3 Cross-Model Repair (common 3/4 seed)",
        "",
        f"**Experiment:** cross-model EVRPTW code-repair from a common 3/4 seed",
        f"**Model:** `{profile.model}` (`{profile.id}`)",
        f"**Run id:** `{run_id}`",
        f"**Stopped:** {report.stopped_reason}",
        f"**G4 progress (best):** {report.g4_progress} | **G4 PASS (4/4):** {out['G4_PASS']}",
        f"**Wall:** {report.wall_s}s | **LLM calls:** {report.llm_calls} "
        f"(hard cap {args.max_llm_calls}) | "
        f"**prompt_tokens:** {report.prompt_tokens} | **completion_tokens:** {report.completion_tokens}",
        "",
        "## Provenance (code-changing calls)",
        "",
    ]
    for p in provenance:
        lines.append(
            f"- `{p.get('hash')}` parent=`{p.get('parent_hash')}` "
            f"**{p.get('agent')}**/{p.get('change_kind')} "
            f"accepted={p.get('accepted')} after={p.get('panel_after')}"
        )
    if not provenance:
        lines.append("- (none)")
    first = next((x for x in report.agent_log if x.get("kind") == "first_trace"), None)
    if first:
        lines.extend(["", "## First target trace", "", "```", str(first.get("trace") or "")[:4000], "```", ""])
    arch = [x for x in report.agent_log if x.get("kind") == "architect_escalation"]
    lines.extend(["## Architect (max once)", ""])
    if arch:
        for a in arch:
            lines.append(f"- {a.get('hypothesis')} → {a.get('target')}")
    else:
        lines.append("- (not used or not reached)")
    lines.extend(["", f"**best solver:** `{report.solver_path}`", ""])
    if report.c5_generalization:
        gen = report.c5_generalization
        lines.append(f"## All C5: {gen.get('feasible')}/{gen.get('total')}")
        for iid, st in (gen.get("by_instance") or {}).items():
            lines.append(f"- `{iid}`: {st}")
    md.write_text("\n".join(lines), encoding="utf-8")

    # Also refresh a short pointer report (does not erase per-run reports)
    pointer = ROOT / "results" / "md" / "P1_3_REGRESSION_SAFE_REPORT.md"
    pointer.write_text(
        "\n".join(
            [
                "# P1.3 latest run pointer",
                "",
                f"See `{md.name}` for the full report.",
                f"JSON: `{path}`",
                f"Model: `{profile.model}` run_id=`{run_id}` G4={report.g4_progress}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"wrote {md}", flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
