"""Master pipeline: single-agent baseline → seeded repairs → final paper artifacts.

Does not modify MCB V1 or P1.3 protocol logic.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _py() -> Path:
    p = ROOT / ".venv" / "Scripts" / "python.exe"
    return p if p.exists() else Path(sys.executable)


def run(script: str, *args: str) -> int:
    cmd = [str(_py()), str(ROOT / "scripts" / script), *args]
    print(f"\n=== RUN {' '.join(cmd)} ===", flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def main() -> None:
    # 1) Single-agent matched baseline (5 seeds)
    rc = run("run_single_agent_matched_batch.py")
    if rc != 0:
        print(f"WARN: single-agent batch rc={rc}", flush=True)

    # 2) Seeded P1.3 repairs (3 models × 5 seeds)
    rc = run("run_p1_3_seeded_repairs.py")
    if rc != 0:
        print(f"WARN: repair batch rc={rc}", flush=True)

    # 3) Analyses + final reports (always attempt)
    for script in (
        "analyze_qwen_g4_mechanisms.py",
        "generate_final_experimental_artifacts.py",
    ):
        path = ROOT / "scripts" / script
        if path.exists():
            run(script)
        else:
            print(f"SKIP missing {script}", flush=True)

    print("\nMASTER_PIPELINE_DONE", flush=True)


if __name__ == "__main__":
    main()
