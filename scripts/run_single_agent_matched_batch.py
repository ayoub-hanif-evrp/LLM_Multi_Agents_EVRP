"""Batch SINGLE_AGENT_MATCHED_V1 for Qwen seeds 11/22/33/44/55."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (11, 22, 33, 44, 55)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="qwen25_coder_7b")
    parser.add_argument("--seeds", nargs="*", type=int, default=list(SEEDS))
    parser.add_argument(
        "--run-prefix",
        default="single_qwen_parity_seed",
        help="Run id prefix (parity re-runs use single_qwen_parity_seed)",
    )
    args = parser.parse_args()

    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)

    log_path = ROOT / "results" / "md" / "tables" / "raw_autolab" / "single_agent_v1_batch_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    jobs = list(args.seeds)
    print(
        f"SINGLE_AGENT_MATCHED_V1_BATCH jobs={len(jobs)} seeds={jobs} prefix={args.run_prefix}",
        flush=True,
    )
    for i, seed in enumerate(jobs, start=1):
        run_id = f"{args.run_prefix}{seed}"
        json_out = (
            ROOT
            / "results"
            / "md"
            / "tables"
            / "raw_autolab"
            / f"discovery_single_agent_v1_{args.profile}_{run_id}.json"
        )
        if json_out.exists():
            print(f"[{i}/{len(jobs)}] SKIP existing {run_id}", flush=True)
            continue
        cmd = [
            str(py),
            str(ROOT / "scripts" / "run_single_agent_matched_v1.py"),
            "--profile",
            args.profile,
            "--llm-seed",
            str(seed),
            "--run-id",
            run_id,
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
                        "seed": seed,
                        "run_id": run_id,
                        "returncode": proc.returncode,
                        "json": str(json_out) if json_out.exists() else None,
                    }
                )
                + "\n"
            )
        if proc.returncode != 0:
            print(f"WARN: seed={seed} exit={proc.returncode}", flush=True)

    subprocess.run(
        [str(py), str(ROOT / "scripts" / "summarize_single_agent_matched_v1.py")],
        cwd=str(ROOT),
        check=False,
    )


if __name__ == "__main__":
    main()
