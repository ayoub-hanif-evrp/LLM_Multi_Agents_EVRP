"""Summarize MCB V1 strong-model anchor (seeds 11/22/33/44/55) vs frozen ~7B table.

Does not change MCB V1. Reads existing seeded JSON artifacts only.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"
SEEDS = (11, 22, 33, 44, 55)

# Anchor under test + the three ~7B baselines for side-by-side reporting.
PROFILES = (
    ("deepseek_coder_v2_lite", "deepseek-coder-v2:16b"),
    ("qwen25_coder_7b", "qwen2.5-coder:7b"),
    ("deepseek_coder_67b", "deepseek-coder:6.7b"),
    ("codellama_7b", "codellama:7b"),
)


def _gate_pass(j: dict, name: str) -> bool:
    g = (j.get("gates") or {}).get(name) or {}
    return bool(g.get("passed"))


def _reached_real_g4(j: dict) -> bool:
    """Entered the Schneider G4 panel (cleared G3), even if 0/4 or partial."""
    if _gate_pass(j, "G3") or _gate_pass(j, "G4"):
        return True
    progress = str(j.get("G4_progress") or j.get("g4_progress") or "")
    try:
        ok = int(progress.split("/")[0])
    except (ValueError, IndexError):
        ok = 0
    if ok >= 1:
        return True
    stopped = str(j.get("stopped_reason") or "")
    return stopped.startswith("PARTIAL_G4_") or stopped.startswith("G4_")


def _main_failure(rows: list[dict]) -> str:
    mains: dict[str, int] = {}
    for r in rows:
        pf = r.get("primary") or {}
        stopped = str(r.get("stopped") or "")
        fc = str(pf.get("failure_class") or "")
        detail = str(pf.get("detail") or "")
        if fc == "RUNTIME":
            short = "RUNTIME"
            for marker in ("NameError", "AttributeError", "TypeError", "timeout", "KeyError", "IndexError"):
                if marker.lower() in detail.lower() or marker.lower() in stopped.lower():
                    short = f"RUNTIME/{marker}"
                    break
            key = short
        elif fc == "GENERALITY":
            key = "GENERALITY/hardcoded_id"
        elif fc == "FEASIBILITY":
            key = f"FEASIBILITY/{detail.split()[0] if detail else 'fail'}"
        elif fc == "FORMAT":
            key = "FORMAT"
        else:
            key = fc or stopped or "none"
        mains[key] = mains.get(key, 0) + 1
    return max(mains.items(), key=lambda x: x[1])[0] if mains else "—"


def main() -> None:
    by_model: dict[str, list[dict]] = {}
    missing: list[str] = []
    for pid, label in PROFILES:
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
                    "llm_seed": j.get("llm_seed"),
                    "seed_provided": j.get("seed_provided"),
                    "G0": _gate_pass(j, "G0"),
                    "G1": _gate_pass(j, "G1"),
                    "G2": _gate_pass(j, "G2"),
                    "G3": _gate_pass(j, "G3"),
                    "G4": _gate_pass(j, "G4"),
                    "reached_real_g4": _reached_real_g4(j),
                    "g4_progress": j.get("G4_progress") or j.get("g4_progress"),
                    "calls": j.get("llm_calls"),
                    "stopped": j.get("stopped_reason"),
                    "primary": j.get("primary_failure"),
                }
            )
        by_model[label] = rows

    summary_rows = []
    for label, rows in by_model.items():
        def rate(pred) -> str:
            return f"{sum(1 for r in rows if pred(r))}/{len(rows)}" if rows else "0/0"

        calls = [int(r["calls"] or 0) for r in rows]
        summary_rows.append(
            {
                "model": label,
                "n": len(rows),
                "G1_success": rate(lambda r: r["G1"]),
                "G2_success": rate(lambda r: r["G2"]),
                "G3_success": rate(lambda r: r["G3"]),
                "G4_success": rate(lambda r: r["G4"]),
                "reached_real_g4": rate(lambda r: r["reached_real_g4"]),
                "median_calls": statistics.median(calls) if calls else None,
                "main_failure": _main_failure(rows),
                "runs": rows,
            }
        )

    out = {
        "protocol": "MINIMAL_COOPERATIVE_BUILD_V1",
        "experiment": "strong_model_anchor_seeded",
        "anchor_profile": "deepseek_coder_v2_lite",
        "anchor_note": (
            "Qwen3-Coder-30B-A3B preferred but deferred on RTX A2000 12GB + ~16GB RAM; "
            "DeepSeek-Coder-V2-Lite (16B MoE / ~2.4B active) used as strong anchor."
        ),
        "seeds": list(SEEDS),
        "missing": missing,
        "summary": summary_rows,
    }
    dest = RAW / "mcb_v1_strong_anchor_summary.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")

    lines = [
        "# MCB V1 — Strong-model anchor (seeded)",
        "",
        "MCB V1 **frozen**. Same seeds `11/22/33/44/55` as the ~7B package.",
        "",
        "**Hardware note:** Preferred anchor `qwen3-coder:30b` (~19GB Q4) deferred on this machine",
        "(RTX A2000 12GB + ~16GB system RAM). Running **`deepseek-coder-v2:16b`**",
        "(DeepSeek-Coder-V2-Lite-Instruct, ~8.9GB, MoE ~2.4B active) instead.",
        "",
        "| Model | n | G1 | G2 | G3 | G4 4/4 | Reached real G4 | Median calls | Main failure |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in summary_rows:
        lines.append(
            f"| `{r['model']}` | {r['n']} | {r['G1_success']} | {r['G2_success']} | "
            f"{r['G3_success']} | {r['G4_success']} | {r['reached_real_g4']} | "
            f"{r['median_calls']} | {r['main_failure']} |"
        )
    if missing:
        lines.extend(["", "## Missing runs", ""])
        for m in missing:
            lines.append(f"- `{m}`")

    lines.extend(["", "## Per-seed detail (strong anchor)", ""])
    anchor = next((r for r in summary_rows if r["model"] == "deepseek-coder-v2:16b"), None)
    if anchor:
        for run in anchor["runs"]:
            pf = run.get("primary") or {}
            fc = pf.get("failure_class") or ""
            detail = str(pf.get("detail") or "")
            if fc == "RUNTIME":
                det = "timeout" if "timeout" in detail.lower() else detail.split("\n")[0][:80]
            else:
                det = detail[:80]
            lines.append(
                f"- seed `{run['seed']}`: G1={run['G1']} G2={run['G2']} G3={run['G3']} "
                f"G4={run['G4']} g4_progress={run.get('g4_progress')} "
                f"calls={run['calls']} stopped={run['stopped']} primary={fc}/{det}"
            )
    else:
        lines.append("_No strong-anchor runs yet._")

    md = ROOT / "results" / "md" / "MCB_V1_STRONG_ANCHOR.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"missing": missing, "summary": [
        {k: r[k] for k in (
            "model", "n", "G1_success", "G2_success", "G3_success",
            "G4_success", "reached_real_g4", "median_calls", "main_failure",
        )}
        for r in summary_rows
    ]}, indent=2))
    print(f"wrote {md}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
