"""Run AutoLab experiments, weak baselines, and literature comparison artifacts."""
from __future__ import annotations

import json
import time
import traceback
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib.pyplot as plt
import yaml

from evrptw_autolab.evaluation.fidelity import (
    by_customer_count,
    load_all,
    split_instances,
    write_split_manifest,
)
from evrptw_autolab.evaluation.runner import evaluate_fidelity
from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.registry import SKIPPED_NOT_INSTALLED, availability, list_profiles, make_backend, resolve_profile
from evrptw_autolab.problem.evaluator import evaluate_solution
from evrptw_autolab.problem.physics import distance, energy_required
from evrptw_autolab.problem.types import CandidateSolution, EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver

ROOT = Path(__file__).resolve().parents[1]
MD = ROOT / "results" / "md"
FIG = MD / "figures"
TAB = MD / "tables"
RAW = ROOT / "results" / "runs"


# Schneider et al. (2014) Transportation Science, Table 3: CPLEX vs VNS/TS on small instances.
# Vehicles (m) and distance (f). RC2 rows are literature-only; never used to pick a model.
SCHNEIDER_2014_SMALL_CPLEX = {
    "c101C5": (2, 257.75),
    "c103C5": (1, 176.05),
    "c206C5": (1, 242.56),
    "c208C5": (1, 158.48),
    "r104C5": (2, 136.69),
    "r105C5": (2, 156.08),
    "r202C5": (1, 128.78),
    "r203C5": (1, 179.06),
    "rc105C5": (2, 241.30),
    "rc108C5": (1, 253.93),
    "rc204C5": (1, 176.39),
    "rc208C5": (1, 167.98),
    "c101C10": (3, 393.76),
    "c104C10": (2, 273.93),
    "c202C10": (1, 304.06),
    "c205C10": (2, 228.28),
    "r102C10": (3, 249.19),
    "r103C10": (2, 207.05),
    "r201C10": (1, 241.51),
    "r203C10": (1, 218.21),
    "rc102C10": (4, 423.51),
    "rc108C10": (3, 345.93),
    "rc201C10": (1, 412.86),
    "rc205C10": (2, 325.98),
    "c103C15": (3, 384.29),
    "c106C15": (3, 275.13),
}

# Schneider et al. (2014) VNS/TS best on 100-customer instances (full recharge).
SCHNEIDER_2014_LARGE_VNSTS = {
    "c101_21": (12, 1053.83),
    "c102_21": (11, 1056.47),
    "c103_21": (10, 1041.55),
    "c104_21": (10, 979.51),
    "c105_21": (11, 1075.37),
    "c201_21": (4, 645.16),
    "c208_21": (4, 638.17),
    "r101_21": (18, 1670.80),
    "r102_21": (16, 1495.31),
    "r201_21": (3, 1262.06),
    "rc101_21": (16, 1731.07),
}

# Keskin & Çatay (2016) TRC: ALNS on the same Schneider full-recharge EVRPTW (selected BKS they report).
KESKIN_2016_ALNS = {
    "c101_21": (12, 1053.83),
    "c201_21": (4, 629.95),
    "r101_21": (17, 1772.39),
    "rc101_21": (15, 1744.85),
}


def dedicated_routes(instance: EVRPTWInstance) -> CandidateSolution:
    depot = instance.depot_id
    return CandidateSolution([[depot, cid, depot] for cid in instance.customer_ids], {"baseline": "dedicated"})


