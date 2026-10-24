"""v4 repair-policy gate. Historical v1 repair ranking is left unchanged.

A candidate counts as behavior-changing only when it selects a different
screened ALNS repair position for the same removed customer.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from evrptw_autolab.backbone.alns import repair_greedy
from evrptw_autolab.backbone.decision_features import insertion_features_v4
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import default_sources, wrap_expression
from evrptw_autolab.components.interpret import UnsafeComponent
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.bundle_selection import random_component_expression
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V4
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    RouteStopV2,
    SolutionV2,
    VehicleTypeV2,
)

MAX_LIVE_CALLS = 12


def fleet_spec() -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id="two_route_cost",
        family="hiermann",
        capabilities=CapabilityFlags(heterogeneous_fleet=True, capacity=True, euclidean_distances=True),
        nodes=(
            NodeV2("D", "depot", 0, 0, due_time=1000),
            NodeV2("A", "customer", 2, 2, demand=1, due_time=1000),
            NodeV2("B", "customer", -20, 0, demand=1, due_time=1000),
            NodeV2("C", "customer", 2, 0, demand=1, due_time=1000),
        ),
        vehicle_types=(
            VehicleTypeV2(
                "ICE",
                capacity=10,
                is_electric=False,
                is_conventional=True,
                velocity=1,
                fixed_cost=0,
                metadata={"fuel_consumption_rate": 10.0},
            ),
            VehicleTypeV2(
                "BEV",
                capacity=10,
                battery_capacity=100,
                consumption_rate=0.1,
                velocity=1,
                is_electric=True,
                fixed_cost=0,
            ),
        ),
        depot_ids=("D",),
        fleet_availability={"ICE": 1, "BEV": 1},
        metadata={"energy_prices": {"fossil-fuel": 1.0, "electricity": 1.0}},
    )


def _fleet_start() -> SolutionV2:
    return SolutionV2(
        routes=[
            [RouteStopV2("D", "ICE", "depot"), RouteStopV2("A", "ICE", "visit"), RouteStopV2("D", "ICE", "depot")],
            [RouteStopV2("D", "BEV", "depot"), RouteStopV2("B", "BEV", "visit"), RouteStopV2("D", "BEV", "depot")],
        ],
        vehicle_assignments=["ICE", "BEV"],
    )


def _host(solution: SolutionV2, node_id: str) -> str | None:
    for route in solution.routes:
        if any(stop.node_id == node_id for stop in route):
            return str(route[0].vehicle_type_id)
    return None


def gate1() -> dict[str, Any]:
    """Zero model calls. Energy cost must beat shortest detour on two open routes."""
    spec = fleet_spec()
    start = _fleet_start()
    distance = _real_rank_changed("delta_distance")
    energy = _real_rank_changed("incremental_energy_cost")
    points = [
        insertion_features_v4(spec, start.routes[0], 1, "C", spec.vehicle_types[0]),
        insertion_features_v4(spec, start.routes[1], 1, "C", spec.vehicle_types[1]),
    ]
    ok = bool(
        distance.get("loaded")
        and energy.get("loaded")
        and distance.get("vehicle") == "ICE"
        and energy.get("vehicle") == "BEV"
        and distance.get("changed_from_objective") is True
        and energy.get("changed_from_objective") is False
        and energy.get("feasible")
        and distance.get("feasible")
        and tuple(energy["objective_key"]) < tuple(distance["objective_key"])
        and points[0]["incremental_energy_cost"] != points[1]["incremental_energy_cost"]
    )
    return {
        "ok": ok,
        "llm_calls": 0,
        "schema": FEATURE_SCHEMA_V4,
        "distance_policy": distance,
        "energy_policy": energy,
        "classical_objective": distance.get("objective_key"),
        "energy_objective": energy.get("objective_key"),
        "energy_costs": [points[0]["incremental_energy_cost"], points[1]["incremental_energy_cost"]],
    }


def _real_rank_changed(expression: str) -> dict[str, Any]:
    spec = fleet_spec()
    start = _fleet_start()
    sources = default_sources(FEATURE_SCHEMA_V4)
    try:
        sources["insertion_score"] = wrap_expression("insertion_score", expression, FEATURE_SCHEMA_V4)
    except (UnsafeComponent, ValueError, SyntaxError) as error:
        return {"loaded": False, "error": str(error), "changed": False}
    bundle, errors = load_bundle(sources, feature_schema=FEATURE_SCHEMA_V4)
    if errors:
        return {"loaded": False, "error": errors, "changed": False}
    ranked = repair_greedy(spec, start, [("C",)], random.Random(0), policy=bundle)
    report = evaluate(spec, ranked)
    vehicle = _host(ranked, "C")
    trace = bundle.decision_trace[0] if bundle.decision_trace else {}
    return {
        "loaded": True,
        "changed": vehicle != "ICE",
        "changed_from_objective": bool(trace.get("changed_from_objective")),
        "feasible": bool(report.feasible),
        "vehicle": vehicle,
        "objective_key": [float(value) for value in report.objective_key] if report.feasible else None,
        "source": sources["insertion_score"],
    }


def run_live(backend: Any, model: str, directory: Path) -> dict[str, Any]:
    """At most 12 calls. A no-op on the real repair position is not evaluated further."""
    from evrptw_autolab.experiments.generational_compare import _ollama_digest
    from evrptw_autolab.experiments.matched_pilot import (
        _architect_text,
        _propose_component,
        _propose_unified_component,
    )
    from evrptw_autolab.llm.usage import UsageCollector

    directory.mkdir(parents=True, exist_ok=True)
    proven = gate1()
    if not proven["ok"]:
        payload = {"status": "ENGINEERING_BLOCKED", "gate1": proven, "llm_calls": 0}
        (directory / "live_two_route.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
    collector = UsageCollector(max_calls=MAX_LIVE_CALLS, max_tokens=12000)
    context = (
        "Hiermann two-route repair. Native cost is fixed cost plus fossil fuel plus electricity. "
        "The shortest detour is the ICE and has the higher incremental_energy_cost. "
        "The BEV detour is longer and cheaper. "
        "A score that selects the same vehicle as delta_distance is rejected."
    )
    architect = _architect_text(collector, backend, model, context=context)
    code, row, _schema = _propose_component(
        collector,
        backend,
        model,
        "insertion_score",
        context=str(architect.get("hypothesis") or context),
        schema=FEATURE_SCHEMA_V4,
    )
    multi = _real_rank_changed(_expression_line(code))
    critic_called = False
    critic_effect = None
    if multi.get("changed") and not _better(multi, proven):
        from evrptw_autolab.experiments.matched_pilot import _critic

        critic_called = True
        reason = _critic(collector, backend, model, [{"repair": multi}], None)
        revised_code, revised_row, _schema = _propose_component(
            collector,
            backend,
            model,
            "insertion_score",
            context=(
                f"{context}\nCritic: {reason}\n"
                f"The previous expression selected {multi.get('vehicle')} and did not lower the native cost."
            ),
            schema=FEATURE_SCHEMA_V4,
        )
        revised = _real_rank_changed(_expression_line(revised_code))
        critic_effect = revised.get("vehicle") != multi.get("vehicle")
        multi = {
            **multi,
            "critic_reason": reason,
            "revised": revised,
            "revised_attribution": revised_row,
            "critic_effect": critic_effect,
        }
    single_code, single_row, _schema = _propose_unified_component(
        collector, backend, model, "insertion_score", context=context, schema=FEATURE_SCHEMA_V4
    )
    single = _real_rank_changed(_expression_line(single_code))
    rng = random.Random(7)
    random_row = _real_rank_changed(random_component_expression("insertion_score", rng, FEATURE_SCHEMA_V4))
    revised_repair = multi.get("revised")
    if not isinstance(revised_repair, dict):
        revised_repair = {}
    changed = bool(multi.get("changed") or revised_repair.get("changed") or single.get("changed"))
    improved = _better(multi, proven) or _better(revised_repair, proven) or _better(single, proven)
    status = "LLM_POLICY_BEHAVIOR_CHANGED" if changed else "REAL_POLICY_CONTROL_VALIDATED"
    payload = {
        "status": status,
        "schema": FEATURE_SCHEMA_V4,
        "model": model,
        "model_digest": _ollama_digest(model),
        "llm_calls": collector.logical_calls,
        "llm_tokens": collector.total_tokens,
        "architect": architect,
        "multi_agent": {"attribution": row, "repair": multi},
        "single_agent": {"attribution": single_row, "repair": single},
        "random": random_row,
        "critic_called": critic_called,
        "critic_effect": critic_effect,
        "gate1": proven,
        "objective_improved": improved,
        "confirmation_run": False,
        "note": "objective_improved here is the four-node repair only. It is not a discovery result.",
    }
    (directory / "live_two_route.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _expression_line(source: str) -> str:
    for line in source.splitlines():
        if "return " in line:
            return line.split("return ", 1)[1].strip()
    return source.strip()


def _better(row: dict[str, Any], proven: dict[str, Any]) -> bool:
    key = row.get("objective_key")
    base = proven.get("classical_objective")
    return bool(key and base and tuple(key) < tuple(base))


def write_gate1(directory: Path) -> dict[str, Any]:
    payload = gate1()
    payload["status"] = "REAL_POLICY_CONTROL_VALIDATED" if payload["ok"] else "ENGINEERING_BLOCKED"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "gate1_two_route.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
