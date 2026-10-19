"""Figures from measured JSON. This script does not solve or call a model."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[3]
PAPER = ROOT / "results" / "v2" / "paper"
PILOT = ROOT / "results" / "v2" / "campaigns" / "matched_qwen_20261018T205937Z"


def _hiermann_c101() -> None:
    pilot = json.loads((PILOT / "matched_pilot.json").read_text(encoding="utf-8"))
    confirm = json.loads((PILOT / "confirmation_seeds.json").read_text(encoding="utf-8"))
    values = {7: {}, 11: {}, 22: {}}
    for row in pilot["rows"]:
        if row["instance_id"] != "c101_21":
            continue
        if row["arm"] == "classical":
            values[7]["classical"] = row["objective_key"][0]
        elif row["candidate_id"] in {"random_0", "five_1"}:
            values[7][row["candidate_id"]] = row["objective_key"][0]
    for row in confirm["rows"]:
        if row["instance_id"] != "c101_21":
            continue
        values[int(row["seed"])]["classical"] = row["baseline_key"][0]
        values[int(row["seed"])][row["candidate_id"]] = row["objective_key"][0]
    seeds = [7, 11, 22]
    series = [
        ("classical", "Classical"),
        ("random_0", "Random grammar"),
        ("five_1", "Five-agent"),
    ]
    width = 0.25
    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    for index, (key, label) in enumerate(series):
        ys = [values[seed][key] for seed in seeds]
        axis.bar([s + (index - 1) * width for s in range(len(seeds))], ys, width=width, label=label)
    axis.set_xticks(range(len(seeds)), [str(seed) for seed in seeds])
    axis.set_xlabel("Deployment seed")
    axis.set_ylabel("Hiermann c101_21 total cost")
    axis.legend()
    figure.tight_layout()
    figure.savefig(PAPER / "hiermann_c101_21_cost.png", dpi=160)
    plt.close(figure)


def _family_feasibility() -> None:
    panel = json.loads(
        (ROOT / "results" / "v2" / "diagnostics" / "family_development_gate" / "expanded_panel.json").read_text(
            encoding="utf-8"
        )
    )
    counts: dict[str, list[int]] = {}
    for row in panel["independent_rows"]:
        bucket = counts.setdefault(row["family"], [0, 0])
        bucket[1] += 1
        bucket[0] += int(bool(row["feasible"]))
    names = sorted(counts)
    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    axis.bar(names, [counts[name][0] for name in names], label="Feasible")
    axis.bar(
        names,
        [counts[name][1] - counts[name][0] for name in names],
        bottom=[counts[name][0] for name in names],
        label="Infeasible",
    )
    axis.set_ylabel("Independent instance-seed rows")
    axis.legend()
    figure.tight_layout()
    figure.savefig(PAPER / "development_feasibility.png", dpi=160)
    plt.close(figure)


def main() -> None:
    PAPER.mkdir(parents=True, exist_ok=True)
    _hiermann_c101()
    _family_feasibility()
    print("wrote figures")


if __name__ == "__main__":
    main()