def greedy_nn_with_stations(instance: EVRPTWInstance) -> CandidateSolution:
    """Weak reference heuristic for scale, not the AutoLab method."""
    depot = instance.depot_id
    vehicle = instance.vehicle
    remaining = list(instance.customer_ids)
    routes: list[list[str]] = []
    while remaining:
        route = [depot]
        load = 0.0
        battery = vehicle.start_soc
        loc = depot
        inner_guard = 0
        stations_here = 0
        while remaining and inner_guard < 40:
            inner_guard += 1
            best = None
            best_d = float("inf")
            for cid in remaining:
                node = instance.node_map[cid]
                if load + node.demand > vehicle.capacity + 1e-9:
                    continue
                d = distance(instance.node_map[loc], node)
                e = energy_required(instance.node_map[loc], node, vehicle)
                if e <= battery + 1e-9 and d < best_d:
                    best, best_d = cid, d
            if best is not None:
                node = instance.node_map[best]
                battery -= energy_required(instance.node_map[loc], node, vehicle)
                load += node.demand
                route.append(best)
                loc = best
                remaining.remove(best)
                continue
            if stations_here >= 2:
                break
            chosen_station = None
            best_se = float("inf")
            for sid in instance.station_ids:
                if sid == loc:
                    continue
                e1 = energy_required(instance.node_map[loc], instance.node_map[sid], vehicle)
                if e1 <= battery + 1e-9 and e1 < best_se:
                    chosen_station, best_se = sid, e1
            if chosen_station is None:
                break
            route.append(chosen_station)
            loc = chosen_station
            battery = vehicle.battery_capacity
            stations_here += 1
        if len(route) == 1:
            cid = remaining.pop(0)
            route = [depot, cid]
        route.append(depot)
        routes.append(route)
    return CandidateSolution(routes, {"baseline": "greedy_nn"})


def dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_csv(path: Path, rows: list[dict], keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(keys)]
    for row in rows:
        lines.append(",".join(str(row.get(k, "")).replace(",", ";") for k in keys))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def style_ax(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def main() -> None:
    print("inventory and baselines ...", flush=True)
    started = time.monotonic()
    for folder in (MD, FIG, TAB, RAW):
        folder.mkdir(parents=True, exist_ok=True)

    instances = load_all()
    split = split_instances(instances)
    write_split_manifest(ROOT / "results" / "manifests" / "split.json", split)
    discovery, heldout = split["discovery"], split["heldout"]
    inventory = {
        "n_total": len(instances),
        "n_discovery": len(discovery),
        "n_heldout_rc2": len(heldout),
        "by_family_all": dict(Counter(str(i.metadata.get("family")) for i in instances)),
        "by_family_discovery": dict(Counter(str(i.metadata.get("family")) for i in discovery)),
        "by_scale_discovery": dict(Counter(str(i.metadata.get("scale")) for i in discovery)),
        "n_customers_hist": dict(Counter(len(i.customer_ids) for i in discovery)),
        "timestamp": datetime.now(UTC).isoformat(),
    }
    dump(RAW / "inventory.json", inventory)

    ollama = OllamaBackend()
    model_rows = []
    for profile in list_profiles():
        status = availability(profile, ollama)
        model_rows.append(
            {
                "model_id": profile.id,
                "model": profile.model,
                "status": status,
                "team_mode": "five_agent",
            }
        )
    dump(RAW / "models.json", model_rows)

    smoke = by_customer_count(discovery, [5])
    small10 = by_customer_count(discovery, [10])
    small15 = by_customer_count(discovery, [15])

    baseline_rows = []
    for instance in smoke + small10[:6] + small15[:4]:
        for name, builder in (("dedicated", dedicated_routes), ("greedy_nn", greedy_nn_with_stations)):
            report = evaluate_solution(instance, builder(instance))
            lit = SCHNEIDER_2014_SMALL_CPLEX.get(instance.instance_id)
            baseline_rows.append(
                {
                    "instance_id": instance.instance_id,
                    "family": instance.metadata.get("family"),
                    "n_customers": len(instance.customer_ids),
                    "baseline": name,
                    "feasible": report.feasible,
                    "vehicles": report.vehicles,
                    "distance": round(report.total_distance, 2),
                    "unserved": len(report.unserved),
                    "battery_violations": report.battery_violations,
                    "tw_violations": report.time_window_violations,
                    "literature_m": lit[0] if lit else "",
                    "literature_f": lit[1] if lit else "",
                    "held_out": instance.metadata.get("family") == "RC2",
                }
            )
    dump(RAW / "baselines.json", baseline_rows)
    write_csv(
        TAB / "baselines.csv",
        baseline_rows,
        [
            "instance_id",
            "family",
            "n_customers",
            "baseline",
            "feasible",
            "vehicles",
            "distance",
            "literature_m",
            "literature_f",
        ],
    )

    lit_small_rows = [
        {
            "instance_id": k,
            "cplex_m": v[0],
            "cplex_f": v[1],
            "held_out": k.lower().startswith("rc2"),
            "source": "Schneider et al. 2014 Table 3 (CPLEX)",
        }
        for k, v in SCHNEIDER_2014_SMALL_CPLEX.items()
    ]
    write_csv(TAB / "literature_small_cplex.csv", lit_small_rows, ["instance_id", "cplex_m", "cplex_f", "held_out", "source"])
    lit_large_rows = []
    for iid, (m, f) in SCHNEIDER_2014_LARGE_VNSTS.items():
        keskin = KESKIN_2016_ALNS.get(iid)
        lit_large_rows.append(
            {
                "instance_id": iid,
                "schneider2014_vnsts_m": m,
                "schneider2014_vnsts_f": f,
                "keskin2016_alns_m": keskin[0] if keskin else "",
                "keskin2016_alns_f": keskin[1] if keskin else "",
                "held_out": iid.lower().startswith("rc2"),
            }
        )
    write_csv(
        TAB / "literature_large.csv",
        lit_large_rows,
        [
            "instance_id",
            "schneider2014_vnsts_m",
            "schneider2014_vnsts_f",
            "keskin2016_alns_m",
            "keskin2016_alns_f",
            "held_out",
        ],
    )

    experiments = yaml.safe_load((ROOT / "configs" / "experiments.yaml").read_text(encoding="utf-8")) or {}
    model_ids = list((experiments.get("model_comparison") or {}).get("model_ids") or [])
    autolab_rows = []
    for model_id in model_ids:
        profile = resolve_profile(model_id)
        status = availability(profile, ollama)
        row = {
            "model_id": model_id,
            "model": profile.model,
            "team_mode": "five_agent",
            "status": status,
            "error": "",
            "wall_s": 0.0,
            "f0_ok": False,
            "bootstrap_feasible": False,
            "bootstrap_vehicles": "",
            "bootstrap_distance": "",
            "f1_feasible_rate": "",
            "f1_mean_vehicles": "",
            "solver_path": "",
        }
        if status != "installed":
            print(f"{SKIPPED_NOT_INSTALLED}: {profile.model}")
            autolab_rows.append(row)
            dump(RAW / f"autolab_{model_id}.json", row)
            continue
        t0 = time.monotonic()
        try:
            print(f"bootstrap {model_id} ...", flush=True)
            result = bootstrap_solver(
                ROOT / "workspace" / "model_benchmark" / model_id,
                make_backend(profile),
                model=profile.model,
                instance=smoke[0],
                temperatures=profile.temperatures,
            )
            row["wall_s"] = round(time.monotonic() - t0, 1)
            row["status"] = "ran"
            row["solver_path"] = result.get("path", "")
            row["bootstrap_feasible"] = bool(result["evaluation"]["feasible"])
            row["bootstrap_vehicles"] = result["evaluation"]["vehicles"]
            row["bootstrap_distance"] = result["evaluation"]["distance"]
            row["f0_ok"] = not result.get("f0_errors")
            row["activated"] = result.get("activated")
            row["critic"] = result.get("critic")
            solver_dir = Path(result["path"]) if result.get("path") else None
            if solver_dir and solver_dir.exists():
                f1 = evaluate_fidelity(
                    solver_dir,
                    smoke,
                    "F1",
                    seeds=[0],
                    limits=RunLimits(wall_clock_s=12.0),
                    max_instances=8,
                )
                row["f1"] = f1
                summary = f1.get("summary") or {}
                row["f1_feasible_rate"] = summary.get("feasible_rate")
                row["f1_mean_vehicles"] = summary.get("mean_vehicles")
                per = []
                for instance in smoke[:8]:
                    report = run_solver(solver_dir, instance, seed=0, limits=RunLimits(wall_clock_s=12.0))
                    lit = SCHNEIDER_2014_SMALL_CPLEX.get(instance.instance_id)
                    per.append(
                        {
                            "instance_id": instance.instance_id,
                            "feasible": report.feasible,
                            "vehicles": report.vehicles,
                            "distance": round(report.total_distance, 2),
                            "crashed": report.crashed,
                            "error": report.error[:240],
                            "literature_m": lit[0] if lit else "",
                            "literature_f": lit[1] if lit else "",
                        }
                    )
                row["per_instance_f1"] = per
            dump(RAW / f"autolab_{model_id}.json", row)
        except Exception as error:
            row["status"] = "failed"
            row["error"] = f"{error}\n{traceback.format_exc()[-1500:]}"
            row["wall_s"] = round(time.monotonic() - t0, 1)
            dump(RAW / f"autolab_{model_id}.json", row)
            print(f"FAILED {model_id}: {error}", flush=True)
        autolab_rows.append(row)

    dump(ROOT / "results" / "model_comparison" / "summary.json", autolab_rows)
    write_csv(
        TAB / "autolab_model_comparison.csv",
        autolab_rows,
        [
            "model_id",
            "model",
            "team_mode",
            "status",
            "wall_s",
            "f0_ok",
            "bootstrap_feasible",
            "bootstrap_vehicles",
            "bootstrap_distance",
            "f1_feasible_rate",
            "f1_mean_vehicles",
        ],
    )

    # Figures
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [r["model_id"] for r in model_rows]
    colors = ["#2a6f97" if r["status"] == "installed" else "#9b2226" for r in model_rows]
    ax.bar(labels, [1 if r["status"] == "installed" else 0 for r in model_rows], color=colors)
    style_ax(ax, "Configured comparison models (homogeneous 5-agent teams)", "Model profile", "Installed (1) / skipped (0)")
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
    ids = [r["instance_id"] for r in lit_small_rows if r["instance_id"].endswith("C5")]
    cplex_m = [SCHNEIDER_2014_SMALL_CPLEX[i][0] for i in ids]
    greedy = {r["instance_id"]: r for r in baseline_rows if r["baseline"] == "greedy_nn"}
    ded = {r["instance_id"]: r for r in baseline_rows if r["baseline"] == "dedicated"}
    g_m = [greedy[i]["vehicles"] if i in greedy else 0 for i in ids]
    d_m = [ded[i]["vehicles"] if i in ded else 0 for i in ids]
    x = range(len(ids))
    ax.bar([i - 0.25 for i in x], cplex_m, width=0.25, label="CPLEX 2014 (opt/UB)", color="#1d3557")
    ax.bar(list(x), g_m, width=0.25, label="Greedy NN baseline", color="#457b9d")
    ax.bar([i + 0.25 for i in x], d_m, width=0.25, label="Dedicated-route baseline", color="#a8dadc")
    ax.set_xticks(list(x))
    ax.set_xticklabels(ids, rotation=45, ha="right")
    style_ax(ax, "Vehicles on 5-customer instances vs Schneider 2014 CPLEX", "Instance", "Vehicles (lex primary)")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(FIG / "vehicles_c5_vs_cplex.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    names = [r["model_id"] for r in autolab_rows]
    rates = []
    for r in autolab_rows:
        v = r.get("f1_feasible_rate")
        rates.append(float(v) if v not in ("", None) else 0.0)
    ax.bar(names, rates, color="#2a6f97")
    style_ax(
        ax,
        "AutoLab generated-solver F1 feasible rate (5-customer discovery)",
        "Homogeneous 5-agent model",
        "Feasible rate",
    )
    ax.set_ylim(0, 1.05)
    fig.tight_layout()
    fig.savefig(FIG / "autolab_f1_feasible.png", dpi=160)
    plt.close(fig)

    dump(
        RAW / "campaign_meta.json",
        {
            "elapsed_s": round(time.monotonic() - started, 1),
            "n_models": len(autolab_rows),
            "smoke_instance": smoke[0].instance_id if smoke else None,
        },
    )
    print("done", round(time.monotonic() - started, 1), "s")


if __name__ == "__main__":
    main()
