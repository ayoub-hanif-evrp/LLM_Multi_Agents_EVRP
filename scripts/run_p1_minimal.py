"""Run P1_MINIMAL_COOPERATIVE_SOLVER with Qwen2.5-Coder 7B.

Usage:
    python scripts/run_p1_minimal.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.build.p1_minimal import run_p1_minimal  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402


def main() -> None:
    profile = resolve_profile("qwen25_coder_7b")
    backend = OllamaBackend(timeout_s=180.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    status = availability(profile, backend)
    if status != "installed":
        print(f"FAILED: model not installed ({status})")
        sys.exit(2)
    workspace = ROOT / "workspace" / "discovery_p1_minimal" / profile.id
    if workspace.exists():
        # fresh empty workspace for the protocol
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)
    print(f"P1_MINIMAL_COOPERATIVE_SOLVER model={profile.model}", flush=True)
    report = run_p1_minimal(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_budget=100,
    )
    out = {
        "protocol": "P1_MINIMAL_COOPERATIVE_SOLVER",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "stopped_reason": report.stopped_reason,
        "gates": {
            name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
            for name, g in report.gates.items()
        },
        "G4": f"{report.g4_feasible}/{report.g4_total}",
        "llm_calls": report.llm_calls,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "wall_s": report.wall_s,
        "solver_path": report.solver_path,
        "agent_log": report.agent_log,
    }

    # Persist solver for inspection even if workspace is later cleared.
    artifact_dir = ROOT / "results" / "md" / "artifacts" / "p1_minimal"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    solver_src = Path(report.solver_path)
    if solver_src.exists():
        dest_solver = artifact_dir / "solver.py"
        dest_solver.write_text(solver_src.read_text(encoding="utf-8"), encoding="utf-8")
        out["solver_artifact"] = str(dest_solver)

    attribution: dict[str, list[str]] = {}
    for row in report.agent_log:
        gate = str(row.get("gate") or "")
        agent = str(row.get("agent") or row.get("kind") or "")
        if gate and agent:
            attribution.setdefault(gate, []).append(f"{row.get('kind')}:{agent}")
    out["gate_attribution"] = attribution

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "discovery_p1_minimal_qwen25_coder_7b.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / "P1_MINIMAL_REPORT.md"
    lines = [
        "# P1_MINIMAL_COOPERATIVE_SOLVER",
        "",
        f"**Model:** `{profile.model}`",
        f"**Stopped:** {report.stopped_reason}",
        f"**Wall:** {report.wall_s}s | **LLM calls:** {report.llm_calls} | "
        f"**prompt_tokens:** {report.prompt_tokens} | **completion_tokens:** {report.completion_tokens}",
        "",
        "| Gate | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for name in ("G0", "G1", "G2", "G3", "G4"):
        g = report.gates.get(name)
        if g is None:
            lines.append(f"| {name} | — | not reached |")
        else:
            lines.append(f"| {name} | {'PASS' if g.passed else 'FAIL'} | {g.detail} |")
    lines.extend(
        [
            "",
            f"**G4 panel:** {report.g4_feasible}/{report.g4_total}",
            f"**solver.py:** `{report.solver_path}`",
            f"**artifact copy:** `{out.get('solver_artifact', 'n/a')}`",
            "",
            "## Gate attribution (agent changes)",
            "",
        ]
    )
    for name in ("G0", "G1", "G2", "G3", "G4"):
        steps = attribution.get(name) or ["—"]
        lines.append(f"- **{name}:** {', '.join(steps)}")
    lines.extend(
        [
            "",
            "P0 results remain archived and unchanged under `results/md/archive_p0_clean/`.",
            "",
        ]
    )
    md.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({k: out[k] for k in ("stopped_reason", "gates", "G4", "llm_calls", "wall_s")}, indent=2))
    print(f"wrote {md}", flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
