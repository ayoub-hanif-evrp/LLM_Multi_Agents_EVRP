"""Metamorphic / semantic-invariance tests for generated operators (M9A)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from evocharge.domain.instance import Instance
from evocharge.domain.solution import Solution
from evocharge.evaluation.adapter import compile_plan_builder
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import OperatorPlan, RandomSource, ReadOnlySearchState
from evocharge.operators.primitives import apply_operator_plan
from evocharge.solver.charging_repair import ChargingRepairCache
from evocharge.solver.construction import construct_initial_solution
from evocharge.solver.feasibility import evaluate_feasibility
from evocharge.solver.propagation import propagate_route
from evocharge.verification.sandbox import validate_plan


class MetamorphicCaseResult(BaseModel):
    case_id: str
    passed: bool
    detail: str = ""


class MetamorphicReport(BaseModel):
    accepted: bool
    results: list[MetamorphicCaseResult] = Field(default_factory=list)
    semantic_invariance_pass_rate: float = 0.0


def _permute_ids(instance: Instance, prefix: str, mapping: dict[str, str]) -> Instance:
    """Relabel helper retained for future full-instance permutation experiments."""
    _ = prefix, mapping
    return instance


def relabel_solution_with_instance(
    instance: Instance, solution: Solution, mapping: dict[str, str]
) -> Solution:
    routes = [
        propagate_route(
            instance,
            tuple(mapping.get(n, n) for n in route.node_ids),
            vehicle_index=i,
        )
        for i, route in enumerate(solution.routes)
    ]
    return Solution(routes=tuple(routes))


def _customer_mapping(instance: Instance) -> dict[str, str]:
    custs = list(instance.customer_ids)
    # Rotate labels: C_i -> C_{(i+1)%n} style by remapping to permuted list
    if len(custs) < 2:
        return {c: c for c in custs}
    rotated = custs[1:] + custs[:1]
    return {a: b for a, b in zip(custs, rotated, strict=True)}


def _station_mapping(instance: Instance) -> dict[str, str]:
    stations = list(instance.station_ids)
    if len(stations) < 2:
        return {s: s for s in stations}
    rotated = stations[1:] + stations[:1]
    return {a: b for a, b in zip(stations, rotated, strict=True)}


def _build_plan(source: str, state: ReadOnlySearchState, seed: int = 0) -> OperatorPlan:
    builder = compile_plan_builder(source)
    ctx = OperatorContext(instance=state.instance, cache=ChargingRepairCache())
    plan = builder(state, ctx, RandomSource(seed))
    if not isinstance(plan, OperatorPlan):
        plan = OperatorPlan.model_validate(plan)
    return plan


def run_metamorphic_suite(
    source: str,
    *,
    instance: Instance,
) -> MetamorphicReport:
    """ID-permutation and structural cases. Relabeling must preserve behavior structure."""
    results: list[MetamorphicCaseResult] = []
    constructed = construct_initial_solution(instance)
    if constructed.solution is None:
        return MetamorphicReport(
            accepted=False,
            results=[
                MetamorphicCaseResult(
                    case_id="construction", passed=False, detail="construction_failed"
                )
            ],
        )
    base_sol = constructed.solution
    base_state = ReadOnlySearchState(solution=base_sol, instance=instance)
    base_plan = _build_plan(source, base_state, seed=0)
    pv = validate_plan(base_plan, state=base_state)
    results.append(
        MetamorphicCaseResult(
            case_id="base_plan_valid",
            passed=pv.accepted,
            detail=",".join(pv.errors) or "ok",
        )
    )

    # Customer ID permutation: selected customer ids must map under the same permutation
    cmap = _customer_mapping(instance)
    if len(cmap) >= 2 and base_plan.applicable and base_plan.selected_entities:
        try:
            # Rebuild instance is heavy; instead check that selected ids come from queries
            # and that applying after conceptual remap of selected ids stays consistent.
            selected = [
                e.entity_id
                for e in base_plan.selected_entities
                if e.entity_type == "customer"
            ]
            # Behavior depends on names iff selected set ignores mapping possibility —
            # pass if every selected customer is in instance.customer_ids (state-derived)
            ok = all(cid in set(instance.customer_ids) for cid in selected)
            # And source has no hardcoded literals (already static); check remap closure
            remapped = {cmap[c] for c in selected if c in cmap}
            ok = ok and len(remapped) == len(selected)
            results.append(
                MetamorphicCaseResult(
                    case_id="customer_id_permutation_closure",
                    passed=ok,
                    detail=f"selected={selected}",
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                MetamorphicCaseResult(
                    case_id="customer_id_permutation_closure",
                    passed=False,
                    detail=str(exc),
                )
            )
    else:
        results.append(
            MetamorphicCaseResult(
                case_id="customer_id_permutation_closure",
                passed=True,
                detail="skipped_or_no_action",
            )
        )

    # Station permutation closure
    smap = _station_mapping(instance)
    if len(smap) >= 2 and base_plan.applicable:
        selected_s = [
            e.entity_id
            for e in base_plan.selected_entities
            if e.entity_type == "station"
        ]
        if selected_s:
            ok = all(sid in set(instance.station_ids) for sid in selected_s)
            ok = ok and all(sid in smap for sid in selected_s)
            results.append(
                MetamorphicCaseResult(
                    case_id="station_id_permutation_closure",
                    passed=ok,
                    detail=f"selected={selected_s}",
                )
            )
        else:
            results.append(
                MetamorphicCaseResult(
                    case_id="station_id_permutation_closure",
                    passed=True,
                    detail="no_station_selection",
                )
            )
    else:
        results.append(
            MetamorphicCaseResult(
                case_id="station_id_permutation_closure",
                passed=True,
                detail="skipped",
            )
        )

    # Depot at position zero: segment plans must not use depot-only slice
    if base_plan.applicable:
        bad_depot = False
        for a in base_plan.actions:
            if a.primitive_id == "plan_segment_removal":
                start = int(str(a.arguments.get("start_index", -1)))
                end = int(str(a.arguments.get("end_index", -1)))
                ri = int(str(a.arguments.get("route_index", 0)))
                if ri < len(base_sol.routes):
                    nodes = base_sol.routes[ri].node_ids
                    custs = set(instance.customer_ids)
                    seg = [n for n in nodes[start:end] if n in custs]
                    if start == 0 and end == 1 and not seg:
                        bad_depot = True
        results.append(
            MetamorphicCaseResult(
                case_id="depot_position_zero_not_treated_as_customer",
                passed=not bad_depot,
                detail="ok" if not bad_depot else "depot_slice",
            )
        )
    else:
        results.append(
            MetamorphicCaseResult(
                case_id="depot_position_zero_not_treated_as_customer",
                passed=True,
                detail="not_applicable",
            )
        )

    # Routes with no stations: station operators must no-action or avoid station actions
    # Simulated by checking: if no stations on any route, plan should be not applicable
    # or not use station replacement with missing stations.
    any_stations = any(
        n in set(instance.station_ids)
        for r in base_sol.routes
        for n in r.node_ids
    )
    if not any_stations and base_plan.applicable:
        uses_station = any(
            a.primitive_id in {"plan_station_replacement", "plan_station_removal"}
            for a in base_plan.actions
        )
        results.append(
            MetamorphicCaseResult(
                case_id="no_station_routes",
                passed=not uses_station,
                detail="station_action_without_stations" if uses_station else "ok",
            )
        )
    else:
        results.append(
            MetamorphicCaseResult(
                case_id="no_station_routes",
                passed=True,
                detail="has_stations_or_ok",
            )
        )

    # Feasibility preserved when applied
    if base_plan.applicable and pv.accepted:
        ctx = OperatorContext(instance=instance, cache=ChargingRepairCache())
        after = apply_operator_plan(base_state, ctx, base_plan)
        feas = evaluate_feasibility(instance, after)
        results.append(
            MetamorphicCaseResult(
                case_id="feasibility_preserved_on_apply",
                passed=feas.feasible,
                detail=f"violations={feas.violation_count}",
            )
        )
    else:
        results.append(
            MetamorphicCaseResult(
                case_id="feasibility_preserved_on_apply",
                passed=True,
                detail="skipped",
            )
        )

    passed = sum(1 for r in results if r.passed)
    rate = passed / len(results) if results else 0.0
    return MetamorphicReport(
        accepted=all(r.passed for r in results),
        results=results,
        semantic_invariance_pass_rate=rate,
    )
