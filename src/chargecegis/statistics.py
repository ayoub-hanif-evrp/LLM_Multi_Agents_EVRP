"""ChargeCEGIS results analysis: paired statistics and summary tables.

    python -m chargecegis.statistics --results results/raw/full_dataset_runs.csv

Reads the per-run CSV produced by ``chargecegis.experiment run-pilot`` / ``run-full-dataset`` and
writes summary tables (CSV + Markdown) into ``results/tables/``. The instance is the statistical
unit: seeds are collapsed to a per-instance median before any method is compared against another,
so a method is never given credit for simply being re-sampled more often (see project spec
section 22).

Equal-budget ranking methods (``method_kind == "equal_budget"``: RANDOM_RANKING,
HANDCRAFTED_CHARGING_RANKING, HANDCRAFTED_TIME_RANKING, HANDCRAFTED_COMBINED_RANKING,
REFERENCE_DSL_RANKING) share the same merged initial solution, candidate pool, and repair budget
per instance/seed (see :mod:`chargecegis.alns`), so they are directly comparable against each
other via paired win/tie/loss on the (vehicles, distance) lexicographic score. Distance is only
compared when the paired vehicle counts are equal (fleet size dominates the objective).
``CLASSIC_ALNS_REFERENCE`` uses an unrelated (unequal-budget) destroy/repair interface and is
always reported in its own table, never mixed into the equal-budget win/tie/loss comparison.
"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

import pandas as pd
import typer

from chargecegis.data import discover_instances, load_instance

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results"
DEFAULT_RESULTS_CSV = RESULTS_DIR / "raw" / "full_dataset_runs.csv"
MOVE_INVOCATIONS_CSV = RESULTS_DIR / "raw" / "move_invocations.csv"
TABLES_DIR = RESULTS_DIR / "tables"
DATASET_MANIFEST = RESULTS_DIR / "manifests" / "dataset_manifest.json"

CLASSIC_METHOD = "CLASSIC_ALNS_REFERENCE"
EQUAL_BUDGET_BASELINE = "RANDOM_RANKING"
EQUAL_BUDGET_RANKING_METHODS = (
    "RANDOM_RANKING", "HANDCRAFTED_CHARGING_RANKING", "HANDCRAFTED_TIME_RANKING",
    "HANDCRAFTED_COMBINED_RANKING", "REFERENCE_DSL_RANKING",
)
_LEX_SCALE = 1.0e6  # vehicles dominate distance in the combined lexicographic score
_FLEET_TOLERANCE = 1e-9

FAMILY_ORDER = ["C1", "C2", "R1", "R2", "RC1", "RC2"]


def percentile(values: list[float], q: float) -> float:
    if not values or not 0 <= q <= 100:
        raise ValueError("nonempty values and q in [0, 100] required")
    data = sorted(values)
    pos = (len(data) - 1) * q / 100
    lo, hi = int(pos), min(int(pos) + 1, len(data) - 1)
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def paired_win_tie_loss(left: list[float], right: list[float]) -> dict[str, int]:
    if len(left) != len(right):
        raise ValueError("paired samples must align")
    return {
        "win": sum(a < b for a, b in zip(left, right)),
        "tie": sum(a == b for a, b in zip(left, right)),
        "loss": sum(a > b for a, b in zip(left, right)),
    }


def family_group(family: str) -> str:
    return "RC" if family.startswith("RC") else family[:1]


def horizon_class(family: str) -> str:
    return "narrow" if family.endswith("1") else "wide"


def _write_markdown_table(df: pd.DataFrame, path: Path, note: str | None = None) -> None:
    if df.empty:
        path.write_text("_No data available._\n", encoding="utf-8")
        return
    lines: list[str] = []
    if note:
        lines.append(f"_{note}_\n")
    columns = list(df.columns)
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join("---" for _ in columns) + " |")
    for _, row in df.iterrows():
        cells = []
        for value in row:
            if isinstance(value, float):
                cells.append("nan" if pd.isna(value) else f"{value:.4g}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_table(df: pd.DataFrame, stem: str, note: str | None = None) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(TABLES_DIR / f"{stem}.csv", index=False)
    _write_markdown_table(df, TABLES_DIR / f"{stem}.md", note=note)


def dataset_rows() -> list[dict[str, object]]:
    if DATASET_MANIFEST.exists():
        payload = json.loads(DATASET_MANIFEST.read_text(encoding="utf-8"))
        return list(payload.get("instances", []))
    instances = [load_instance(p) for p in discover_instances()]
    return [
        {
            "instance_id": inst.instance_id,
            "family": inst.metadata.get("family"),
            "scale": inst.metadata.get("scale"),
            "num_customers": len(inst.customer_ids),
            "num_stations": len(inst.station_ids),
        }
        for inst in instances
    ]


def build_dataset_summary() -> pd.DataFrame:
    rows = dataset_rows()
    if not rows:
        return pd.DataFrame(
            columns=["scale", "family_group", "horizon", "num_instances", "avg_customers", "avg_stations"]
        )
    df = pd.DataFrame(rows)
    df["family_group"] = df["family"].map(family_group)
    df["horizon"] = df["family"].map(horizon_class)
    grouped = (
        df.groupby(["scale", "family_group", "horizon"])
        .agg(
            num_instances=("instance_id", "count"),
            avg_customers=("num_customers", "mean"),
            avg_stations=("num_stations", "mean"),
            min_customers=("num_customers", "min"),
            max_customers=("num_customers", "max"),
        )
        .reset_index()
        .sort_values(["scale", "family_group", "horizon"])
    )
    return grouped


def _per_instance_median(df: pd.DataFrame, method: str) -> pd.DataFrame:
    subset = df[df["method"] == method]
    if subset.empty:
        return pd.DataFrame(columns=["instance_id", "vehicles", "distance"]).set_index("instance_id")
    return (
        subset.groupby("instance_id")
        .agg(vehicles=("vehicles", "median"), distance=("distance", "median"))
    )


def _lex_score(vehicles: float, distance: float) -> float:
    return vehicles * _LEX_SCALE + distance


def _order_by_family(df: pd.DataFrame, column: str = "family") -> pd.DataFrame:
    out = df.copy()
    out["_order"] = out[column].map({f: i for i, f in enumerate(FAMILY_ORDER)}).fillna(len(FAMILY_ORDER))
    return out.sort_values(["_order", *([c for c in ("method",) if c in out.columns])]).drop(columns="_order").reset_index(drop=True)


def build_equal_budget_large_instance_results(df: pd.DataFrame) -> pd.DataFrame:
    """56-large-instance-only comparison across equal-budget ranking methods, paired
    win/tie/loss against RANDOM_RANKING on the (vehicles, distance) lexicographic score, plus a
    fleet-size-gated mean distance delta (see module docstring)."""
    columns = [
        "method", "n_instances", "win_vs_random", "tie_vs_random", "loss_vs_random",
        "median_vehicles", "median_distance", "distance_comparable_pairs",
        "mean_distance_delta_vs_random_when_fleet_equal",
    ]
    if df.empty or "method_kind" not in df.columns:
        return pd.DataFrame(columns=columns)
    large = df[(df.get("scale") == "large") & (df["method_kind"] == "equal_budget")]
    if large.empty:
        return pd.DataFrame(columns=columns)
    baseline_med = _per_instance_median(large, EQUAL_BUDGET_BASELINE)
    rows: list[dict[str, object]] = []
    for method, sub in large.groupby("method"):
        method = str(method)
        method_med = _per_instance_median(large, method)
        common = method_med.index.intersection(baseline_med.index)
        wtl = {"win": 0, "tie": 0, "loss": 0}
        distance_pairs = 0
        mean_delta: float = float("nan")
        if method != EQUAL_BUDGET_BASELINE and len(common) > 0:
            left = [_lex_score(*method_med.loc[i]) for i in common]
            right = [_lex_score(*baseline_med.loc[i]) for i in common]
            wtl = paired_win_tie_loss(left, right)
            equal_fleet = [
                i for i in common
                if abs(float(method_med.loc[i, "vehicles"]) - float(baseline_med.loc[i, "vehicles"])) < _FLEET_TOLERANCE
            ]
            distance_pairs = len(equal_fleet)
            if equal_fleet:
                deltas = [
                    float(method_med.loc[i, "distance"]) - float(baseline_med.loc[i, "distance"])
                    for i in equal_fleet
                ]
                mean_delta = float(mean(deltas))
        rows.append({
            "method": method,
            "n_instances": int(len(method_med)),
            "win_vs_random": int(wtl["win"]),
            "tie_vs_random": int(wtl["tie"]),
            "loss_vs_random": int(wtl["loss"]),
            "median_vehicles": float(sub["vehicles"].median()),
            "median_distance": float(sub["distance"].median()),
            "distance_comparable_pairs": distance_pairs,
            "mean_distance_delta_vs_random_when_fleet_equal": mean_delta,
        })
    return pd.DataFrame(rows, columns=columns).sort_values("method").reset_index(drop=True)


def build_equal_budget_results_by_family(df: pd.DataFrame) -> pd.DataFrame:
    columns = ["family", "method", "n_runs", "feasible_rate", "median_vehicles", "median_distance",
               "mean_runtime_seconds"]
    if df.empty or "method_kind" not in df.columns or "family" not in df.columns:
        return pd.DataFrame(columns=columns)
    equal_budget = df[df["method_kind"] == "equal_budget"]
    if equal_budget.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for (family, method), sub in equal_budget.groupby(["family", "method"]):
        rows.append({
            "family": family,
            "method": method,
            "n_runs": len(sub),
            "feasible_rate": float(sub["feasible"].mean()),
            "median_vehicles": float(sub["vehicles"].median()),
            "median_distance": float(sub["distance"].median()),
            "mean_runtime_seconds": float(sub["runtime_seconds"].mean()),
        })
    return _order_by_family(pd.DataFrame(rows, columns=columns))


def build_classic_alns_reference(df: pd.DataFrame) -> pd.DataFrame:
    """CLASSIC_ALNS_REFERENCE reported alone, by scale: never mixed into equal-budget tables."""
    columns = ["scale", "n_runs", "feasible_rate", "median_vehicles", "median_distance",
               "mean_runtime_seconds"]
    if df.empty or "method" not in df.columns:
        return pd.DataFrame(columns=columns)
    classic = df[df["method"] == CLASSIC_METHOD]
    if classic.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for scale, sub in classic.groupby("scale"):
        rows.append({
            "scale": scale,
            "n_runs": len(sub),
            "feasible_rate": float(sub["feasible"].mean()),
            "median_vehicles": float(sub["vehicles"].median()),
            "median_distance": float(sub["distance"].median()),
            "mean_runtime_seconds": float(sub["runtime_seconds"].mean()),
        })
    return pd.DataFrame(rows, columns=columns).sort_values("scale").reset_index(drop=True)


def build_policy_behavior(df: pd.DataFrame) -> pd.DataFrame:
    """Equal-budget-ranking move-invocation behavior (candidate pool size, feasibility,
    acceptance, effective-change rate) read from ``move_invocations.csv``."""
    columns = ["method", "total_invocations", "mean_candidate_count", "feasible_rate",
               "accepted_rate", "new_best_rate", "effective_move_rate"]
    present = set(df["method"]) if not df.empty and "method" in df.columns else set()
    methods = [m for m in EQUAL_BUDGET_RANKING_METHODS if m in present] or list(EQUAL_BUDGET_RANKING_METHODS)
    if MOVE_INVOCATIONS_CSV.exists():
        moves = pd.read_csv(MOVE_INVOCATIONS_CSV)
    else:
        moves = pd.DataFrame(columns=[
            "method", "candidate_count", "feasible", "accepted", "new_best",
            "customer_sequence_changed", "station_sequence_changed",
        ])
    rows = []
    for method in methods:
        sub = moves[moves["method"] == method] if "method" in moves.columns else moves.iloc[0:0]
        if sub.empty:
            rows.append({
                "method": method, "total_invocations": 0, "mean_candidate_count": 0.0,
                "feasible_rate": 0.0, "accepted_rate": 0.0, "new_best_rate": 0.0,
                "effective_move_rate": 0.0,
            })
            continue
        effective = (sub["customer_sequence_changed"].astype(bool) | sub["station_sequence_changed"].astype(bool))
        rows.append({
            "method": method,
            "total_invocations": int(len(sub)),
            "mean_candidate_count": float(sub["candidate_count"].mean()),
            "feasible_rate": float(sub["feasible"].astype(bool).mean()),
            "accepted_rate": float(sub["accepted"].astype(bool).mean()),
            "new_best_rate": float(sub["new_best"].astype(bool).mean()),
            "effective_move_rate": float(effective.mean()),
        })
    return pd.DataFrame(rows, columns=columns)


def build_runtime_results(df: pd.DataFrame) -> pd.DataFrame:
    group_cols = [c for c in ("method", "scale") if c in df.columns]
    if not group_cols or df.empty:
        return pd.DataFrame(columns=["method", "scale", "n_runs", "mean_runtime_seconds",
                                      "median_runtime_seconds", "mean_time_to_best",
                                      "mean_iterations_completed"])
    rows = []
    for key, sub in df.groupby(group_cols):
        key = key if isinstance(key, tuple) else (key,)
        record = dict(zip(group_cols, key))
        record.update({
            "n_runs": len(sub),
            "mean_runtime_seconds": float(sub["runtime_seconds"].mean()),
            "median_runtime_seconds": float(sub["runtime_seconds"].median()),
            "mean_time_to_best": float(sub["time_to_best"].mean()),
            "mean_iterations_completed": float(sub["iterations_completed"].mean()),
        })
        rows.append(record)
    return pd.DataFrame(rows).sort_values(group_cols).reset_index(drop=True)


def generate_all_tables(results_csv: Path) -> None:
    TABLES_DIR.mkdir(parents=True, exist_ok=True)
    _write_table(build_dataset_summary(), "dataset_summary")
    if not results_csv.exists():
        typer.echo(f"No results at {results_csv}; wrote dataset_summary only.")
        return
    df = pd.read_csv(results_csv)
    _write_table(
        build_equal_budget_large_instance_results(df), "equal_budget_large_instance_results",
        note="Win/tie/loss against RANDOM_RANKING on the (vehicles, distance) lexicographic "
             "score, large (56-instance) subset only. Distance deltas are computed only over "
             "instance pairs where the paired median vehicle counts are equal.",
    )
    _write_table(build_equal_budget_results_by_family(df), "equal_budget_results_by_family")
    _write_table(
        build_classic_alns_reference(df), "classic_alns_reference",
        note="CLASSIC_ALNS_REFERENCE uses an unequal-budget destroy/repair interface; reported "
             "separately and never mixed into the equal-budget comparison tables.",
    )
    _write_table(build_policy_behavior(df), "policy_behavior")
    _write_table(build_runtime_results(df), "runtime_results")
    typer.echo(f"Wrote 6 tables to {TABLES_DIR}")


def main(
    results: Path = typer.Option(DEFAULT_RESULTS_CSV, "--results", help="Path to full_dataset_runs.csv"),
) -> None:
    generate_all_tables(results)


if __name__ == "__main__":
    typer.run(main)
