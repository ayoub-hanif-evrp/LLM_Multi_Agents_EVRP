"""Build the paper tables from this repository's experiment JSON only."""
from __future__ import annotations

import csv
import json
from collections import Counter
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "results" / "paper"


def _rows(folder: str) -> list[dict]:
    directory = PAPER / folder
    if not directory.exists():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        row["_file"] = path.name
        rows.append(row)
    return rows


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _rate(rows: list[dict], key: str) -> str:
    if not rows:
        return "0/0"
    return f"{sum(1 for row in rows if row.get(key))}/{len(rows)}"


def _depth(row: dict) -> int:
    score = 0
    for key in ("executable", "routing", "charging", "multi_customer", "schneider_c5"):
        if row.get(key):
            score += 1
        else:
            break
    return score


def _sign_test(wins: int, losses: int) -> float | None:
    n = wins + losses
    if n == 0:
        return None
    tail = min(wins, losses)
    one_side = sum(comb(n, index) for index in range(tail + 1))
    return min(1.0, 2.0 * one_side / (2**n))


def _category(row: dict) -> str:
    stored = str(row.get("failure_category") or "").upper()
    allowed = {
        "SUCCESS",
        "SYNTAX",
        "RUNTIME",
        "TIMEOUT",
        "DEPOT",
        "VISIT",
        "CAPACITY",
        "WINDOW",
        "BATTERY",
        "CHARGE_POLICY",
        "GENERALITY",
        "BUDGET",
    }
    if stored in allowed:
        return stored
    if row.get("schneider_c5") or row.get("improved"):
        return "SUCCESS"
    return "RUNTIME"


def _scale_section() -> str:
    directory = PAPER / "evaluation"
    if not directory.exists():
        return "Held-out evaluation has not been run."
    status_path = directory / "status.json"
    lines = []
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("synthesis_status"):
            lines.append(status["synthesis_status"] + ".")
        if status.get("evolution_status"):
            lines.append(status["evolution_status"] + ".")
    rows: list[list[object]] = []
    for label, filename in (("synthesized", "synthesized.json"), ("evolved", "evolved.json")):
        path = directory / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        sets = payload.get("sets") or {}
        for name in (
            "c5_development",
            "c5_confirmation",
            "c5_heldout_rc2",
            "c10",
            "c15",
            "larger",
        ):
            metrics = sets.get(name) or {}
            rows.append(
                [
                    label,
                    name,
                    f"{metrics.get('feasible', 0)}/{metrics.get('total', 0)}",
                    metrics.get("vehicles_sum"),
                    metrics.get("distance_sum"),
                    metrics.get("primary_fault") or "",
                ]
            )
    if not rows:
        lines.append("No frozen solver was evaluated. Held-out instances were not used to adapt any solver.")
        return "\n".join(lines)
    lines.append(
        _md_table(
            ["Solver", "Slice", "Feasible", "Vehicles", "Distance", "Primary fault"],
            rows,
        )
    )
    lines.append("These numbers were measured after prompts and solvers were frozen. They were not fed back into synthesis or evolution.")
    return "\n".join(lines)


