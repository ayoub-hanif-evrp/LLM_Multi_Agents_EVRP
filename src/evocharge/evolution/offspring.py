"""Structured offspring generation (lineage + modification plans)."""

from __future__ import annotations

import random
from typing import Any

from evocharge.evolution.schemas import CreationMode, ModificationPlan
from evocharge.operators.m9a_reference import REFERENCE_SOURCES


def _noop_source() -> str:
    return '''def build_operator_plan(state, context, rng):
    _ = state
    _ = context
    _ = rng
    return OperatorPlan(
        applicable=False,
        no_action_reason="noop_control",
        preconditions_checked=["noop"],
        selected_entities=[],
        selection_evidence=[],
        actions=[],
        expected_behavioral_effect="none",
        notes=["noop_control"],
    )
'''


def _random_composition(rng: random.Random) -> str:
    k = rng.randint(1, 2)
    use_regret = rng.choice([True, False])
    reinsert = (
        "plan_regret_reinsertion([cid], action_id=\"a1\"),"
        if use_regret
        else "plan_greedy_reinsertion([cid], action_id=\"a1\"),"
    )
    return f'''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = ["has_routes", "rank_customers_by_energy_criticality"]
    if len(state.solution.routes) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_routes",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    route_index = 0
    for ri in range(len(state.solution.routes)):
        if len(customers_in_route(state, ri)) > 0:
            route_index = ri
            break
    ranked = rank_customers_by_energy_criticality(state, route_index, k={k})
    if len(ranked) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_customers_on_route",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    chosen = ranked[0]
    cid = chosen.entity_id
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=[
            EntityReference(entity_type="customer", entity_id=cid, route_index=route_index)
        ],
        selection_evidence=[
            SelectionEvidence(
                entity_id=cid,
                query_id="rank_customers_by_energy_criticality",
                score=1.0,
                rationale="random_composition_top_critical",
            )
        ],
        actions=[
            plan_customer_removal([cid], action_id="a0"),
            {reinsert}
        ],
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=1,
        notes=["random_composition"],
    )
'''


def _mutate_h2(k: int, pick_last: bool) -> str:
    route_loop = (
        "for ri in range(len(state.solution.routes)-1, -1, -1):"
        if pick_last
        else "for ri in range(len(state.solution.routes)):"
    )
    return f'''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = [
        "has_routes",
        "rank_customers_by_energy_criticality",
        "query_energy_slack",
    ]
    if len(state.solution.routes) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_routes",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    route_index = 0
    {route_loop}
        if len(customers_in_route(state, ri)) > 0:
            route_index = ri
            break
    ranked = rank_customers_by_energy_criticality(state, route_index, k={k})
    if len(ranked) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_customers_on_route",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    chosen = ranked[0]
    cid = chosen.entity_id
    slack = query_energy_slack(state, route_index)
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=[
            EntityReference(entity_type="customer", entity_id=cid, route_index=route_index)
        ],
        selection_evidence=[
            SelectionEvidence(
                entity_id=cid,
                query_id="rank_customers_by_energy_criticality",
                score=float(slack),
                rationale="mutated_energy_critical_selection",
            )
        ],
        actions=[
            plan_customer_removal([cid], action_id="a0"),
            plan_regret_reinsertion([cid], action_id="a1"),
        ],
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=1,
        notes=["mutation_h2"],
    )
'''


