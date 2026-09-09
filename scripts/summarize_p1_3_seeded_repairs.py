"""Summarize seeded P1.3 repair repeats."""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"
SEEDS = (11, 22, 33, 44, 55)
PROFILES = (
    ("qwen25_coder_7b", "qwen2.5-coder:7b", "Qwen 7B"),
    ("deepseek_coder_67b", "deepseek-coder:6.7b", "DeepSeek 6.7B"),
    ("codellama_7b", "codellama:7b", "CodeLlama 7B"),
)


def main() -> None:
    missing = []
    summary_rows = []
    detail = {}
    for pid, model, label in PROFILES:
        rows = []
        for seed in SEEDS:
            path = RAW / f"discovery_p1_3_{pid}_repair_seed{seed}.json"
            if not path.exists():
                missing.append(f"{pid}/repair_seed{seed}")
                continue
            j = json.loads(path.read_text(encoding="utf-8"))
            agent_log = j.get("agent_log") or []
            regressions = sum(1 for x in agent_log if x.get("kind") == "regression_transaction")
            noops = sum(1 for x in agent_log if x.get("kind") == "noop" or x.get("noop"))
            provenance = j.get("provenance") or []
            noops += sum(1 for p in provenance if p.get("noop"))
            success = bool(j.get("G4_PASS"))
            c5 = j.get("c5_generalization") or {}
            rows.append(
                {
                    "seed": seed,
                    "success_4of4": success,
                    "g4": j.get("G4_progress"),
                    "calls": j.get("llm_calls"),
                    "prompt_tokens": j.get("prompt_tokens"),
                    "completion_tokens": j.get("completion_tokens"),
                    "regressions": regressions,
                    "noop": noops,
                    "stopped": j.get("stopped_reason"),
                    "c5_feasible": c5.get("feasible"),
                    "c5_total": c5.get("total"),
                    "hash": (j.get("summary") or {}).get("final_solver_hash"),
                }
            )
        n = len(rows)
        successes = [r for r in rows if r["success_4of4"]]
        calls_ok = [int(r["calls"] or 0) for r in successes]
        summary_rows.append(
            {
                "label": label,
                "model": model,
                "profile": pid,
                "n": n,
                "successes_4of4": len(successes),
                "success_rate": f"{len(successes)}/{n}" if n else "0/0",
                "median_calls_to_success": statistics.median(calls_ok) if calls_ok else None,
                "regressions_total": sum(int(r["regressions"] or 0) for r in rows),
                "noop_rate": (
                    f"{sum(1 for r in rows if int(r['noop'] or 0) > 0)}/{n}" if n else "0/0"
                ),
                "c5_on_success": [
                    f"{r['c5_feasible']}/{r['c5_total']}" for r in successes if r.get("c5_total")
                ],
                "runs": rows,
            }
        )
        detail[label] = rows

    out = {
        "protocol": "P1.3_REGRESSION_SAFE",
        "experiment": "seeded_repair_repeats",
        "seeds": list(SEEDS),
        "missing": missing,
        "summary": summary_rows,
    }
    (RAW / "p1_3_seeded_repair_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    csv_path = ROOT / "results" / "md" / "tables" / "FINAL_REPAIR_SEEDED.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(
            [
                "model",
                "n",
                "4of4_successes",
                "success_rate",
                "median_calls_to_success",
                "regressions_total",
                "noop_rate",
            ]
        )
        for r in summary_rows:
            w.writerow(
                [
                    r["label"],
                    r["n"],
                    r["successes_4of4"],
                    r["success_rate"],
                    r["median_calls_to_success"],
                    r["regressions_total"],
                    r["noop_rate"],
                ]
            )

    lines = [
        "# Seeded P1.3 repair repeats",
        "",
        "Frozen P1.3 protocol. Common 3/4 seed. Seeds `11/22/33/44/55`.",
        "",
        "| Model | n | 4/4 successes | Success rate | Median calls to success | Regressions | NO_OP rate |",
        "| --- | -: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary_rows:
        lines.append(
            f"| {r['label']} | {r['n']} | {r['successes_4of4']} | {r['success_rate']} | "
            f"{r['median_calls_to_success']} | {r['regressions_total']} | {r['noop_rate']} |"
        )
    lines.extend(["", "## Per-seed", ""])
    for r in summary_rows:
        lines.append(f"### {r['label']}")
        lines.append("")
        for run in r["runs"]:
            lines.append(
                f"- seed `{run['seed']}`: 4/4={run['success_4of4']} g4={run['g4']} "
                f"calls={run['calls']} stopped={run['stopped']} "
                f"c5={run['c5_feasible']}/{run['c5_total']} regressions={run['regressions']}"
            )
        lines.append("")
    if missing:
        lines.extend(["## Missing", ""] + [f"- `{m}`" for m in missing])
    md = ROOT / "results" / "md" / "P1_3_SEEDED_REPAIRS.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"missing": missing, "summary": [
        {k: r[k] for k in (
            "label", "n", "successes_4of4", "success_rate",
            "median_calls_to_success", "regressions_total", "noop_rate", "c5_on_success",
        )}
        for r in summary_rows
    ]}, indent=2))
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
