"""Behavioral effect measurement for generated candidates (Milestone 8)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from evocharge.domain.instance import Instance
from evocharge.domain.objective import ObjectiveVector
from evocharge.domain.solution import Solution
from evocharge.operators.api import OperatorContext
from evocharge.operators.generated_api import OperatorPlan, ReadOnlySearchState
from evocharge.operators.primitives import apply_operator_plan
from evocharge.solver.feasibility import evaluate_feasibility, evaluate_objective
from evocharge.solver.route_utils import customer_sequence_of


class BehavioralEffect(BaseModel):
    plan_nonempty: bool
    plan_applied: bool
    customer_sequence_changed: bool
    station_sequence_changed: bool
    charging_decision_changed: bool
    route_assignment_changed: bool
    objective_changed: bool
    feasibility_preserved: bool
    rejection_reason: str | None = None
    before_objective: dict[str, Any] = Field(default_factory=dict)
    after_objective: dict[str, Any] = Field(default_factory=dict)
    n_actions: int = 0
    plan_primitives: list[str] = Field(default_factory=list)


def _customer_seqs(instance: Instance, solution: Solution) -> list[tuple[str, ...]]:
    return [customer_sequence_of(r, instance) for r in solution.routes]


def _station_seqs(instance: Instance, solution: Solution) -> list[tuple[str, ...]]:
    stations = set(instance.station_ids)
    return [
        tuple(n for n in r.node_ids if n in stations) for r in solution.routes
    ]


def _charging_signature(solution: Solution) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for route in solution.routes:
        stops = []
        for s in route.schedule:
            if s.energy_charged > 1e-9 or s.charging_duration > 1e-9:
                stops.append(
                    (
                        s.node_id,
                        round(float(s.energy_charged), 6),
                        round(float(s.charging_duration), 6),
                    )
                )
        out.append(tuple(stops))
    return out


def _route_assignment(instance: Instance, solution: Solution) -> dict[str, int]:
    assign: dict[str, int] = {}
    for i, route in enumerate(solution.routes):
        for cid in customer_sequence_of(route, instance):
            assign[cid] = i
    return assign


def measure_behavioral_effect(
    *,
    instance: Instance,
    before: Solution,
    plan: OperatorPlan | None,
    after: Solution | None,
    context: OperatorContext,
    before_obj: ObjectiveVector | None = None,
    after_obj: ObjectiveVector | None = None,
    plan_applied: bool = True,
    rejection_reason: str | None = None,
) -> BehavioralEffect:
    """Compare before/after solutions under an applied (or rejected) plan."""
    _ = context
    plan_nonempty = bool(plan and plan.actions)
    primitives = [a.primitive_id for a in plan.actions] if plan else []
    if after is None or not plan_applied:
        return BehavioralEffect(
            plan_nonempty=plan_nonempty,
            plan_applied=False,
            customer_sequence_changed=False,
            station_sequence_changed=False,
            charging_decision_changed=False,
            route_assignment_changed=False,
            objective_changed=False,
            feasibility_preserved=True,
            rejection_reason=rejection_reason or "plan_not_applied",
            n_actions=len(plan.actions) if plan else 0,
            plan_primitives=primitives,
        )

    before_report = evaluate_feasibility(instance, before)
    after_report = evaluate_feasibility(instance, after)
    b_obj = before_obj or evaluate_objective(instance, before, before_report)
    a_obj = after_obj or evaluate_objective(instance, after, after_report)

    return BehavioralEffect(
        plan_nonempty=plan_nonempty,
        plan_applied=True,
        customer_sequence_changed=_customer_seqs(instance, before)
        != _customer_seqs(instance, after),
        station_sequence_changed=_station_seqs(instance, before)
        != _station_seqs(instance, after),
        charging_decision_changed=_charging_signature(before)
        != _charging_signature(after),
        route_assignment_changed=_route_assignment(instance, before)
        != _route_assignment(instance, after),
        objective_changed=b_obj.as_tuple() != a_obj.as_tuple(),
        feasibility_preserved=after_report.feasible,
        rejection_reason=rejection_reason,
        before_objective=b_obj.model_dump(),
        after_objective=a_obj.model_dump(),
        n_actions=len(plan.actions) if plan else 0,
        plan_primitives=primitives,
    )


def is_behaviorally_inert(effect: BehavioralEffect) -> bool:
    """Nonempty/applied but no executed-state change counts as inert."""
    if not effect.plan_applied:
        return True
    return not (
        effect.customer_sequence_changed
        or effect.station_sequence_changed
        or effect.charging_decision_changed
        or effect.route_assignment_changed
    )


def apply_and_measure(
    *,
    instance: Instance,
    solution: Solution,
    plan: OperatorPlan,
    context: OperatorContext,
) -> tuple[Solution, BehavioralEffect]:
    state = ReadOnlySearchState(solution=solution, instance=instance)
    after = apply_operator_plan(state, context, plan)
    effect = measure_behavioral_effect(
        instance=instance,
        before=solution,
        plan=plan,
        after=after,
        context=context,
        plan_applied=True,
    )
    return after, effect