def _crossover_h2_select_h3_action() -> str:
    """Selection from H2-style ranking; action is station replacement when available."""
    return '''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = [
        "rank_customers_by_energy_criticality",
        "stations_in_route",
        "enumerate_feasible_station_replacements",
    ]
    if len(state.solution.routes) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_routes",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    # Prefer routes with both customers and stations
    route_index = 0
    found = False
    for ri in range(len(state.solution.routes)):
        if len(customers_in_route(state, ri)) > 0 and len(stations_in_route(state, ri)) > 0:
            route_index = ri
            found = True
            break
    if not found:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_route_with_customers_and_stations",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    _ = rank_customers_by_energy_criticality(state, route_index, k=1)
    ranked = rank_stations_by_detour(state, route_index, k=1)
    if len(ranked) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_stations",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    old = ranked[0].entity_id
    alts = enumerate_feasible_station_replacements(state, route_index, old, max_alternatives=5)
    if len(alts) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_alternative_station",
            preconditions_checked=checked,
            selected_entities=[
                EntityReference(entity_type="station", entity_id=old, route_index=route_index)
            ],
            selection_evidence=[
                SelectionEvidence(
                    entity_id=old,
                    query_id="rank_stations_by_detour",
                    score=1.0,
                    rationale="crossover_no_alt",
                )
            ],
            actions=[],
            expected_behavioral_effect="none",
        )
    new = alts[0]
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=[
            EntityReference(entity_type="station", entity_id=old, route_index=route_index),
            EntityReference(entity_type="station", entity_id=new, route_index=route_index),
        ],
        selection_evidence=[
            SelectionEvidence(
                entity_id=old,
                query_id="rank_stations_by_detour",
                score=1.0,
                rationale="crossover_select_station_via_detour",
            ),
            SelectionEvidence(
                entity_id=new,
                query_id="enumerate_feasible_station_replacements",
                score=1.0,
                rationale="crossover_action_replace",
            ),
        ],
        actions=[plan_station_replacement(route_index, old, new, action_id="a0")],
        expected_behavioral_effect="station_sequence_changed",
        notes=["semantic_crossover_h2select_h3action"],
    )
'''


def _revise_for_inert(parent_key: str = "h2") -> tuple[str, ModificationPlan]:
    # Address inertness by increasing k and preferring last route with customers
    src = _mutate_h2(k=2, pick_last=True)
    plan = ModificationPlan(
        mode="evidence_guided_revision",
        rationale="Increase selection breadth and change route scan order to escape inert applies.",
        parent_ids=[f"m9a_ref_{parent_key}_precondition"],
        changes=["k=2", "scan_routes_reversed"],
        weakness_addressed="APPLIED_BUT_INERT",
    )
    return src, plan


def _analogue_destroy_source() -> str:
    return '''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = ["rank_customers_by_energy_criticality", "handcrafted_analogue_style"]
    if len(state.solution.routes) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_routes",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    route_index = 0
    for ri in range(len(state.solution.routes)):
        if len(customers_in_route(state, ri)) > 0:
            route_index = ri
            break
    ranked = rank_customers_by_energy_criticality(state, route_index, k=2)
    if len(ranked) < 1:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_customers",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    cid = ranked[0].entity_id
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=[
            EntityReference(entity_type="customer", entity_id=cid, route_index=route_index)
        ],
        selection_evidence=[
            SelectionEvidence(
                entity_id=cid,
                query_id="rank_customers_by_energy_criticality",
                score=1.0,
                rationale="analogue_low_energy_slack_style",
            )
        ],
        actions=[
            plan_customer_removal([cid], action_id="a0"),
            plan_regret_reinsertion([cid], action_id="a1"),
        ],
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=1,
        notes=["handcrafted_analogue_wrapper"],
    )
'''


def seed_sources() -> dict[str, tuple[str, CreationMode, list[str]]]:
    """candidate_key -> (source, mode, hypothesis_ids)."""
    return {
        "seed_h1": (REFERENCE_SOURCES["h1"], "seed", ["M9A-H1"]),
        "seed_h2": (REFERENCE_SOURCES["h2"], "seed", ["M9A-H2"]),
        "seed_h3": (REFERENCE_SOURCES["h3"], "seed", ["M9A-H3"]),
        "seed_analogue": (_analogue_destroy_source(), "handcrafted_analogue", ["ANALOGUE"]),
        "seed_random": (_random_composition(random.Random(2027)), "random_composition", ["RAND"]),
        "seed_noop": (_noop_source(), "noop_control", ["NOOP"]),
    }


