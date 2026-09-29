"""Run the frozen paper campaign in order. Existing result JSON files are kept."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(script: str, *args: str) -> None:
    command = [sys.executable, str(ROOT / "scripts" / script), *args]
    print("RUN " + " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=False)


def main() -> None:
    _run("run_five_agent.py", "--all")
    _run("run_single_agent.py", "--all")
    _run("run_evolution.py", "--all")
    _run("evaluate_solver.py", "--final")
    _run("generate_paper_results.py")


if __name__ == "__main__":
    main()
