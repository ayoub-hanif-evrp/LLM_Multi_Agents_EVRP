"""Panel evaluation, lex accept, experimental charging repair branch."""
from __future__ import annotations

import ast
import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evrptw_autolab.evaluation.fidelity import (
    by_customer_count,
    load_all,
    partition_of,
    split_instances,
)
from evrptw_autolab.problem.types import EVRPTWInstance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.sandbox.static_scan import scan_source
from evrptw_autolab.slm_evo.types import PANEL_IDS, PanelMetrics


@dataclass
class CandidateValidation:
    ok: bool
    failure_class: str = ""
    reason: str = ""


def code_hash(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def collect_union_node_ids(instances: list[EVRPTWInstance]) -> set[str]:
    found: set[str] = set()
    for instance in instances:
        found.add(instance.depot_id)
        found.update(instance.customer_ids)
        found.update(instance.station_ids)
    return found


def find_hardcoded_node_ids(
    source: str,
    probe: EVRPTWInstance | None = None,
    known_ids: set[str] | None = None,
) -> list[str]:
    ids = set(known_ids or [])
    if probe is not None:
        ids.update(collect_union_node_ids([probe]))
    if not ids:
        return []
    found: list[str] = []

    def _keep(token: str) -> None:
        if token in ids and token not in found:
            found.append(token)

    try:
        tree = ast.parse(source)
    except SyntaxError:
        for token in re.findall(r"""['\"]([^'\"]+)['\"]""", source):
            _keep(token)
        return found
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            _keep(node.value)
    return found


def validate_candidate(
    source: str,
    *,
    probe: EVRPTWInstance,
    limits: RunLimits | None = None,
    known_ids: set[str] | None = None,
) -> CandidateValidation:
    limits = limits or RunLimits(wall_clock_s=20.0)
    try:
        ast.parse(source)
    except SyntaxError as error:
        return CandidateValidation(False, "SYNTAX", str(error))
    hard = find_hardcoded_node_ids(source, probe, known_ids=known_ids)
    if hard:
        return CandidateValidation(False, "HARDCODED_INSTANCE_IDENTIFIER", ",".join(hard))
    scan_errors = scan_source(source)
    if scan_errors:
        return CandidateValidation(False, "STATIC", scan_errors[0])
    if "def solve" not in source:
        return CandidateValidation(False, "CONTRACT", "missing solve")
    with tempfile.TemporaryDirectory() as tmp:
        solver_dir = Path(tmp)
        (solver_dir / "solver.py").write_text(source, encoding="utf-8")
        report = run_solver(solver_dir, probe, seed=0, limits=limits)
    if report.crashed or not report.parse_ok:
        detail = str(report.error or (report.first_fault or {}).get("detail") or "runtime failure")
        return CandidateValidation(False, "RUNTIME", detail[:300])
    return CandidateValidation(True, "", "ok")


def panel_instances(data_root: Path | None = None) -> list[EVRPTWInstance]:
    discovery = split_instances(load_all(data_root))["discovery"]
    small = by_customer_count(discovery, [5])
    by_id = {i.instance_id: i for i in small}
    return [by_id[w] for w in PANEL_IDS if w in by_id]


def all_c5_instances(data_root: Path | None = None) -> list[EVRPTWInstance]:
    """Every 5-customer instance except the held-out RC2 family."""
    selected = [
        instance
        for instance in load_all(data_root)
        if len(instance.customer_ids) == 5 and partition_of(instance) != "heldout"
    ]
    selected.sort(key=lambda instance: instance.instance_id)
    return selected


def instances_by_customer_count(
    n_customers: int,
    data_root: Path | None = None,
) -> list[EVRPTWInstance]:
    discovery = split_instances(load_all(data_root))["discovery"]
    return by_customer_count(discovery, [n_customers])


def literature_scale_instances(
    *,
    customer_count: int,
    data_root: Path | None = None,
) -> list[EVRPTWInstance]:
    """Instances present in Schneider literature table at the given size."""
    from evrptw_autolab.evaluation.literature import SCHNEIDER_2014_SMALL_CPLEX

    suffix = f"C{customer_count}"
    wanted = {iid for iid in SCHNEIDER_2014_SMALL_CPLEX if iid.endswith(suffix)}
    by_id = {i.instance_id: i for i in instances_by_customer_count(customer_count, data_root)}
    return [by_id[iid] for iid in sorted(wanted) if iid in by_id]


def known_ids_for_panel(data_root: Path | None = None) -> set[str]:
    return collect_union_node_ids(panel_instances(data_root) + all_c5_instances(data_root))


def evaluate_panel(
    solver_dir: Path,
    instances: list[EVRPTWInstance],
    *,
    limits: RunLimits | None = None,
) -> tuple[PanelMetrics, list[Any]]:
    limits = limits or RunLimits(wall_clock_s=20.0)
    reports = []
    by: dict[str, dict[str, Any]] = {}
    ok = 0
    vehicles = 0
    distance = 0.0
    primary_fault = ""
    for inst in instances:
        r = run_solver(solver_dir, inst, seed=0, limits=limits)
        reports.append(r)
        if r.feasible and not r.crashed and r.parse_ok and not r.timed_out:
            ok += 1
            vehicles += int(r.vehicles or 0)
            distance += float(r.total_distance or 0.0)
            by[inst.instance_id] = {
                "ok": True,
                "vehicles": int(r.vehicles or 0),
                "distance": float(r.total_distance or 0.0),
            }
        else:
            fam = str((r.first_fault or {}).get("family") or r.error or "fail")[:80]
            if not primary_fault:
                primary_fault = fam
            by[inst.instance_id] = {"ok": False, "fault": fam, "vehicles": int(r.vehicles or 0)}
    return (
        PanelMetrics(
            feasible=ok,
            total=len(instances),
            vehicles_sum=vehicles,
            distance_sum=round(distance, 4),
            by_instance=by,
            primary_fault=primary_fault,
        ),
        reports,
    )


def validate_source(
    source: str,
    *,
    probe: EVRPTWInstance,
    known_ids: set[str],
    limits: RunLimits | None = None,
) -> tuple[bool, str]:
    limits = limits or RunLimits(wall_clock_s=20.0)
    hard = find_hardcoded_node_ids(source, probe, known_ids=known_ids)
    if hard:
        return False, f"HARDCODED_INSTANCE_IDENTIFIER: {hard}"
    result = validate_candidate(source, probe=probe, limits=limits, known_ids=known_ids)
    if not result.ok:
        return False, f"{result.failure_class}:{result.reason}"[:400]
    return True, "ok"


def lex_better_panel(parent: PanelMetrics, child: PanelMetrics) -> bool:
    if not child.fully_feasible:
        return False
    if not parent.fully_feasible:
        return True
    if child.vehicles_sum < parent.vehicles_sum:
        return True
    if child.vehicles_sum == parent.vehicles_sum and child.distance_sum + 1e-9 < parent.distance_sum:
        return True
    return False


def vehicle_reduction_on_any(parent: PanelMetrics, child_partial: PanelMetrics) -> list[str]:
    """Instances where child reports fewer vehicles even if infeasible elsewhere."""
    hits = []
    for iid, crow in (child_partial.by_instance or {}).items():
        prow = (parent.by_instance or {}).get(iid) or {}
        if crow.get("ok") and prow.get("ok"):
            if int(crow.get("vehicles") or 0) < int(prow.get("vehicles") or 0):
                hits.append(iid)
        elif int(crow.get("vehicles") or 0) and int(prow.get("vehicles") or 99) > int(
            crow.get("vehicles") or 0
        ):
            # child may be infeasible but still report a shorter fleet in partial eval
            if int(crow.get("vehicles") or 0) < int(prow.get("vehicles") or 99):
                hits.append(iid)
    return hits


def experimental_battery_or_window(metrics: PanelMetrics) -> bool:
    fault = (metrics.primary_fault or "").upper()
    return any(x in fault for x in ("BATTERY", "WINDOW", "CHARGE_POLICY"))


def write_solver(dir_path: Path, source: str) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / "solver.py"
    path.write_text(source, encoding="utf-8")
    return path


def source_hash(source: str) -> str:
    return code_hash(source)[:16]


def milestone_instances(metrics: PanelMetrics, *, threshold: int = 4) -> list[str]:
    hits = []
    for iid, row in (metrics.by_instance or {}).items():
        if row.get("ok") and int(row.get("vehicles") or 99) <= threshold:
            hits.append(iid)
    return hits
