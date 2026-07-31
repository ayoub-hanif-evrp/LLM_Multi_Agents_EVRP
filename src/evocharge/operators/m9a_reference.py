"""Reference precondition-aware operators for Milestone 9A (human-authored).

These are not LLM-generated. They demonstrate the API 1.1.0 contract and are
used to verify evaluation/metamorphic infrastructure before population evolution.
"""

from __future__ import annotations

H2_CRITICAL_CUSTOMER_DESTROY = '''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = [
        "has_routes",
        "rank_customers_by_energy_criticality",
        "query_time_slack",
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
    for ri in range(len(state.solution.routes)):
        if len(customers_in_route(state, ri)) > 0:
            route_index = ri
            break
    ranked = rank_customers_by_energy_criticality(state, route_index, k=1)
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
    tw = query_time_slack(state, route_index, 0)
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
                score=float(tw),
                rationale="energy_critical_customer_on_selected_route",
            )
        ],
        actions=[
            plan_customer_removal([cid], action_id="a0"),
            plan_regret_reinsertion([cid], action_id="a1"),
        ],
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=1,
        notes=["m9a_ref_h2_critical_customer"],
    )
'''

H3_STATION_REPLACEMENT = '''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = [
        "stations_in_route",
        "rank_stations_by_detour",
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
    route_index = 0
    ranked = ()
    for ri in range(len(state.solution.routes)):
        cand = rank_stations_by_detour(state, ri, k=1)
        if len(cand) > 0:
            route_index = ri
            ranked = cand
            break
    if len(ranked) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_stations_on_any_route",
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
                    rationale="station_present_but_no_alternative",
                )
            ],
            actions=[],
            expected_behavioral_effect="none",
        )
    new = alts[0]
    if new == old:
        return OperatorPlan(
            applicable=False,
            no_action_reason="alternative_identical",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    detour = query_downstream_charging_delay(state, route_index)
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
                score=float(detour),
                rationale="high_detour_station_on_route",
            ),
            SelectionEvidence(
                entity_id=new,
                query_id="enumerate_feasible_station_replacements",
                score=1.0,
                rationale="distinct_compatible_alternative",
            ),
        ],
        actions=[
            plan_station_replacement(route_index, old, new, action_id="a0"),
        ],
        expected_behavioral_effect="station_sequence_changed",
        estimated_removals=0,
        notes=["m9a_ref_h3_station_replace"],
    )
'''

H1_SEGMENT_CHARGING = '''def build_operator_plan(state, context, rng):
    _ = context
    _ = rng
    checked = [
        "non_depot_segments",
        "rank_segments_by_charging_detour_contribution",
        "customer_positions_only",
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
    ranked = ()
    for ri in range(len(state.solution.routes)):
        cand = rank_segments_by_charging_detour_contribution(state, ri, k=1)
        if len(cand) > 0:
            route_index = ri
            ranked = cand
            break
    if len(ranked) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_customer_segment",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    seg = ranked[0]
    start = int(seg.start_index)
    end = int(seg.end_index)
    positions = customer_positions_only(state, route_index)
    if len(positions) == 0:
        return OperatorPlan(
            applicable=False,
            no_action_reason="no_customer_positions",
            preconditions_checked=checked,
            selected_entities=[],
            selection_evidence=[],
            actions=[],
            expected_behavioral_effect="none",
        )
    detour = query_charging_detour(state, route_index)
    cust_ids = list(seg.metadata.get("customer_ids") or [])
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=[
            EntityReference(
                entity_type="segment",
                entity_id=seg.entity_id,
                route_index=route_index,
                start_index=start,
                end_index=end,
            )
        ],
        selection_evidence=[
            SelectionEvidence(
                entity_id=seg.entity_id,
                query_id="rank_segments_by_charging_detour_contribution",
                score=float(detour),
                rationale="non_depot_customer_segment_with_detour",
            )
        ],
        actions=[
            plan_segment_removal(route_index, start, end, action_id="a0"),
            plan_charging_reconstruction(route_index, action_id="a1"),
            plan_regret_reinsertion(cust_ids, action_id="a2"),
        ],
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=max(1, len(cust_ids)),
        notes=["m9a_ref_h1_segment_charge"],
    )
'''

REFERENCE_SOURCES = {
    "h2": H2_CRITICAL_CUSTOMER_DESTROY,
    "h3": H3_STATION_REPLACEMENT,
    "h1": H1_SEGMENT_CHARGING,
}