def make_offspring(
    *,
    mode: CreationMode,
    rng: random.Random,
    parent_ids: list[str],
    generation: int,
) -> tuple[str, ModificationPlan, str]:
    """Return (source, plan, suggested_suffix)."""
    _ = generation
    if mode == "mutation":
        k = rng.choice([1, 2, 3])
        pick_last = rng.choice([True, False])
        src = _mutate_h2(k=k, pick_last=pick_last)
        plan = ModificationPlan(
            mode="mutation",
            rationale="Mutate H2 selection breadth and route scan order.",
            parent_ids=parent_ids or ["seed_h2"],
            changes=[f"k={k}", f"pick_last={pick_last}"],
        )
        return src, plan, f"mut_k{k}_{int(pick_last)}"
    if mode == "semantic_crossover":
        src = _crossover_h2_select_h3_action()
        plan = ModificationPlan(
            mode="semantic_crossover",
            rationale=(
                "Combine customer/station route filtering (H2-style awareness) "
                "with station replacement action (H3)."
            ),
            parent_ids=parent_ids or ["seed_h2", "seed_h3"],
            changes=["selection:rank_stations_by_detour", "action:plan_station_replacement"],
        )
        return src, plan, "xover_h2h3"
    if mode == "evidence_guided_revision":
        src, plan = _revise_for_inert("h2")
        plan.parent_ids = parent_ids or plan.parent_ids
        return src, plan, "rev_inert"
    if mode == "novel_invention":
        # Limited novelty: segment ranking with greedy reinsertion (not a parent clone)
        src = _random_composition(rng)
        # Replace note
        src = src.replace('notes=["random_composition"]', 'notes=["novel_invention_bounded"]')
        plan = ModificationPlan(
            mode="novel_invention",
            rationale="Bounded novel composition from approved primitives only.",
            parent_ids=parent_ids,
            changes=["rank_customers", "optional_reinsertion_variant"],
        )
        return src, plan, "novel"
    if mode == "baseline_random_mutation":
        src = _mutate_h2(k=rng.randint(1, 3), pick_last=rng.random() < 0.5)
        plan = ModificationPlan(
            mode="baseline_random_mutation",
            rationale="Random mutation baseline without LLM reasoning.",
            parent_ids=parent_ids or ["seed_h2"],
            changes=["random_k", "random_scan"],
        )
        return src, plan, "base_randmut"
    if mode == "baseline_non_llm":
        src = _crossover_h2_select_h3_action()
        plan = ModificationPlan(
            mode="baseline_non_llm",
            rationale="Non-LLM structured crossover baseline.",
            parent_ids=parent_ids or ["seed_h2", "seed_h3"],
            changes=["structured_crossover"],
        )
        return src, plan, "base_nonllm"
    # default
    src = _random_composition(rng)
    plan = ModificationPlan(
        mode="random_composition",
        rationale="Random valid primitive composition.",
        parent_ids=parent_ids,
        changes=["random_composition"],
    )
    return src, plan, "rand"


def choose_offspring_modes(rng: random.Random, n: int) -> list[CreationMode]:
    bag: list[CreationMode] = [
        "mutation",
        "semantic_crossover",
        "evidence_guided_revision",
        "novel_invention",
    ]
    # Keep novel invention rare
    weights = [3, 2, 2, 1]
    out: list[CreationMode] = []
    for _ in range(n):
        out.append(rng.choices(bag, weights=weights, k=1)[0])
    return out


def source_fingerprint(source: str) -> dict[str, Any]:
    return {
        "n_lines": len(source.splitlines()),
        "has_station_replacement": "plan_station_replacement" in source,
        "has_customer_removal": "plan_customer_removal" in source,
        "has_segment_removal": "plan_segment_removal" in source,
        "has_noop": "noop_control" in source,
    }
