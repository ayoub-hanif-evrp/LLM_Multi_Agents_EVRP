"""Batch MCB V1 seeded empty-workspace repeats (experimental RNG only).

Does NOT change MCB V1 protocol. Seeds: 11,22,33,44,55.
Keeps screen01 / synth04 as preliminary; does not count them as seeded replicates.

Usage:
  python scripts/run_mcb_v1_seeded_repeats.py
  python scripts/run_mcb_v1_seeded_repeats.py --profiles qwen25_coder_7b --seeds 11
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (11, 22, 33, 44, 55)
PROFILES = ("deepseek_coder_67b", "qwen25_coder_7b", "codellama_7b")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="*", default=list(PROFILES))
    parser.add_argument("--seeds", nargs="*", type=int, default=list(SEEDS))
    parser.add_argument("--max-llm-budget", type=int, default=80)
    parser.add_argument("--continue-on-error", action="store_true", default=True)
    args = parser.parse_args()

    log_path = ROOT / "results" / "md" / "tables" / "raw_autolab" / "mcb_v1_seeded_batch_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)

    jobs = [(p, s) for p in args.profiles for s in args.seeds]
    print(f"MCB_V1_SEEDED_BATCH jobs={len(jobs)} seeds={args.seeds} profiles={args.profiles}", flush=True)

    for i, (profile, seed) in enumerate(jobs, start=1):
        run_id = f"seed{seed}"
        json_out = ROOT / "results" / "md" / "tables" / "raw_autolab" / f"discovery_mcb_v1_{profile}_{run_id}.json"
        if json_out.exists():
            print(f"[{i}/{len(jobs)}] SKIP existing {profile} {run_id}", flush=True)
            continue
        cmd = [
            str(py),
            str(ROOT / "scripts" / "run_minimal_cooperative_build_v1.py"),
            "--profile",
            profile,
            "--run-id",
            run_id,
            "--llm-seed",
            str(seed),
            "--max-llm-budget",
            str(args.max_llm_budget),
        ]
        print(f"[{i}/{len(jobs)}] RUN {' '.join(cmd)}", flush=True)
        started = datetime.now(UTC).isoformat()
        proc = subprocess.run(cmd, cwd=str(ROOT))
        row = {
            "started": started,
            "finished": datetime.now(UTC).isoformat(),
            "profile": profile,
            "llm_seed": seed,
            "run_id": run_id,
            "returncode": proc.returncode,
            "json": str(json_out) if json_out.exists() else None,
        }
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")
        if proc.returncode != 0 and not args.continue_on_error:
            sys.exit(proc.returncode)
        if proc.returncode != 0:
            print(f"WARN: {profile} seed={seed} exit={proc.returncode}", flush=True)

    # Summarize after batch
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "summarize_mcb_v1_seeded_repeats.py")],
        cwd=str(ROOT),
        check=False,
    )
    if "deepseek_coder_v2_lite" in args.profiles:
        subprocess.run(
            [str(py), str(ROOT / "scripts" / "summarize_mcb_v1_strong_anchor.py")],
            cwd=str(ROOT),
            check=False,
        )
    if "qwen25_coder_14b" in args.profiles:
        subprocess.run(
            [str(py), str(ROOT / "scripts" / "summarize_mcb_v1_qwen14b.py")],
            cwd=str(ROOT),
            check=False,
        )
    print(f"batch log: {log_path}", flush=True)


if __name__ == "__main__":
    main()
