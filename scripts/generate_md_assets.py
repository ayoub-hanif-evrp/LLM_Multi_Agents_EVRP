"""Rebuild results/md figures and literature tables from stored campaign JSON/CSV."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "results" / "md"
FIG = MD / "figures"
TAB = MD / "tables"
RAW = TAB / "raw_autolab"

# Keskin & Çatay (2016) working paper Table 2: ALNS on Schneider full-recharge EVRPTW.
# Keys use this repo's instance ids (*_21). Values: (vehicles, distance).
KESKIN_2016_ALNS = {
    "c101_21": (12, 1053.83),
    "c102_21": (11, 1056.12),
    "c103_21": (11, 1001.81),
    "c104_21": (10, 951.57),
    "c105_21": (11, 1075.37),
    "c106_21": (11, 1057.65),
    "c107_21": (11, 1031.56),
    "c108_21": (11, 1015.68),
    "c109_21": (10, 1069.16),
    "c201_21": (4, 645.16),
    "c202_21": (4, 645.16),
    "c203_21": (4, 644.98),
    "c204_21": (4, 636.43),
    "c205_21": (4, 641.13),
    "c206_21": (4, 638.17),
    "c207_21": (4, 638.17),
    "c208_21": (4, 638.17),
    "r101_21": (18, 1679.06),
    "r102_21": (16, 1524.14),
    "r103_21": (13, 1312.50),
    "r104_21": (12, 1071.89),
    "r105_21": (15, 1383.29),
    "r106_21": (14, 1276.15),
    "r107_21": (12, 1148.43),
    "r108_21": (11, 1051.59),
    "r109_21": (13, 1214.72),
    "r110_21": (12, 1097.89),
    "r111_21": (12, 1109.14),
    "r112_21": (11, 1038.74),
    "r201_21": (3, 1265.67),
    "r202_21": (3, 1052.32),
    "r203_21": (3, 895.54),
    "r204_21": (2, 780.98),
    "r205_21": (3, 987.36),
    "r206_21": (3, 922.70),
    "r207_21": (2, 847.14),
    "r208_21": (2, 736.12),
    "r209_21": (3, 871.22),
    "r210_21": (3, 843.65),
    "r211_21": (3, 761.56),
    "rc101_21": (16, 1731.07),
    "rc102_21": (15, 1551.69),
    "rc103_21": (13, 1351.73),
    "rc104_21": (11, 1232.45),
    "rc105_21": (14, 1473.24),
    "rc106_21": (14, 1414.99),
    "rc107_21": (12, 1283.05),
    "rc108_21": (11, 1209.11),
    "rc201_21": (4, 1446.84),
    "rc202_21": (3, 1450.34),
    "rc203_21": (3, 1069.27),
    "rc204_21": (3, 887.45),
    "rc205_21": (3, 1277.60),
    "rc206_21": (3, 1207.64),
    "rc207_21": (3, 994.48),
    "rc208_21": (3, 841.34),
}

# BKS cited in that same Table 2 (SSG / GS / HPH), not mixed with partial recharge.
KESKIN_2016_CITED_BKS = {
    "c101_21": (12, 1053.83, "SSG"),
    "c102_21": (11, 1051.38, "GS"),
    "c103_21": (10, 1034.86, "GS"),
    "c104_21": (10, 961.88, "GS"),
    "c105_21": (11, 1075.37, "SSG"),
    "c106_21": (11, 1057.65, "HPH"),
    "c107_21": (11, 1031.56, "SSG"),
    "c108_21": (10, 1095.66, "GS"),
    "c109_21": (10, 1033.67, "GS"),
    "c201_21": (4, 645.16, "SSG"),
    "c202_21": (4, 645.16, "SSG"),
    "c203_21": (4, 644.98, "SSG"),
    "c204_21": (4, 636.43, "SSG"),
    "c205_21": (4, 641.13, "SSG"),
    "c206_21": (4, 638.17, "SSG"),
    "c207_21": (4, 638.17, "SSG"),
    "c208_21": (4, 638.17, "SSG"),
    "r101_21": (18, 1663.04, "HPH"),
    "r102_21": (16, 1487.41, "GS"),
    "r103_21": (13, 1271.35, "GS"),
    "r104_21": (11, 1088.43, "SSG"),
    "r105_21": (14, 1442.35, "GS"),
    "r106_21": (13, 1324.10, "GS"),
    "r107_21": (12, 1150.95, "GS"),
    "r108_21": (11, 1050.04, "SSG"),
    "r109_21": (12, 1261.31, "GS"),
    "r110_21": (11, 1119.50, "GS"),
    "r111_21": (12, 1106.19, "SSG"),
    "r112_21": (11, 1016.63, "GS"),
    "r201_21": (3, 1264.82, "SSG"),
    "r202_21": (3, 1052.32, "SSG"),
    "r203_21": (3, 895.54, "GS"),
    "r204_21": (2, 779.49, "GS"),
    "r205_21": (3, 987.36, "GS"),
    "r206_21": (3, 922.19, "GS"),
    "r207_21": (2, 845.26, "GS"),
    "r208_21": (2, 736.12, "GS"),
    "r209_21": (3, 867.05, "GS"),
    "r210_21": (3, 846.20, "GS"),
    "r211_21": (2, 827.89, "GS"),
    "rc101_21": (16, 1726.91, "HPH"),
    "rc102_21": (14, 1552.08, "HPH"),
    "rc103_21": (13, 1350.09, "GS"),
    "rc104_21": (11, 1227.25, "GS"),
    "rc105_21": (14, 1475.31, "HPH"),
    "rc106_21": (13, 1427.21, "GS"),
    "rc107_21": (12, 1274.89, "SSG"),
    "rc108_21": (11, 1197.83, "GS"),
    "rc201_21": (4, 1444.94, "SSG"),
    "rc202_21": (3, 1410.74, "GS"),
    "rc203_21": (3, 1055.19, "GS"),
    "rc204_21": (3, 884.80, "GS"),
    "rc205_21": (3, 1273.55, "GS"),
    "rc206_21": (3, 1188.63, "GS"),
    "rc207_21": (3, 985.03, "GS"),
    "rc208_21": (3, 836.29, "GS"),
}

# Family means from Keskin & Çatay (2016) Table 1 (full recharge, mean vehicles / mean distance).
FAMILY_MEANS = [
    {"family": "C1", "ssg_m": 10.67, "ssg_f": 1050.04, "kc_m": 10.89, "kc_f_delta_pct": 0.78},
    {"family": "C2", "ssg_m": 4.00, "ssg_f": 640.92, "kc_m": 4.00, "kc_f_delta_pct": 0.00},
    {"family": "R1", "ssg_m": 12.83, "ssg_f": 1268.60, "kc_m": 13.25, "kc_f_delta_pct": 0.69},
    {"family": "R2", "ssg_m": 2.64, "ssg_f": 919.04, "kc_m": 2.82, "kc_f_delta_pct": -0.07},
    {"family": "RC1", "ssg_m": 13.13, "ssg_f": 1415.84, "kc_m": 13.38, "kc_f_delta_pct": 0.13},
    {"family": "RC2", "ssg_m": 3.13, "ssg_f": 1146.76, "kc_m": 3.25, "kc_f_delta_pct": 0.08},
]


def family_of(instance_id: str) -> str:
    name = instance_id.lower().replace("_21", "")
    if name.startswith("rc"):
        return "RC2" if name.startswith("rc2") else "RC1"
    if name.startswith("c2"):
        return "C2"
    if name.startswith("c"):
        return "C1"
    if name.startswith("r2"):
        return "R2"
    return "R1"


def style_ax(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def write_csv(path: Path, rows: list[dict], keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in keys})


def load_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)

    inventory = load_json(RAW / "inventory.json")
    models = load_json(RAW / "models.json")
    autolab_csv = load_csv(TAB / "autolab_model_comparison.csv")
    baselines = load_csv(TAB / "baselines.csv")
    lit_small = load_csv(TAB / "literature_small_cplex.csv")
    lit_full = load_csv(TAB / "literature_large_full.csv")

    autolab_json = {}
    for path in sorted(RAW.glob("autolab_*.json")):
        payload = load_json(path)
        autolab_json[payload["model_id"]] = payload

    # --- literature merge table ---
    comparison_rows = []
    for row in lit_full:
        iid = row["instance_id"]
        keskin = KESKIN_2016_ALNS.get(iid)
        cited = KESKIN_2016_CITED_BKS.get(iid)
        comparison_rows.append(
            {
                "instance_id": iid,
                "family": family_of(iid),
                "held_out": row["held_out"],
                "schneider2014_bks_m": row["bks_vehicles"],
                "schneider2014_bks_f": row["bks_distance"],
                "schneider2014_vnsts_m": row["vnsts_vehicles"],
                "schneider2014_vnsts_f": row["vnsts_distance"],
                "keskin2016_alns_m": keskin[0] if keskin else "",
                "keskin2016_alns_f": keskin[1] if keskin else "",
                "bks_2016_m": cited[0] if cited else "",
                "bks_2016_f": cited[1] if cited else "",
                "bks_2016_ref": cited[2] if cited else "",
                "autolab_gen0": "not_run_F1_failed",
            }
        )
    write_csv(
        TAB / "literature_100cust_comparison.csv",
        comparison_rows,
        [
            "instance_id",
            "family",
            "held_out",
            "schneider2014_bks_m",
            "schneider2014_bks_f",
            "schneider2014_vnsts_m",
            "schneider2014_vnsts_f",
            "keskin2016_alns_m",
            "keskin2016_alns_f",
            "bks_2016_m",
            "bks_2016_f",
            "bks_2016_ref",
            "autolab_gen0",
        ],
    )
    write_csv(
        TAB / "literature_keskin2016_alns.csv",
        [
            {
                "instance_id": k,
                "family": family_of(k),
                "held_out": family_of(k) == "RC2",
                "vehicles": v[0],
                "distance": v[1],
                "source": "Keskin & Catay 2016 working paper Table 2 (full recharge ALNS)",
            }
            for k, v in KESKIN_2016_ALNS.items()
        ],
        ["instance_id", "family", "held_out", "vehicles", "distance", "source"],
    )
    write_csv(
        TAB / "literature_family_averages.csv",
        [
            {
                **row,
                "autolab_gen0_m": "n/a",
                "note": "SSG=Schneider 2014 VNS/TS family mean; KC=Keskin 2016 Table 1 full recharge",
            }
            for row in FAMILY_MEANS
        ],
        ["family", "ssg_m", "ssg_f", "kc_m", "kc_f_delta_pct", "autolab_gen0_m", "note"],
    )
    write_csv(
        TAB / "literature_large.csv",
        [
            {
                "instance_id": r["instance_id"],
                "schneider2014_vnsts_m": r["schneider2014_vnsts_m"],
                "schneider2014_vnsts_f": r["schneider2014_vnsts_f"],
                "keskin2016_alns_m": r["keskin2016_alns_m"],
                "keskin2016_alns_f": r["keskin2016_alns_f"],
                "held_out": r["held_out"],
            }
            for r in comparison_rows
        ],
        [
            "instance_id",
            "schneider2014_vnsts_m",
            "schneider2014_vnsts_f",
            "keskin2016_alns_m",
            "keskin2016_alns_f",
            "held_out",
        ],
    )

    # --- AutoLab F1 per instance ---
    f1_rows = []
    for model_id, payload in autolab_json.items():
        for item in payload.get("per_instance_f1") or []:
            err = (item.get("error") or "").replace("\n", " ")[:180]
            f1_rows.append(
                {
                    "model_id": model_id,
                    "model": payload.get("model"),
                    "instance_id": item.get("instance_id"),
                    "feasible": item.get("feasible"),
                    "crashed": item.get("crashed"),
                    "vehicles": item.get("vehicles"),
                    "distance": item.get("distance"),
                    "literature_m": item.get("literature_m"),
                    "literature_f": item.get("literature_f"),
                    "error": err,
                    "primary_cause": (payload.get("critic") or {}).get("primary_cause", ""),
                }
            )
    write_csv(
        TAB / "autolab_f1_per_instance.csv",
        f1_rows,
        [
            "model_id",
            "model",
            "instance_id",
            "feasible",
            "crashed",
            "vehicles",
            "distance",
            "literature_m",
            "literature_f",
            "primary_cause",
            "error",
        ],
    )

    # --- figures ---
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [r["model_id"] for r in models]
    colors = ["#2a6f97" if r["status"] == "installed" else "#9b2226" for r in models]
    ax.bar(labels, [1 if r["status"] == "installed" else 0 for r in models], color=colors)
    style_ax(ax, "Configured comparison models (homogeneous 5-agent teams)", "Model profile", "Installed (1) / skipped (0)")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG / "model_availability.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6, 4))
    fam = inventory["by_family_all"]
    ax.bar(list(fam.keys()), list(fam.values()), color="#2a6f97")
    style_ax(ax, "Schneider EVRPTW instances by family (n=92)", "Family", "Instance count")
    fig.tight_layout()
    fig.savefig(FIG / "dataset_families.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ids = [r["instance_id"] for r in lit_small if str(r["instance_id"]).endswith("C5") and str(r["held_out"]).lower() == "false"]
    cplex = {r["instance_id"]: r for r in lit_small}
    greedy = {r["instance_id"]: r for r in baselines if r["baseline"] == "greedy_nn"}
    dedicated = {r["instance_id"]: r for r in baselines if r["baseline"] == "dedicated"}
    cplex_m = [float(cplex[i]["cplex_m"]) for i in ids]
    g_m = [float(greedy[i]["vehicles"]) if i in greedy else 0 for i in ids]
    d_m = [float(dedicated[i]["vehicles"]) if i in dedicated else 0 for i in ids]
    x = list(range(len(ids)))
    ax.bar([i - 0.25 for i in x], cplex_m, width=0.25, label="CPLEX 2014 (opt/UB)", color="#1d3557")
    ax.bar(x, g_m, width=0.25, label="Greedy NN baseline", color="#457b9d")
    ax.bar([i + 0.25 for i in x], d_m, width=0.25, label="Dedicated-route baseline", color="#a8dadc")
    ax.set_xticks(x)
    ax.set_xticklabels(ids, rotation=45, ha="right")
    style_ax(ax, "Vehicles on 5-customer discovery instances vs Schneider 2014 CPLEX", "Instance", "Vehicles")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "vehicles_c5_vs_cplex.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4))
    names = [r["model_id"] for r in autolab_csv]
    rates = []
    for row in autolab_csv:
        value = row.get("f1_feasible_rate")
        rates.append(float(value) if value not in ("", None) else 0.0)
    ax.bar(names, rates, color="#2a6f97")
    style_ax(
        ax,
        "AutoLab generated-solver F1 feasible rate (5-customer discovery)",
        "Homogeneous 5-agent model",
        "Feasible rate",
    )
    ax.set_ylim(0, 1.05)
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    fig.tight_layout()
    fig.savefig(FIG / "autolab_f1_feasible.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    labels = []
    json_ok, f0_ok, f1_ok = [], [], []
    for row in autolab_csv:
        labels.append(row["model_id"])
        skipped = row["status"] == "SKIPPED_NOT_INSTALLED"
        json_ok.append(0 if skipped else 1)
        f0_ok.append(1 if str(row["f0_ok"]).lower() == "true" else 0)
        value = row.get("f1_feasible_rate")
        f1_ok.append(1 if value not in ("", None) and float(value) > 0 else 0)
    x = list(range(len(labels)))
    ax.bar([i - 0.25 for i in x], json_ok, width=0.25, label="Valid JSON after coerce", color="#1d3557")
    ax.bar(x, f0_ok, width=0.25, label="F0 has solve()", color="#2a6f97")
    ax.bar([i + 0.25 for i in x], f1_ok, width=0.25, label="F1 any feasible", color="#9b2226")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right")
    ax.set_ylim(0, 1.15)
    style_ax(ax, "Generation-0 pipeline gates by model", "Homogeneous 5-agent model", "Pass (1) / fail (0)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "pipeline_stages.png", dpi=160)
    plt.close(fig)

    family_m: dict[str, list[float]] = defaultdict(list)
    for row in lit_full:
        family_m[family_of(row["instance_id"])].append(float(row["bks_vehicles"]))
    order = ["C1", "C2", "R1", "R2", "RC1", "RC2"]
    fig, ax = plt.subplots(figsize=(6.5, 4))
    ax.bar(order, [sum(family_m[f]) / len(family_m[f]) for f in order], color="#2a6f97")
    style_ax(
        ax,
        "Schneider 2014 Table 4 BKS mean fleet size (100-customer)",
        "Family",
        "Mean vehicles",
    )
    fig.tight_layout()
    fig.savefig(FIG / "literature_large_vehicles.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    fams = [r["family"] for r in FAMILY_MEANS]
    ssg = [r["ssg_m"] for r in FAMILY_MEANS]
    kc = [r["kc_m"] for r in FAMILY_MEANS]
    x = list(range(len(fams)))
    ax.bar([i - 0.18 for i in x], ssg, width=0.36, label="Schneider 2014 VNS/TS (SSG)", color="#1d3557")
    ax.bar([i + 0.18 for i in x], kc, width=0.36, label="Keskin 2016 ALNS (full recharge)", color="#457b9d")
    ax.set_xticks(x)
    ax.set_xticklabels(fams)
    style_ax(
        ax,
        "Mean vehicles on 100-customer Schneider EVRPTW (full recharge)",
        "Family (RC2 is held out of AutoLab ranking)",
        "Mean vehicles",
    )
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "literature_family_mean_vehicles.png", dpi=160)
    plt.close(fig)

    # c101C5 vehicles: literature + baselines; AutoLab omitted as crash (annotated).
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    methods = ["CPLEX 2014", "VNS/TS 2014", "Dedicated\n(this evaluator)", "Greedy NN\n(this evaluator)"]
    vehicles = [2, 2, 5, 2]
    colors = ["#1d3557", "#2a6f97", "#a8dadc", "#e9c46a"]
    bars = ax.bar(methods, vehicles, color=colors)
    for bar, feasible in zip(bars, [True, True, True, False], strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.08,
            "feasible" if feasible else "infeasible",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax.set_ylim(0, 6.2)
    style_ax(ax, "c101C5 vehicles (full recharge). AutoLab Gen-0: crash, no score", "Method", "Vehicles")
    fig.tight_layout()
    fig.savefig(FIG / "c101C5_head_to_head.png", dpi=160)
    plt.close(fig)

    evo_path = TAB / "autolab_evolution.csv"
    if evo_path.exists():
        evo = load_csv(evo_path)
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        names = [r["model_id"] for r in evo]
        rates = []
        for row in evo:
            value = row.get("f1_feasible_rate")
            rates.append(float(value) if value not in ("", None) else 0.0)
        ax.bar(names, rates, color="#2a6f97")
        style_ax(
            ax,
            "AutoLab F1 feasible rate after 5 equal-budget evolution cycles",
            "Homogeneous 5-agent model",
            "Feasible rate",
        )
        ax.set_ylim(0, 1.05)
        plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
        fig.tight_layout()
        fig.savefig(FIG / "autolab_evolution_f1.png", dpi=160)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(7.8, 4.2))
    campaign_labels = []
    campaign_rates = []
    model_csv = TAB / "autolab_model_comparison.csv"
    if model_csv.exists():
        for row in load_csv(model_csv):
            if row.get("model_id") == "qwen25_coder_7b":
                campaign_labels.append("Gen-0")
                value = row.get("f1_feasible_rate")
                campaign_rates.append(float(value) if value not in ("", None) else 0.0)
                break
    for label, filename in (
        ("Evolution", "autolab_evolution.csv"),
        ("Spark", "autolab_spark.csv"),
    ):
        path = TAB / filename
        if not path.exists():
            continue
        rows = load_csv(path)
        chosen = next((r for r in rows if r.get("model_id") == "qwen25_coder_7b"), rows[0] if rows else None)
        if chosen is None:
            continue
        value = chosen.get("f1_feasible_rate")
        campaign_labels.append(label)
        campaign_rates.append(float(value) if value not in ("", None) else 0.0)
    if campaign_labels:
        ax.bar(campaign_labels, campaign_rates, color="#2a6f97")
        style_ax(
            ax,
            "Qwen 7B F1 feasible rate by campaign (same 8 discovery C5)",
            "Campaign",
            "Feasible rate",
        )
        ax.set_ylim(0, 1.05)
        fig.tight_layout()
        fig.savefig(FIG / "autolab_campaign_f1.png", dpi=160)
        plt.close(fig)

    print("wrote", FIG)
    print("png", sorted(p.name for p in FIG.glob("*.png")))


if __name__ == "__main__":
    main()
