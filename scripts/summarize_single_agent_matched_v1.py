"""Summarize SINGLE_AGENT_MATCHED_V1 vs Qwen MCB V1 (paired token ceilings).

Budget semantics: paired token-ceiling baseline with call-boundary overshoot.
The last in-flight LLM call may finish after the ceiling is crossed; report actual tokens.
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "results" / "md" / "tables" / "raw_autolab"
SEEDS = (11, 22, 33, 44, 55)
PROFILE = "qwen25_coder_7b"
TOKEN_BUDGETS = {11: 18179, 22: 39157, 33: 23579, 44: 6205, 55: 18207}
# Prefer prompt-parity re-runs when present; fall back to original soft-budget runs.
SA_RUN_PREFIXES = ("single_qwen_parity_seed", "single_qwen_seed")


def _gate(j: dict, name: str) -> bool:
    return bool((j.get("gates") or {}).get(name, {}).get("passed"))


def _g4_count(j: dict) -> int:
    prog = str(j.get("G4_progress") or "0/4")
    try:
        return int(prog.split("/")[0])
    except (ValueError, IndexError):
        return 0


def _reached_g4(j: dict) -> bool:
    return _gate(j, "G3") or _g4_count(j) >= 1 or str(j.get("stopped_reason") or "").startswith(
        ("PARTIAL_G4_", "G4_", "TOKEN_BUDGET_PARTIAL_G4_")
    )


def _highest(j: dict) -> str:
    if j.get("highest_gate"):
        return str(j["highest_gate"])
    for g in ("G4", "G3", "G2", "G1", "G0"):
        if _gate(j, g):
            return g if g != "G4" or _gate(j, "G4") else f"G4_partial_{_g4_count(j)}"
    return "none"


def _load_mcb(seed: int) -> dict | None:
    path = RAW / f"discovery_mcb_v1_{PROFILE}_seed{seed}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _load_sa(seed: int) -> tuple[dict | None, str]:
    for prefix in SA_RUN_PREFIXES:
        path = RAW / f"discovery_single_agent_v1_{PROFILE}_{prefix}{seed}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8")), prefix
    return None, ""


def _tokens(j: dict) -> int:
    if j.get("total_tokens") is not None:
        return int(j["total_tokens"])
    return int(j.get("prompt_tokens") or 0) + int(j.get("completion_tokens") or 0)


def _runtime_fail(j: dict) -> bool:
    tax = j.get("taxonomy_counts") or {}
    pf = j.get("primary_failure") or {}
    return int(tax.get("RUNTIME") or 0) > 0 or pf.get("failure_class") == "RUNTIME"


def _feas_fail(j: dict) -> bool:
    tax = j.get("taxonomy_counts") or {}
    pf = j.get("primary_failure") or {}
    return int(tax.get("FEASIBILITY") or 0) > 0 or pf.get("failure_class") == "FEASIBILITY"


def _noop(j: dict) -> int:
    if j.get("noop_count") is not None:
        return int(j["noop_count"])
    tax = j.get("taxonomy_counts") or {}
    return int(tax.get("NO_OP") or 0)


def _agg(rows: list[dict], key_pred) -> str:
    if not rows:
        return "0/0"
    return f"{sum(1 for r in rows if key_pred(r))}/{len(rows)}"


def main() -> None:
    mcb_rows = []
    sa_rows = []
    missing = []
    paired = []
    sa_source = None
    for seed in SEEDS:
        m = _load_mcb(seed)
        s, prefix = _load_sa(seed)
        if m is None:
            missing.append(f"mcb/seed{seed}")
        else:
            mcb_rows.append(m)
        if s is None:
            missing.append(f"sa/seed{seed}")
        else:
            sa_rows.append(s)
            sa_source = prefix
        budget = TOKEN_BUDGETS[seed]
        used = _tokens(s) if s else None
        overshoot = None if used is None else max(0, used - budget)
        paired.append(
            {
                "seed": seed,
                "token_budget": budget,
                "five_highest": _highest(m) if m else "missing",
                "single_highest": _highest(s) if s else "missing",
                "five_tokens": _tokens(m) if m else None,
                "single_tokens": used,
                "single_overshoot": overshoot,
                "five_g4": _g4_count(m) if m else None,
                "single_g4": _g4_count(s) if s else None,
                "five_calls": (m or {}).get("llm_calls"),
                "single_calls": (s or {}).get("llm_calls"),
            }
        )

    def mean_g4(rows: list[dict]) -> float | None:
        if not rows:
            return None
        return round(statistics.mean(_g4_count(r) for r in rows), 2)

    def median_calls(rows: list[dict]) -> float | None:
        vals = [int(r.get("llm_calls") or 0) for r in rows]
        return statistics.median(vals) if vals else None

    def median_tokens(rows: list[dict]) -> float | None:
        vals = [_tokens(r) for r in rows]
        return statistics.median(vals) if vals else None

    def rate(rows: list[dict], pred) -> str:
        if not rows:
            return "0/0"
        return f"{sum(1 for r in rows if pred(r))}/{len(rows)}"

    comparison = {
        "metric": [
            "n",
            "G1 success",
            "G2 success",
            "G3 success",
            "reached G4",
            "G4 4/4",
            "mean G4 feasible count",
            "median calls",
            "median tokens",
            "runtime-failure rate",
            "feasibility-failure rate",
            "NO_OP rate",
        ],
        "five_agent": [
            len(mcb_rows),
            _agg(mcb_rows, lambda r: _gate(r, "G1")),
            _agg(mcb_rows, lambda r: _gate(r, "G2")),
            _agg(mcb_rows, lambda r: _gate(r, "G3")),
            _agg(mcb_rows, _reached_g4),
            _agg(mcb_rows, lambda r: _gate(r, "G4")),
            mean_g4(mcb_rows),
            median_calls(mcb_rows),
            median_tokens(mcb_rows),
            rate(mcb_rows, _runtime_fail),
            rate(mcb_rows, _feas_fail),
            rate(mcb_rows, lambda r: _noop(r) > 0),
        ],
        "single_agent": [
            len(sa_rows),
            _agg(sa_rows, lambda r: _gate(r, "G1")),
            _agg(sa_rows, lambda r: _gate(r, "G2")),
            _agg(sa_rows, lambda r: _gate(r, "G3")),
            _agg(sa_rows, _reached_g4),
            _agg(sa_rows, lambda r: _gate(r, "G4")),
            mean_g4(sa_rows),
            median_calls(sa_rows),
            median_tokens(sa_rows),
            rate(sa_rows, _runtime_fail),
            rate(sa_rows, _feas_fail),
            rate(sa_rows, lambda r: _noop(r) > 0),
        ],
    }

    def score(rows: list[dict]) -> tuple[int, int, float]:
        g3 = sum(1 for r in rows if _gate(r, "G3"))
        g4r = sum(1 for r in rows if _reached_g4(r))
        mg4 = mean_g4(rows) or 0.0
        return g3, g4r, mg4

    five_s, single_s = score(mcb_rows), score(sa_rows)
    if five_s > single_s:
        outcome = "A"
        outcome_text = (
            "Role-specialized cooperation improved panel depth under the tested "
            "local model/budget, without wholesale dominance on curriculum reach rates."
        )
    elif single_s > five_s:
        outcome = "B"
        outcome_text = (
            "The specialized five-agent architecture introduced communication/coordination "
            "overhead and did not outperform simpler self-refinement under matched inference."
        )
    else:
        outcome = "C"
        outcome_text = (
            "Role specialization did not materially improve synthesis success but provides "
            "structured failure attribution and domain-specific interpretability."
        )

    out = {
        "protocol_compare": ["MINIMAL_COOPERATIVE_BUILD_V1", "SINGLE_AGENT_MATCHED_V1"],
        "budget_semantics": "paired_token_ceiling_with_call_boundary_overshoot",
        "prompt_parity": (
            "union_domain_guidance_no_role_decomposition"
            if sa_source and "parity" in sa_source
            else "legacy_or_mixed"
        ),
        "sa_run_prefix": sa_source,
        "model": "qwen2.5-coder:7b",
        "seeds": list(SEEDS),
        "token_budgets": TOKEN_BUDGETS,
        "missing": missing,
        "comparison": comparison,
        "paired": paired,
        "outcome": outcome,
        "outcome_text": outcome_text,
    }
    dest = RAW / "single_agent_matched_v1_summary.json"
    dest.write_text(json.dumps(out, indent=2), encoding="utf-8")

    csv_path = ROOT / "results" / "md" / "tables" / "FINAL_MULTI_AGENT_BASELINE.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["metric", "five_agent_qwen_mcb_v1", "single_agent_qwen"])
        for i, metric in enumerate(comparison["metric"]):
            w.writerow([metric, comparison["five_agent"][i], comparison["single_agent"][i]])

    paired_csv = ROOT / "results" / "md" / "tables" / "FINAL_MULTI_AGENT_BASELINE_PAIRED.csv"
    with paired_csv.open("w", encoding="utf-8", newline="") as handle:
        w = csv.DictWriter(handle, fieldnames=list(paired[0].keys()) if paired else ["seed"])
        w.writeheader()
        w.writerows(paired)

    lines = [
        "# FINAL — Five-agent MCB V1 vs Single-agent matched baseline",
        "",
        "Model: `qwen2.5-coder:7b`. Seeds `11/22/33/44/55`.",
        "",
        "**Budget semantics:** paired token-ceiling baseline with **call-boundary overshoot**.",
        "The final in-flight LLM call may finish after the ceiling; tables report **actual** tokens.",
        "This is soft-ceiling matching, not a hard abort mid-generation.",
        "",
        "**Prompt parity:** single-agent prompt carries the **union** of fixed API/domain guidance",
        "(routing + charging physics + solve contract) without role decomposition.",
        f"Active SA run prefix: `{sa_source or 'missing'}`.",
        "",
        f"**Outcome {outcome}:** {outcome_text}",
        "",
        "| Metric | Five-agent Qwen MCB V1 | Single-agent Qwen |",
        "| --- | ---: | ---: |",
    ]
    for i, metric in enumerate(comparison["metric"]):
        lines.append(
            f"| {metric} | {comparison['five_agent'][i]} | {comparison['single_agent'][i]} |"
        )
    lines.extend(
        [
            "",
            "## Per-seed paired",
            "",
            "| Seed | Five-agent highest | Single-agent highest | Five tokens | Single tokens | Overshoot |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for p in paired:
        lines.append(
            f"| {p['seed']} | {p['five_highest']} | {p['single_highest']} | "
            f"{p['five_tokens']} | {p['single_tokens']} | {p['single_overshoot']} |"
        )
    if missing:
        lines.extend(["", "## Missing", ""] + [f"- `{m}`" for m in missing])
    md = ROOT / "results" / "md" / "FINAL_MULTI_AGENT_BASELINE.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "results" / "md" / "SINGLE_AGENT_MATCHED_V1_SUMMARY.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    print(json.dumps({"missing": missing, "outcome": outcome, "sa_source": sa_source}, indent=2))
    print(f"wrote {md}")


if __name__ == "__main__":
    main()
