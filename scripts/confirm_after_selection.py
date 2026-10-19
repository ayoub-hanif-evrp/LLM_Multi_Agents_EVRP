"""Confirm seed-7 selections, then run the untouched Schneider confirmation ids.

The deployment decision is written before any confirmation instance is loaded.
Confirmation ids are c206C5, r202C5, and r203C5: Schneider confirmation, not
the development panel, and not the RC2 held-out list.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.bundle_selection import conservative_decision
from evrptw_autolab.experiments.family_gate import gate_panel
from evrptw_autolab.experiments.matched_pilot import KINDS, PanelItem, _evaluate, _pairs
from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

ROOT = Path(__file__).resolve().parents[1]
CONFIRM_IDS = ("c206C5", "r202C5", "r203C5")
FREEZE = ROOT / "results" / "v2" / "baselines" / "classical_frozen_c2de5a0"
OUT = ROOT / "results" / "v2" / "paper" / "confirmation_schneider.json"


def _latest_generational() -> Path:
    campaigns = ROOT / "results" / "v2" / "campaigns"
    matches = sorted(campaigns.glob("generational_qwen_*/generational.json"))
    if not matches:
        raise SystemExit("no live generational artifact")
    return matches[-1]


def _gate() -> list[PanelItem]:
    return [
        PanelItem(
            item.family,
            item.instance_id,
            item.loader(item.path),
            float(item.time_limit_s),
            int(item.alns_iterations),
        )
        for item in gate_panel()
    ]


def _classical_freeze(seed: int) -> list[dict[str, Any]]:
    rows = []
    for path in FREEZE.glob("run_*/pilot.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload["rows"]:
            if int(row["seed"]) != seed:
                continue
            if row["instance_id"] not in {item.instance_id for item in gate_panel()}:
                continue
            rows.append(
                {
                    "instance_id": row["instance_id"],
                    "seed": seed,
                    "feasible": bool(row["feasible"]),
                    "objective_key": [float(v) for v in row["objective_key"]],
                }
            )
    return rows


def _candidate(payload: dict[str, Any], arm: str, candidate_id: str) -> dict[str, Any]:
    for item in payload[arm]:
        if item["candidate_id"] == candidate_id:
            return item
    raise SystemExit(f"missing {arm} {candidate_id}")


def _solve_confirmation(policy: str, sources: dict[str, str] | None, schema: str | None) -> list[dict[str, Any]]:
    bundle = None
    if sources is not None:
        typed = {kind: sources[kind] for kind in sources}
        owners = {kind: "confirmation" for kind in typed}
        bundle, errors = load_bundle(typed, owners, feature_schema=schema)
        if errors:
            raise SystemExit(f"bundle load failed: {errors}")
    rows = []
    for instance_id in CONFIRM_IDS:
        spec = load_schneider_v2(ROOT / "dataset" / "schneider" / "raw_instances" / f"{instance_id}.txt")
        for seed in (7, 11, 22):
            solution = solve_classical(
                spec,
                seed=seed,
                time_limit_s=8.0,
                alns_iterations=80,
                policy=bundle,
            )
            report = evaluate(spec, solution)
            fault = "" if report.first_fault is None else f"{report.first_fault.family}: {report.first_fault.detail}"
            rows.append(
                {
                    "policy": policy,
                    "instance_id": instance_id,
                    "seed": seed,
                    "time_limit_s": 8.0,
                    "alns_iterations": 80,
                    "feasible": bool(report.feasible),
                    "objective_key": [float(v) for v in report.objective_key] if report.feasible else None,
                    "vehicles": report.vehicles,
                    "distance": report.total_distance,
                    "first_fault": fault,
                    "completed_within_budget": solution.metadata.get("completed_within_budget"),
                    "runtime_s": solution.metadata.get("runtime_s"),
                }
            )
            print(policy, instance_id, seed, rows[-1]["feasible"], rows[-1]["objective_key"], flush=True)
    return rows


def main() -> None:
    split = json.loads((ROOT / "results" / "manifests" / "split.json").read_text(encoding="utf-8"))
    panel_ids = {item.instance_id for item in gate_panel()}
    development = json.loads(
        (ROOT / "results" / "v2" / "manifests" / "development_panel.json").read_text(encoding="utf-8")
    )
    development_ids = {row["instance_id"] for row in development["instances"]}
    held = set(split["heldout_ids"])
    confirmation = set(split["confirmation_ids"])
    for instance_id in CONFIRM_IDS:
        if (
            instance_id not in confirmation
            or instance_id in held
            or instance_id in development_ids
            or instance_id in panel_ids
        ):
            raise SystemExit(f"{instance_id} is not an untouched confirmation id")
    source = _latest_generational()
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("fake"):
        raise SystemExit("refusing a FakeBackend artifact")
    panel = _gate()
    decisions = []
    promoted: list[dict[str, Any]] = []
    for arm, candidate_id in payload["selected"].items():
        if not candidate_id:
            decisions.append({"arm": arm, "candidate_id": None, "three_seed_accepted": False, "reason": "not_selected_on_seed_7"})
            continue
        item = _candidate(payload, arm, str(candidate_id))
        sources = {kind: str(item["sources"][kind]) for kind in KINDS}
        schema = str(item["feature_schema"])
        extra_pairs = []
        seed_rows = []
        for seed in (11, 22):
            measured = _evaluate(
                arm,
                str(candidate_id),
                sources,
                schema,
                panel,
                seed,
            )
            seed_rows.append({"seed": seed, "rows": measured})
            extra_pairs.extend(_pairs(_classical_freeze(seed), measured))
        combined = _pairs(payload["classical"], item["rows"]) + extra_pairs
        decision = conservative_decision(combined)
        record = {
            "arm": arm,
            "candidate_id": candidate_id,
            "three_seed_accepted": bool(decision["accepted"]),
            "reason": decision["reason"],
            "wins": decision["wins"],
            "losses": decision["losses"],
            "seed_rows": seed_rows,
        }
        decisions.append(record)
        if decision["accepted"]:
            promoted.append({"policy": f"{arm}:{candidate_id}", "sources": sources, "schema": schema})
    decision_path = OUT.with_name("confirmation_decision.json")
    decision_path.write_text(
        json.dumps(
            {
                "source": str(source),
                "rule": "conservative on gate seeds 7, 11, and 22",
                "decisions": [
                    {key: value for key, value in row.items() if key != "seed_rows"} for row in decisions
                ],
                "promoted": [row["policy"] for row in promoted],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("decision written", decision_path, [row["policy"] for row in promoted], flush=True)
    rows = _solve_confirmation("classical_default", None, None)
    for policy in promoted:
        rows.extend(_solve_confirmation(policy["policy"], policy["sources"], policy["schema"]))
    feasible = sum(1 for row in rows if row["feasible"] and row["policy"] == "classical_default")
    OUT.write_text(
        json.dumps(
            {
                "protocol": "untouched_schneider_confirmation_c5",
                "instance_ids": list(CONFIRM_IDS),
                "decision_file": str(decision_path),
                "promoted_policies": [row["policy"] for row in promoted],
                "classical_feasible": feasible,
                "classical_n": sum(1 for row in rows if row["policy"] == "classical_default"),
                "rows": rows,
                "seed_confirmation": decisions,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
