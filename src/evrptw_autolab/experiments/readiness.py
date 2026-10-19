"""Engineering checks that fail on the known regression classes.

These checks read frozen artifacts and the declared protocol. They do not
re-solve instances and they do not treat an infeasible objective as a pass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evrptw_autolab.baselines.classical_pilot import development_panel
from evrptw_autolab.experiments.evolution_pilot import pilot_protocol
from evrptw_autolab.experiments.fair_budget import SEARCH_CANDIDATES, solver_passes
from evrptw_autolab.experiments.family_gate import BASELINE_PATH, load_baseline

ROOT = Path(__file__).resolve().parents[3]


def engineering_checks(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    failures: list[dict[str, str]] = []
    notes: list[str] = []
    baseline = load_baseline(base / "results" / "v2" / "diagnostics" / "family_development_gate" / "baseline.json")
    rows = {str(row["instance_id"]): row for row in baseline["rows"]}
    hier = rows.get("c101_21")
    if hier is None or not bool(hier.get("feasible")) or hier.get("completed_within_budget") is not True:
        failures.append(
            {
                "check": "hiermann_gate",
                "class": "correctness",
                "detail": "frozen Hiermann c101_21 row is missing, infeasible, or over budget",
            }
        )
    if "tc0c10s3cf1" in rows:
        failures.append(
            {
                "check": "montoya_duplicate",
                "class": "leakage",
                "detail": "tc0c10s3cf1 is a duplicate and must not sit in the frozen gate",
            }
        )
    for row in baseline["rows"]:
        if bool(row.get("feasible")) and not row.get("objective_key"):
            failures.append(
                {
                    "check": "objective_key",
                    "class": "correctness",
                    "detail": f"{row.get('instance_id')} is feasible without an objective key",
                }
            )
    protocol = pilot_protocol()
    expected = solver_passes(len(protocol["instances"]), candidates=SEARCH_CANDIDATES)
    if protocol["solver_passes"] != expected:
        failures.append(
            {
                "check": "search_budgets",
                "class": "fairness",
                "detail": f"protocol passes {protocol['solver_passes']} != {expected}",
            }
        )
    if protocol["status"] != "not_started":
        notes.append("pilot status is no longer not_started; confirm a real run exists before citing it")
    split_path = base / "results" / "manifests" / "split.json"
    if not split_path.exists():
        failures.append(
            {
                "check": "split_manifest",
                "class": "provenance",
                "detail": "Schneider split manifest is missing",
            }
        )
    else:
        split = json.loads(split_path.read_text(encoding="utf-8"))
        held = set(split.get("heldout_ids") or [])
        panel_ids = {item.instance_id for item in development_panel(base)}
        leaked = sorted(panel_ids & held)
        if leaked:
            failures.append(
                {
                    "check": "heldout_leakage",
                    "class": "leakage",
                    "detail": f"development panel contains held-out ids {leaked}",
                }
            )
        confirmation = set(split.get("confirmation_ids") or [])
        overlap = sorted(panel_ids & confirmation)
        if overlap:
            notes.append(
                "Schneider confirmation ids also appear in the development panel: " + ", ".join(overlap)
            )
    confirmation_path = (
        base / "results" / "v2" / "diagnostics" / "backbone_ablation" / "montoya_confirmation.json"
    )
    if not confirmation_path.exists():
        failures.append(
            {
                "check": "montoya_confirmation",
                "class": "provenance",
                "detail": "seed 11/22 charging confirmation file is missing",
            }
        )
    if not BASELINE_PATH.exists():
        failures.append(
            {
                "check": "baseline_path",
                "class": "provenance",
                "detail": "family development gate baseline is missing",
            }
        )
    expanded_path = base / "results" / "v2" / "diagnostics" / "family_development_gate" / "expanded_panel.json"
    if not expanded_path.exists():
        failures.append(
            {
                "check": "expanded_panel",
                "class": "provenance",
                "detail": "expanded development panel measurement is missing",
            }
        )
    else:
        expanded = json.loads(expanded_path.read_text(encoding="utf-8"))
        independent = expanded.get("independent_rows") or []
        ids = {str(row.get("instance_id")) for row in independent}
        if "tc0c10s3cf1" in ids:
            failures.append(
                {
                    "check": "expanded_duplicate",
                    "class": "leakage",
                    "detail": "the duplicate Montoya file is counted as an independent row",
                }
            )
        n10 = [row for row in independent if row.get("instance_id") == "10-N10"]
        if not n10 or any(row.get("feasible") is True for row in n10):
            failures.append(
                {
                    "check": "bezzi_10n10_history",
                    "class": "provenance",
                    "detail": "the historical expanded panel must keep the infeasible 10-N10 rows",
                }
            )
        pack_path = base / "results" / "v2" / "diagnostics" / "bezzi_pack" / "summary.json"
        if not pack_path.exists():
            failures.append(
                {
                    "check": "bezzi_10n10_repair",
                    "class": "correctness",
                    "detail": "the 10-N10 fleet-pack measurement is missing",
                }
            )
        else:
            packed = json.loads(pack_path.read_text(encoding="utf-8"))
            repaired = [
                row
                for row in packed.get("rows") or []
                if row.get("instance_id") == "10-N10" and int(row.get("seed") or -1) in {7, 11, 22}
            ]
            if len(repaired) != 3 or any(not row.get("feasible") or not row.get("completed_within_budget") for row in repaired):
                failures.append(
                    {
                        "check": "bezzi_10n10_repair",
                        "class": "correctness",
                        "detail": "10-N10 seeds 7, 11, and 22 must be feasible inside the 12s budget",
                    }
                )
            c101 = [
                row
                for row in packed.get("rows") or []
                if row.get("instance_id") == "C101-5" and int(row.get("seed") or -1) == 7
            ]
            if len(c101) != 1 or c101[0].get("objective_key") != [227.0] or not c101[0].get("feasible"):
                failures.append(
                    {
                        "check": "bezzi_c101_regression",
                        "class": "performance",
                        "detail": "C101-5 seed 7 must stay feasible at recharge cost 227",
                    }
                )
        frozen_seed7 = {
            (str(row["family"]), str(row["instance_id"])): [float(v) for v in row["objective_key"]]
            for row in baseline["rows"]
            if int(row["seed"]) == 7 and bool(row.get("feasible"))
        }
        for row in independent:
            key = (str(row.get("family")), str(row.get("instance_id")))
            if int(row.get("seed") or -1) != 7 or key not in frozen_seed7:
                continue
            measured = [float(v) for v in row.get("objective_key") or []]
            if measured != frozen_seed7[key]:
                failures.append(
                    {
                        "check": "expanded_gate_mismatch",
                        "class": "performance",
                        "detail": f"{key} seed 7 key {measured} does not match the frozen gate {frozen_seed7[key]}",
                    }
                )
    return {"ok": not failures, "failures": failures, "notes": notes}