def _md_table(headers: list[str], body: list[list[object]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def main() -> None:
    synthesis = [row for row in _rows("synthesis") if row.get("experiment") == "five_agent_synthesis"]
    single = [row for row in _rows("single_agent") if row.get("experiment") == "single_agent_synthesis"]
    evolution_all = [row for row in _rows("evolution") if row.get("experiment") == "solver_evolution"]
    evolution = [row for row in evolution_all if row.get("seed") is not None]
    blocked = [row for row in evolution_all if row.get("seed") is None]
    fields = [
        "experiment",
        "model",
        "profile",
        "seed",
        "executable",
        "routing",
        "charging",
        "multi_customer",
        "schneider_c5",
        "fully_feasible",
        "feasible",
        "c5_total",
        "vehicles",
        "distance",
        "llm_calls",
        "tokens",
        "prompt_tokens",
        "completion_tokens",
        "solver_hash",
        "wall_s",
        "failure_reason",
        "published_solver",
        "improved",
    ]
    tables = PAPER / "tables"
    _write_csv(tables / "five_agent_runs.csv", synthesis, fields)
    _write_csv(tables / "single_agent_runs.csv", single, fields)
    _write_csv(tables / "evolution_runs.csv", evolution, fields)

    by_model: dict[str, list[dict]] = {}
    for row in synthesis:
        by_model.setdefault(str(row.get("model")), []).append(row)
    comparison = []
    for model, rows in by_model.items():
        comparison.append(
            [
                model,
                len(rows),
                _rate(rows, "executable"),
                _rate(rows, "routing"),
                _rate(rows, "charging"),
                _rate(rows, "multi_customer"),
                _rate(rows, "schneider_c5"),
                _rate(rows, "fully_feasible"),
                sum(int(row.get("llm_calls") or 0) for row in rows),
                sum(int(row.get("tokens") or 0) for row in rows),
            ]
        )
    qwen7 = [row for row in synthesis if "7b" in str(row.get("model")) and "qwen" in str(row.get("model"))]
    qwen14 = [row for row in synthesis if "14b" in str(row.get("model"))]
    single7 = single
    failures = Counter(_category(row) for row in synthesis + single + evolution)
    by_seed_five = {int(row["seed"]): row for row in qwen7 if row.get("seed") is not None}
    by_seed_single = {int(row["seed"]): row for row in single7 if row.get("seed") is not None}
    paired_seeds = sorted(set(by_seed_five) & set(by_seed_single))
    stage_wins = stage_ties = stage_losses = 0
    g4_wins = g4_ties = g4_losses = 0
    for seed in paired_seeds:
        five_depth = _depth(by_seed_five[seed])
        one_depth = _depth(by_seed_single[seed])
        if five_depth > one_depth:
            stage_wins += 1
        elif five_depth < one_depth:
            stage_losses += 1
        else:
            stage_ties += 1
        five_g4 = int(by_seed_five[seed].get("g4_feasible") or 0)
        one_g4 = int(by_seed_single[seed].get("g4_feasible") or 0)
        if five_g4 > one_g4:
            g4_wins += 1
        elif five_g4 < one_g4:
            g4_losses += 1
        else:
            g4_ties += 1
    stage_p = _sign_test(stage_wins, stage_losses)
    if stage_p is None:
        paired_claim = "No paired seeds were available."
    elif stage_p < 0.05 and stage_wins != stage_losses:
        direction = "five-agent" if stage_wins > stage_losses else "single-agent"
        paired_claim = (
            f"On non-tied seeds the exact two-sided sign test gives p={stage_p:.4f} "
            f"in favor of the {direction} stage depth."
        )
    else:
        shown = "n/a" if stage_p is None else f"{stage_p:.4f}"
        paired_claim = (
            f"Exact two-sided sign test on non-tied stage depths: p={shown}. "
            "This comparison does not establish that one architecture is superior."
        )
    evolved = [row for row in evolution if row.get("improved") and row.get("fully_feasible")]
    best = None
    pool = [row for row in synthesis + single + evolution if row.get("fully_feasible") and row.get("vehicles") is not None]
    if pool:
        best = sorted(pool, key=lambda row: (int(row["vehicles"]), float(row["distance"] or 1e18)))[0]

    parts = [
        "# Paper results",
        "",
        "These tables contain only the runs produced by `scripts/run_five_agent.py`, `scripts/run_single_agent.py`, and `scripts/run_evolution.py` in this repository. Historical development runs are not included.",
        "",
        "## 1. Five-agent synthesis by model",
        "",
        _md_table(
            ["Model", "Seeds", "Executable", "Routing", "Charging", "Multi-customer", "Schneider C5 panel", "Non-held-out C5", "LLM calls", "Tokens"],
            comparison or [["—", 0, "0/0", "0/0", "0/0", "0/0", "0/0", "0/0", 0, 0]],
        ),
        "",
        "## 2. Five-agent Qwen 7B vs single-agent Qwen 7B",
        "",
        _md_table(
            ["System", "Seeds", "Executable", "Routing", "Charging", "Multi-customer", "Schneider C5 panel", "Non-held-out C5", "Tokens"],
            [
                ["five-agent Qwen 7B", len(qwen7), _rate(qwen7, "executable"), _rate(qwen7, "routing"), _rate(qwen7, "charging"), _rate(qwen7, "multi_customer"), _rate(qwen7, "schneider_c5"), _rate(qwen7, "fully_feasible"), sum(int(r.get("tokens") or 0) for r in qwen7)],
                ["single-agent Qwen 7B", len(single7), _rate(single7, "executable"), _rate(single7, "routing"), _rate(single7, "charging"), _rate(single7, "multi_customer"), _rate(single7, "schneider_c5"), _rate(single7, "fully_feasible"), sum(int(r.get("tokens") or 0) for r in single7)],
            ],
        ),
        "",
        f"Paired seeds: {len(paired_seeds)}. Stage-depth wins/ties/losses (five-agent vs single-agent): {stage_wins}/{stage_ties}/{stage_losses}.",
        f"G4-feasible-count wins/ties/losses: {g4_wins}/{g4_ties}/{g4_losses}.",
        paired_claim,
        "",
        "Single-agent token ceilings are the paired five-agent token totals. Call-boundary overshoot is recorded on each single-agent row as `token_overshoot`.",
        "",
        "## 3. Qwen 7B vs Qwen 14B (five-agent)",
        "",
        _md_table(
            ["Model", "Seeds", "Schneider C5 panel", "Non-held-out C5", "LLM calls", "Tokens"],
            [
                ["Qwen 7B", len(qwen7), _rate(qwen7, "schneider_c5"), _rate(qwen7, "fully_feasible"), sum(int(r.get("llm_calls") or 0) for r in qwen7), sum(int(r.get("tokens") or 0) for r in qwen7)],
                ["Qwen 14B", len(qwen14), _rate(qwen14, "schneider_c5"), _rate(qwen14, "fully_feasible"), sum(int(r.get("llm_calls") or 0) for r in qwen14), sum(int(r.get("tokens") or 0) for r in qwen14)],
            ],
        ),
        "",
        "## 4. Solver evolution",
        "",
        _md_table(
            ["Seed", "Improved", "Non-held-out C5", "Vehicles", "Distance", "Calls", "Hash", "Runtime s"],
            [
                [
                    row.get("seed"),
                    row.get("improved"),
                    f"{row.get('feasible')}/{row.get('c5_total')}",
                    row.get("vehicles"),
                    row.get("distance"),
                    row.get("llm_calls"),
                    row.get("solver_hash"),
                    row.get("wall_s"),
                ]
                for row in evolution
            ]
            or [["—", "—", "—", "—", "—", "—", "—", "—"]],
        ),
        "",
        f"Valid improvements kept: {len(evolved)}.",
        "",
        *[
            f"Evolution did not start: {row.get('failure_reason')}."
            for row in blocked
        ],
        "",
        "## 5. Final held-out and scale evaluation",
        "",
        _scale_section(),
        "",
        "## 6. Failure categories",
        "",
        _md_table(
            ["Category", "Count"],
            [[name, failures.get(name, 0)] for name in (
                "SUCCESS", "SYNTAX", "RUNTIME", "TIMEOUT", "DEPOT", "VISIT", "CAPACITY",
                "WINDOW", "BATTERY", "CHARGE_POLICY", "GENERALITY", "BUDGET",
            )],
        ),
        "",
        "## Best valid generated solver",
        "",
    ]
    if best is None:
        parts.append(
            "No run produced a solver that is fully feasible on every non-held-out 5-customer instance."
        )
    else:
        parts.append(
            f"- Experiment: `{best.get('experiment')}`\n"
            f"- Model: `{best.get('model')}` seed `{best.get('seed')}`\n"
            f"- Vehicles: `{best.get('vehicles')}` distance `{best.get('distance')}`\n"
            f"- Hash: `{best.get('solver_hash')}`\n"
            f"- File: `{best.get('published_solver')}`"
        )
    parts.append("")
    text = "\n".join(parts)
    (PAPER / "README.md").write_text(text, encoding="utf-8")
    print(f"wrote {PAPER / 'README.md'}")


if __name__ == "__main__":
    main()
