"""P1.2 — full stop-trace diagnostics for r105C5 WINDOW; Qwen only; no redesign.

Seeds FEASIBLE_SOLVER_V0. At most ~8 focused algorithmic attempts. G4 PASS = 4/4.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.build.p1_minimal import run_p1_2_temporal_trace  # noqa: E402
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
    raise FileNotFoundError("No P1 seed solver found")


def main() -> None:
    profile = resolve_profile("qwen25_coder_7b")
    backend = OllamaBackend(timeout_s=180.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    if availability(profile, backend) != "installed":
        print("FAILED: model not installed")
        sys.exit(2)
    seed = _find_seed()
    workspace = ROOT / "workspace" / "discovery_p1_2" / profile.id
    if workspace.exists():
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)
    print(f"P1.2_TEMPORAL_TRACE model={profile.model} seed={seed}", flush=True)
    report = run_p1_2_temporal_trace(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        seed_solver=seed,
        temperatures=profile.temperatures,
        max_llm_budget=50,
    )

    hashes = []
    for row in report.agent_log:
        if row.get("kind") == "algo_fix" and row.get("hash"):
            hashes.append(
                {
                    "agent": row.get("agent"),
                    "hash": row.get("hash"),
                    "fault": row.get("fault"),
                    "lesson": row.get("lesson"),
                }
            )
    first_trace = next((x for x in report.agent_log if x.get("kind") == "first_trace"), None)
    architect = [x for x in report.agent_log if x.get("kind") == "architect_escalation"]

    out = {
        "protocol": "P1.2_TEMPORAL_TRACE",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "seed": str(seed),
        "stopped_reason": report.stopped_reason,
        "gates": {
            name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
            for name, g in report.gates.items()
        },
        "G4_progress": report.g4_progress,
        "G4_PASS": bool(report.gates.get("G4") and report.gates["G4"].passed),
        "llm_calls": report.llm_calls,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "wall_s": report.wall_s,
        "solver_path": report.solver_path,
        "first_trace": first_trace,
        "architect_escalations": architect,
        "distinct_code_hashes": hashes,
        "agent_log": report.agent_log,
        "c5_generalization": report.c5_generalization,
    }

    artifact_dir = ROOT / "results" / "md" / "artifacts" / "p1_2"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    solver_src = Path(report.solver_path)
    if solver_src.exists():
        (artifact_dir / "solver.py").write_text(solver_src.read_text(encoding="utf-8"), encoding="utf-8")
        out["solver_artifact"] = str(artifact_dir / "solver.py")

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "discovery_p1_2_qwen25_coder_7b.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / "P1_2_TEMPORAL_REPORT.md"
    lines = [
        "# P1.2 temporal-trace WINDOW repair",
        "",
        f"**Model:** `{profile.model}`",
        f"**Stopped:** {report.stopped_reason}",
        f"**G4 progress:** {report.g4_progress} | **G4 PASS (4/4):** "
        f"{out['G4_PASS']}",
        f"**Wall:** {report.wall_s}s | **LLM calls:** {report.llm_calls} | "
        f"**prompt_tokens:** {report.prompt_tokens} | **completion_tokens:** {report.completion_tokens}",
        "",
        "## First r105C5 trace",
        "",
        "```",
        (first_trace or {}).get("trace", "(none)")[:4000],
        "```",
        "",
        "## Architect escalations",
        "",
    ]
    if architect:
        for a in architect:
            lines.append(f"- hypothesis: {a.get('hypothesis')} → {a.get('target')}")
    else:
        lines.append("- (none)")
    lines.extend(["", "## Distinct code hashes", ""])
    for h in hashes:
        lines.append(f"- `{h['hash']}` by **{h['agent']}** ({h.get('fault')}): {h.get('lesson')}")
    if not hashes:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            f"**solver:** `{report.solver_path}`",
            "",
        ]
    )
    if report.c5_generalization:
        gen = report.c5_generalization
        lines.append(f"## All C5: {gen.get('feasible')}/{gen.get('total')}")
        for iid, st in (gen.get("by_instance") or {}).items():
            lines.append(f"- `{iid}`: {st}")
    md.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                k: out[k]
                for k in (
                    "stopped_reason",
                    "G4_progress",
                    "G4_PASS",
                    "llm_calls",
                    "wall_s",
                    "architect_escalations",
                    "c5_generalization",
                )
            },
            indent=2,
        )
    )
    print(f"wrote {md}", flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
