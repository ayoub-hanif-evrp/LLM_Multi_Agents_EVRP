"""ChargeCEGIS figure generation: clean, academic-style Matplotlib figures.

    python -m chargecegis.plots --results results/raw/full_dataset_runs.csv

Writes matching PNG and PDF pairs into ``results/figures/``. Uses the non-interactive Agg
backend so it never requires a display, and never runs an ALNS experiment itself: it only reads
CSV/JSON artifacts already produced by ``chargecegis.experiment`` / ``chargecegis.statistics``.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import typer

matplotlib.use("Agg")

from chargecegis.statistics import (  # noqa: E402
    EQUAL_BUDGET_BASELINE,
    EQUAL_BUDGET_RANKING_METHODS,
    FAMILY_ORDER,
    build_equal_budget_large_instance_results,
    dataset_rows,
    family_group,
)

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
DEFAULT_RESULTS_CSV = RESULTS_DIR / "raw" / "full_dataset_runs.csv"
MOVE_INVOCATIONS_CSV = RESULTS_DIR / "raw" / "move_invocations.csv"
FIGURES_DIR = RESULTS_DIR / "figures"

# Clean academic palette (muted blues/oranges/greens) -- deliberately not neon or purple-heavy.
PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B2", "#937860", "#64B5CD"]

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#444444",
    "axes.grid": True,
    "grid.color": "#DDDDDD",
    "grid.linewidth": 0.6,
    "font.size": 10,
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def _save(fig: plt.Figure, stem: str) -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"{stem}.png", dpi=200)
    fig.savefig(FIGURES_DIR / f"{stem}.pdf")
    plt.close(fig)


def _order_families(values: list[str]) -> list[str]:
    present = [f for f in FAMILY_ORDER if f in values]
    extra = sorted(f for f in values if f not in FAMILY_ORDER)
    return present + extra


def _read_move_invocations() -> pd.DataFrame:
    if not MOVE_INVOCATIONS_CSV.exists():
        return pd.DataFrame()
    return pd.read_csv(MOVE_INVOCATIONS_CSV)


def plot_dataset_overview() -> None:
    rows = dataset_rows()
    if not rows:
        return
    df = pd.DataFrame(rows)
    df["family_group"] = df["family"].map(family_group)
    counts = df.groupby(["family", "scale"]).size().unstack(fill_value=0)
    families = _order_families(list(counts.index))
    counts = counts.reindex(families)
    fig, ax = plt.subplots(figsize=(7, 4))
    scales = [c for c in ("small", "large") if c in counts.columns]
    bottom = pd.Series(0.0, index=counts.index)
    for i, scale in enumerate(scales):
        ax.bar(counts.index, counts[scale], bottom=bottom, label=scale, color=PALETTE[i])
        bottom = bottom + counts[scale]
    ax.set_ylabel("Number of instances")
    ax.set_xlabel("Schneider family")
    ax.set_title("Dataset overview: instances by family and scale")
    ax.legend(title="Scale", frameon=False)
    _save(fig, "dataset_overview")


def plot_large_instance_win_tie_loss(df: pd.DataFrame) -> None:
    """Stacked win/tie/loss bars for each equal-budget ranking method against RANDOM_RANKING,
    large (56-instance) subset only (see ``equal_budget_large_instance_results`` table)."""
    table = build_equal_budget_large_instance_results(df)
    table = table[table["method"] != EQUAL_BUDGET_BASELINE]
    if table.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    methods = list(table["method"])
    wins = table["win_vs_random"].to_numpy()
    ties = table["tie_vs_random"].to_numpy()
    losses = table["loss_vs_random"].to_numpy()
    ax.bar(methods, wins, label="win", color=PALETTE[2])
    ax.bar(methods, ties, bottom=wins, label="tie", color=PALETTE[6])
    ax.bar(methods, losses, bottom=wins + ties, label="loss", color=PALETTE[3])
    ax.set_ylabel("Large instances (of 56)")
    ax.set_title(f"Win/tie/loss vs {EQUAL_BUDGET_BASELINE} (large instances)")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    ax.legend(frameon=False)
    _save(fig, "large_instance_win_tie_loss")


def plot_vehicles_by_family(df: pd.DataFrame) -> None:
    if df.empty or "family" not in df.columns:
        return
    families = _order_families(list(df["family"].dropna().unique()))
    if not families:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    data = [df.loc[df["family"] == f, "vehicles"].to_numpy() for f in families]
    box = ax.boxplot(data, tick_labels=families, patch_artist=True)
    for patch, color in zip(box["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_ylabel("Vehicles used")
    ax.set_xlabel("Family")
    ax.set_title("Vehicles used by family (all methods)")
    _save(fig, "vehicles_by_family")


def plot_distance_when_vehicle_equal(df: pd.DataFrame) -> None:
    """Mean distance delta vs RANDOM_RANKING, restricted to instance pairs with equal median
    vehicle counts (see module docstring in :mod:`chargecegis.statistics`)."""
    table = build_equal_budget_large_instance_results(df)
    table = table[table["method"] != EQUAL_BUDGET_BASELINE].dropna(
        subset=["mean_distance_delta_vs_random_when_fleet_equal"]
    )
    if table.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    methods = list(table["method"])
    deltas = table["mean_distance_delta_vs_random_when_fleet_equal"].to_numpy()
    colors = [PALETTE[2] if d < 0 else PALETTE[3] for d in deltas]
    ax.bar(methods, deltas, color=colors)
    ax.axhline(0.0, color="#444444", linewidth=0.8)
    ax.set_ylabel(f"Mean distance delta vs {EQUAL_BUDGET_BASELINE}\n(negative = better, fleet-equal pairs only)")
    ax.set_title("Distance when vehicle count is equal")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, "distance_when_vehicle_equal")


def plot_runtime_by_method(df: pd.DataFrame) -> None:
    if df.empty or "method" not in df.columns:
        return
    grouped = df.groupby("method")["runtime_seconds"].mean().sort_values(ascending=False)
    if grouped.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(grouped.index, grouped.to_numpy(), color=PALETTE[: len(grouped)] * 3)
    ax.set_ylabel("Mean runtime (seconds)")
    ax.set_title("Runtime by method")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, "runtime_by_method")


def plot_candidate_selection_distribution() -> None:
    """Candidate-pool size seen at each ranking call: should be near-identical across
    equal-budget methods sharing the same pool (sanity/equal-budget-fidelity check)."""
    moves = _read_move_invocations()
    if moves.empty or "candidate_count" not in moves.columns:
        return
    methods = [m for m in EQUAL_BUDGET_RANKING_METHODS if m in set(moves.get("method", []))]
    if not methods:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    data = [moves.loc[moves["method"] == m, "candidate_count"].to_numpy() for m in methods]
    box = ax.boxplot(data, tick_labels=methods, patch_artist=True)
    for patch, color in zip(box["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_ylabel("Candidates evaluated per iteration")
    ax.set_title("Candidate-pool size by ranking method")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, "candidate_selection_distribution")


def plot_effective_move_rate() -> None:
    moves = _read_move_invocations()
    if moves.empty or "method" not in moves.columns:
        return
    moves = moves.copy()
    moves["effective"] = (
        moves["customer_sequence_changed"].astype(bool) | moves["station_sequence_changed"].astype(bool)
    )
    grouped = moves.groupby("method")["effective"].mean().sort_values(ascending=False)
    if grouped.empty:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.bar(grouped.index, grouped.to_numpy(), color=PALETTE[: len(grouped)] * 3)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Effective-move rate")
    ax.set_title("Effective-move rate by method")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, "effective_move_rate")


def plot_charging_reconstruction_depth() -> None:
    """Distribution of |station_count_after - station_count_before| per accepted invocation, a
    proxy for how much charging reconstruction each move required. Skips gracefully when the
    required columns are not present (e.g. no move invocations recorded yet)."""
    moves = _read_move_invocations()
    required = {"station_count_before", "station_count_after", "method", "accepted"}
    if moves.empty or not required.issubset(moves.columns):
        return
    accepted = moves[moves["accepted"].astype(bool)].copy()
    if accepted.empty:
        return
    accepted["station_depth"] = (accepted["station_count_after"] - accepted["station_count_before"]).abs()
    methods = [m for m in EQUAL_BUDGET_RANKING_METHODS if m in set(accepted.get("method", []))]
    if not methods:
        return
    fig, ax = plt.subplots(figsize=(7, 4.5))
    data = [accepted.loc[accepted["method"] == m, "station_depth"].to_numpy() for m in methods]
    box = ax.boxplot(data, tick_labels=methods, patch_artist=True)
    for patch, color in zip(box["boxes"], PALETTE):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    ax.set_ylabel("|Δ station count| on accepted moves")
    ax.set_title("Charging-reconstruction depth by method")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _save(fig, "charging_reconstruction_depth")


def generate_all_figures(results_csv: Path) -> None:
    plot_dataset_overview()
    if results_csv.exists():
        df = pd.read_csv(results_csv)
        plot_large_instance_win_tie_loss(df)
        plot_vehicles_by_family(df)
        plot_distance_when_vehicle_equal(df)
        plot_runtime_by_method(df)
    plot_candidate_selection_distribution()
    plot_effective_move_rate()
    plot_charging_reconstruction_depth()
    typer.echo(f"Wrote figures to {FIGURES_DIR}")


def main(
    results: Path = typer.Option(DEFAULT_RESULTS_CSV, "--results", help="Path to full_dataset_runs.csv"),
) -> None:
    generate_all_figures(results)


if __name__ == "__main__":
    typer.run(main)
