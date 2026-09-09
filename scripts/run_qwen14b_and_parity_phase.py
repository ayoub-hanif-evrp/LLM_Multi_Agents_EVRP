"""Run Qwen 14B MCB V1 seeds, then SA prompt-parity re-runs; finalize reports.

Does not modify MCB V1. If any from-scratch 4/4 appears, freeze + all-C5 already
happen inside the MCB runner; this script then notes optimization unlock eligibility.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"


def _py() -> Path:
    p = ROOT / ".venv" / "Scripts" / "python.exe"
    return p if p.exists() else Path(sys.executable)


def run(script: str, *args: str) -> int:
    cmd = [str(_py()), str(ROOT / "scripts" / script), *args]
    print(f"\n=== RUN {' '.join(cmd)} ===", flush=True)
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def _any_14b_g4_pass() -> bool:
    for seed in (11, 22, 33, 44, 55):
        path = RAW / f"discovery_mcb_v1_qwen25_coder_14b_seed{seed}.json"
        if not path.exists():
            continue
        j = json.loads(path.read_text(encoding="utf-8"))
        if j.get("G4_PASS") or bool((j.get("gates") or {}).get("G4", {}).get("passed")):
            return True
    return False


def main() -> None:
    # 1) Same-family capacity anchor
    run(
        "run_mcb_v1_seeded_repeats.py",
        "--profiles",
        "qwen25_coder_14b",
        "--seeds",
        "11",
        "22",
        "33",
        "44",
        "55",
    )
    run("summarize_mcb_v1_qwen14b.py")

    # 2) Prompt-parity single-agent re-runs (soft token ceilings unchanged)
    run("run_single_agent_matched_batch.py", "--run-prefix", "single_qwen_parity_seed")
    run("summarize_single_agent_matched_v1.py")

    # 3) Refresh paper artifacts
    run("analyze_qwen_g4_mechanisms.py")
    run("generate_final_experimental_artifacts.py")

    if _any_14b_g4_pass():
        print(
            "\nFROM_SCRATCH_4OF4_DETECTED: MCB runner should already have frozen solver + all-C5. "
            "Optimization unlock is now eligible — run small pilot separately if desired.",
            flush=True,
        )
    else:
        print("\nNO_FROM_SCRATCH_4OF4: optimization remains LOCKED.", flush=True)

    print("\nPHASE_COMPLETE_QWEN14B_AND_PARITY", flush=True)


if __name__ == "__main__":
    main()
