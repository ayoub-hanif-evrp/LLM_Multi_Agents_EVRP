"""Batch seeded P1.3 repair repeats (frozen protocol; Ollama seed only)."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (11, 22, 33, 44, 55)
PROFILES = ("qwen25_coder_7b", "deepseek_coder_67b", "codellama_7b")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="*", default=list(PROFILES))
    parser.add_argument("--seeds", nargs="*", type=int, default=list(SEEDS))
    args = parser.parse_args()

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    log_path = ROOT / "results" / "md" / "tables" / "raw_autolab" / "p1_3_seeded_repair_batch_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    jobs = [(p, s) for p in args.profiles for s in args.seeds]
    print(f"P1_3_SEEDED_REPAIR_BATCH jobs={len(jobs)}", flush=True)
    for i, (profile, seed) in enumerate(jobs, start=1):
        run_id = f"repair_seed{seed}"
        json_out = (
            ROOT / "results" / "md" / "tables" / "raw_autolab" / f"discovery_p1_3_{profile}_{run_id}.json"
        )
        if json_out.exists():
            print(f"[{i}/{len(jobs)}] SKIP existing {profile} {run_id}", flush=True)
            continue
        cmd = [
            str(py),
            str(ROOT / "scripts" / "run_p1_3_regression_safe.py"),
            "--profile",
            profile,
            "--run-id",
            run_id,
            "--llm-seed",
            str(seed),
        ]
        print(f"[{i}/{len(jobs)}] RUN {' '.join(cmd)}", flush=True)
        started = datetime.now(UTC).isoformat()
        proc = subprocess.run(cmd, cwd=str(ROOT))
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "started": started,
                        "finished": datetime.now(UTC).isoformat(),
                        "profile": profile,
                        "llm_seed": seed,
                        "run_id": run_id,
                        "returncode": proc.returncode,
                        "json": str(json_out) if json_out.exists() else None,
                    }
                )
                + "\n"
            )
        if proc.returncode != 0:
            print(f"WARN: {profile} seed={seed} exit={proc.returncode}", flush=True)

    subprocess.run(
        [str(py), str(ROOT / "scripts" / "summarize_p1_3_seeded_repairs.py")],
        cwd=str(ROOT),
        check=False,
    )


if __name__ == "__main__":
    main()
