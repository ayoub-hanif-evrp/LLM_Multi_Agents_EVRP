"""Summarize Qwen2.5-Coder 14B MCB V1 seeds vs same-family 7B."""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"
SEEDS = (11, 22, 33, 44, 55)
PAIRS = (
    ("qwen25_coder_14b", "qwen2.5-coder:14b"),
    ("qwen25_coder_7b", "qwen2.5-coder:7b"),
)


def _gate(j: dict, name: str) -> bool:
    return bool((j.get("gates") or {}).get(name, {}).get("passed"))


def _g4(j: dict) -> int:
    try:
        return int(str(j.get("G4_progress") or "0/4").split("/")[0])
    except (ValueError, IndexError):
        return 0


def _reached(j: dict) -> bool:
    return _gate(j, "G3") or _g4(j) >= 1


def main() -> None:
    missing = []
    summary = []
    for pid, label in PAIRS:
        rows = []
        for seed in SEEDS:
            path = RAW / f"discovery_mcb_v1_{pid}_seed{seed}.json"
            if not path.exists():
                missing.append(f"{pid}/seed{seed}")
                continue
            j = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "seed": seed,
                    "G0": _gate(j, "G0"),
                    "G1": _gate(j, "G1"),
                    "G2": _gate(j, "G2"),
                    "G3": _gate(j, "G3"),
                    "G4": _gate(j, "G4"),
                    "reached_g4": _reached(j),
                    "g4_count": _g4(j),
                    "g4_progress": j.get("G4_progress"),
                    "calls": j.get("llm_calls"),
                    "stopped": j.get("stopped_reason"),
                    "primary": j.get("primary_failure"),
                    "solver_path": j.get("solver_path"),
                    "all_c5": j.get("all_c5_unchanged"),
                }
            )
        n = len(rows) or 1

        def rate(pred):
            return f"{sum(1 for r in rows if pred(r))}/{len(rows)}" if rows else "0/0"

        summary.append(
            {
                "model": label,
                "profile": pid,
                "n": len(rows),
                "G1": rate(lambda r: r["G1"]),
                "G2": rate(lambda r: r["G2"]),
                "G3": rate(lambda r: r["G3"]),
                "reached_g4": rate(lambda r: r["reached_g4"]),
                "G4_4of4": rate(lambda r: r["G4"]),
                "mean_g4": round(statistics.mean(r["g4_count"] for r in rows), 2) if rows else None,
                "median_calls": statistics.median(int(r["calls"] or 0) for r in rows) if rows else None,
                "runs": rows,
            }
        )

    out = {
        "protocol": "MINIMAL_COOPERATIVE_BUILD_V1",
        "experiment": "same_family_capacity_anchor_qwen14b",
        "seeds": list(SEEDS),
        "missing": missing,
        "summary": summary,
    }
    (RAW / "mcb_v1_qwen14b_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    csv_path = ROOT / "results" / "md" / "tables" / "MCB_V1_QWEN14B.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["model", "n", "G1", "G2", "G3", "reached_G4", "G4_4of4", "mean_g4", "median_calls"])
        for r in summary:
            w.writerow(
                [r["model"], r["n"], r["G1"], r["G2"], r["G3"], r["reached_g4"], r["G4_4of4"], r["mean_g4"], r["median_calls"]]
            )

    lines = [
        "# MCB V1 — Qwen2.5-Coder 14B same-family capacity anchor",
        "",
        "Frozen MCB V1. Seeds `11/22/33/44/55`. Compares `qwen2.5-coder:14b` vs `7b`.",
        "",
        "| Model | n | G1 | G2 | G3 | reached G4 | G4 4/4 | mean G4 | median calls |",
        "| --- | -: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in summary:
        lines.append(
            f"| `{r['model']}` | {r['n']} | {r['G1']} | {r['G2']} | {r['G3']} | "
            f"{r['reached_g4']} | {r['G4_4of4']} | {r['mean_g4']} | {r['median_calls']} |"
        )
    lines.extend(["", "## Per-seed (14B)", ""])
    for r in summary:
        if r["profile"] != "qwen25_coder_14b":
            continue
        for run in r["runs"]:
            pf = run.get("primary") or {}
            lines.append(
                f"- seed `{run['seed']}`: G1={run['G1']} G2={run['G2']} G3={run['G3']} "
                f"G4={run['G4']} progress={run['g4_progress']} calls={run['calls']} "
                f"stopped={run['stopped']} primary={pf.get('failure_class')}/{str(pf.get('detail') or '')[:60]}"
            )
    if missing:
        lines.extend(["", "## Missing", ""] + [f"- `{m}`" for m in missing])
    md = ROOT / "results" / "md" / "MCB_V1_QWEN14B_ANCHOR.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"missing": missing, "summary": [
        {k: r[k] for k in ("model", "n", "G1", "G2", "G3", "reached_g4", "G4_4of4", "mean_g4", "median_calls")}
        for r in summary
    ]}, indent=2))
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
