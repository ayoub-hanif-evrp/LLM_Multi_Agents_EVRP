"""P1.1 — keep five-agent solver; push G4 to 4/4 (r105C5 WINDOW). No redesign.

Seeds from FEASIBLE_SOLVER_V0 / artifact solver. Does not unlock optimization.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.build.p1_minimal import run_p1_1_window_fix  # noqa: E402
from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402


def _find_seed() -> Path:
    candidates = [
        ROOT / "results" / "md" / "artifacts" / "p1_minimal" / "FEASIBLE_SOLVER_V0_solver.py",
        ROOT / "results" / "md" / "artifacts" / "p1_minimal" / "solver.py",
        ROOT / "workspace" / "discovery_p1_minimal" / "qwen25_coder_7b" / "FEASIBLE_SOLVER_V0" / "solver.py",
        ROOT / "workspace" / "discovery_p1_minimal" / "qwen25_coder_7b" / "current" / "solver.py",
    ]
    for path in candidates:
        if path.exists() and "def solve" in path.read_text(encoding="utf-8"):
            return path
    raise FileNotFoundError("No P1 seed solver found; run P1 first.")


def main() -> None:
    profile = resolve_profile("qwen25_coder_7b")
    backend = OllamaBackend(timeout_s=180.0, num_ctx=min(profile.num_ctx, 4096), keep_alive="10m")
    status = availability(profile, backend)
    if status != "installed":
        print(f"FAILED: model not installed ({status})")
        sys.exit(2)
    seed = _find_seed()
    workspace = ROOT / "workspace" / "discovery_p1_1" / profile.id
    if workspace.exists():
        import shutil

        shutil.rmtree(workspace, ignore_errors=True)
    print(f"P1.1_WINDOW_FIX model={profile.model} seed={seed}", flush=True)
    report = run_p1_1_window_fix(
        model=profile.model,
        backend=backend,
        workspace=workspace,
        seed_solver=seed,
        temperatures=profile.temperatures,
        max_llm_budget=60,
    )
    out = {
        "protocol": "P1.1_WINDOW_FIX",
        "timestamp": datetime.now(UTC).isoformat(),
        "model": profile.model,
        "seed": str(seed),
        "stopped_reason": report.stopped_reason,
        "gates": {
            name: {"passed": g.passed, "detail": g.detail, "agent": g.agent}
            for name, g in report.gates.items()
        },
        "G4_progress": report.g4_progress,
        "G4_PASS": report.gates.get("G4") is not None and report.gates["G4"].passed,
        "llm_calls": report.llm_calls,
        "prompt_tokens": report.prompt_tokens,
        "completion_tokens": report.completion_tokens,
        "wall_s": report.wall_s,
        "solver_path": report.solver_path,
        "agent_log": report.agent_log,
        "c5_generalization": report.c5_generalization,
    }
    artifact_dir = ROOT / "results" / "md" / "artifacts" / "p1_1"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    solver_src = Path(report.solver_path)
    if solver_src.exists():
        (artifact_dir / "solver.py").write_text(solver_src.read_text(encoding="utf-8"), encoding="utf-8")
        out["solver_artifact"] = str(artifact_dir / "solver.py")

    dest = ROOT / "results" / "md" / "tables" / "raw_autolab"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / "discovery_p1_1_qwen25_coder_7b.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    md = ROOT / "results" / "md" / "P1_1_WINDOW_REPORT.md"
    lines = [
        "# P1.1 WINDOW fix (G4 → 4/4)",
        "",
        f"**Model:** `{profile.model}`",
        f"**Seed:** `{seed}`",
        f"**Stopped:** {report.stopped_reason}",
        f"**Wall:** {report.wall_s}s | **LLM calls:** {report.llm_calls} | "
        f"**prompt_tokens:** {report.prompt_tokens} | **completion_tokens:** {report.completion_tokens}",
        "",
        f"**G4 progress:** {report.g4_progress}",
        f"**G4 PASS (requires 4/4):** {report.gates.get('G4').passed if report.gates.get('G4') else False}",
        "",
        "| Gate | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for name in ("G0", "G1", "G2", "G3", "G4"):
        g = report.gates.get(name)
        if g is None:
            lines.append(f"| {name} | — | not reached |")
        else:
            label = "PASS" if g.passed else ("PARTIAL" if name == "G4" else "FAIL")
            lines.append(f"| {name} | {label} | {g.detail} |")
    if report.c5_generalization:
        gen = report.c5_generalization
        lines.extend(
            [
                "",
                "## All Schneider C5 (frozen solver, unchanged)",
                f"**{gen.get('feasible')}/{gen.get('total')}** feasible",
                "",
            ]
        )
        for iid, status in (gen.get("by_instance") or {}).items():
            lines.append(f"- `{iid}`: {status}")
    lines.extend(["", f"**solver:** `{report.solver_path}`", ""])
    md.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                k: out[k]
                for k in ("stopped_reason", "G4_progress", "G4_PASS", "llm_calls", "wall_s", "c5_generalization")
            },
            indent=2,
        )
    )
    print(f"wrote {md}", flush=True)
    print(f"wrote {path}", flush=True)


if __name__ == "__main__":
    main()
