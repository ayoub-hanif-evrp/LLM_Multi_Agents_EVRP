"""Summarize P1.3 Experiment A (cross-model repair) for repair01."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.build.p1_minimal import _code_hash

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"

PROFILES = [
    ("qwen25_coder_7b", "qwen2.5-coder:7b"),
    ("deepseek_coder_67b", "deepseek-coder:6.7b"),
    ("codellama_7b", "codellama:7b"),
]


def main() -> None:
    rows = []
    for pid, label in PROFILES:
        path = RAW / f"discovery_p1_3_{pid}_repair01.json"
        j = json.loads(path.read_text(encoding="utf-8"))
        prov = j.get("provenance") or []
        log = j.get("agent_log") or []
        non_noop = [
            x
            for x in prov
            if not x.get("noop") and x.get("hash") and x.get("hash") != x.get("parent_hash")
        ]
        winning = None
        if j.get("G4_PASS"):
            for x in reversed(prov):
                after = x.get("panel_after") or {}
                if after and all(v == "OK" for v in after.values()):
                    winning = f"{x.get('agent')}/{x.get('change_kind')}"
                    break
        baseline = next((x for x in log if x.get("kind") == "best_baseline"), None)
        best = j.get("best_path") or j.get("solver_path")
        final_hash = None
        if best and Path(best).exists():
            final_hash = _code_hash(Path(best).read_text(encoding="utf-8"))[:16]
        rows.append(
            {
                "model": j.get("model") or label,
                "profile": pid,
                "initial_score": (baseline or {}).get("score") or "3/4",
                "final_best_score": j.get("G4_progress"),
                "success_4of4": bool(j.get("G4_PASS")),
                "llm_calls": j.get("llm_calls"),
                "prompt_tokens": j.get("prompt_tokens"),
                "completion_tokens": j.get("completion_tokens"),
                "distinct_non_noop_patches": len({x.get("hash") for x in non_noop}),
                "architect_called": any(x.get("kind") == "architect_escalation" for x in log),
                "regressions_generated": sum(
                    1 for x in log if x.get("kind") == "regression_transaction"
                ),
                "winning_agent": winning,
                "final_solver_hash": final_hash,
                "stopped_reason": j.get("stopped_reason"),
            }
        )

    c5_path = RAW / "p1_3_first_4of4_all_c5.json"
    c5 = json.loads(c5_path.read_text(encoding="utf-8")) if c5_path.exists() else {}

    out_json = RAW / "p1_3_cross_model_repair01_summary.json"
    out_json.write_text(
        json.dumps({"experiment": "cross_model_repair_common_seed", "run_id": "repair01", "rows": rows, "all_c5": c5}, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# P1.3 Experiment A — Cross-model repair (common 3/4 seed)",
        "",
        "**Not** end-to-end synthesis. Same Qwen seed, same P1.3 protocol, `run_id=repair01`.",
        "",
        "| Model | Initial | Final best | 4/4 | Calls | Prompt tok | Compl. tok | Non-NO_OP patches | Architect | Regressions | Winning agent | Final hash |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| `{r['model']}` | {r['initial_score']} | {r['final_best_score']} | "
            f"{'✅' if r['success_4of4'] else '❌'} | {r['llm_calls']} | {r['prompt_tokens']} | "
            f"{r['completion_tokens']} | {r['distinct_non_noop_patches']} | "
            f"{'yes' if r['architect_called'] else 'no'} | {r['regressions_generated']} | "
            f"{r['winning_agent'] or '—'} | `{r['final_solver_hash']}` |"
        )
    lines.extend(
        [
            "",
            "## First 4/4 freeze",
            "",
            f"- Artifact: `results/md/artifacts/p1_3/P1_3_FIRST_4OF4_SOLVER/solver.py`",
            f"- Source: DeepSeek-Coder 6.7B / repair01",
            f"- Hash: `{c5.get('hash')}`",
            "",
            "## Unchanged evaluation on all Schneider C5 (12 instances)",
            "",
            f"**{c5.get('feasible')}/{c5.get('total')} feasible**",
            "",
        ]
    )
    for iid, st in (c5.get("by_instance") or {}).items():
        lines.append(f"- `{iid}`: {st}")
    lines.extend(
        [
            "",
            "## Classification",
            "",
            "P1.3 is **guided trace-based repair** (Critic still mentions pre-service waiting generically).",
            "This screening does **not** claim empty-workspace autonomous discovery.",
            "",
        ]
    )
    md = ROOT / "results" / "md" / "P1_3_CROSS_MODEL_REPAIR01.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    print(f"wrote {md}")
    print(f"wrote {out_json}")
    print(f"ALL_C5 {c5.get('feasible')}/{c5.get('total')}")


if __name__ == "__main__":
    main()
