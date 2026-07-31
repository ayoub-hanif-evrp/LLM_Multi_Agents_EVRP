# Coding Agent — Task (Milestone 9A)

Generate a precondition-aware operator for the following validated hypothesis.

## Coding request
```json
{{request_json}}
```

## Hypothesis
```json
{{hypothesis_json}}
```

## Revision feedback (may be empty)
```json
{{revision_feedback}}
```

## Exact primitive call forms (use these signatures only)
```python
customers_in_route(state, route_index)
stations_in_route(state, route_index)
customer_positions_only(state, route_index)
non_depot_segments(state, route_index, min_len=1, max_len=4)
rank_customers_by_energy_criticality(state, route_index, k=3)
rank_segments_by_charging_detour_contribution(state, route_index, k=3)
rank_stations_by_detour(state, route_index, k=3)
enumerate_feasible_station_replacements(state, route_index, station_id, max_alternatives=5)
query_time_slack(state, route_index, stop_index)
query_energy_slack(state, route_index)
query_charging_detour(state, route_index)
query_station_dependency(state, route_index)
query_downstream_charging_delay(state, route_index)
plan_customer_removal(customer_ids, action_id="a0")
plan_regret_reinsertion(customer_ids, action_id="a1")
plan_charging_reconstruction(route_index, action_id="a2")
plan_station_replacement(route_index, old_station_id, new_station_id, action_id="a3")
plan_segment_removal(route_index, start_index, end_index, action_id="a4")
```

## Preferred precondition-aware sketch (adapt to allowed_primitives)
```python
def build_operator_plan(state, context, rng):
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
    evidence = [
        SelectionEvidence(
            entity_id=cid,
            query_id="rank_customers_by_energy_criticality",
            score=1.0,
            rationale="highest_energy_criticality_on_route",
        )
    ]
    entities = [
        EntityReference(
            entity_type="customer",
            entity_id=cid,
            route_index=route_index,
        )
    ]
    actions = [
        plan_customer_removal([cid], action_id="a0"),
        plan_regret_reinsertion([cid], action_id="a1"),
    ]
    return OperatorPlan(
        applicable=True,
        no_action_reason=None,
        preconditions_checked=checked,
        selected_entities=entities,
        selection_evidence=evidence,
        actions=actions,
        expected_behavioral_effect="customer_sequence_changed",
        estimated_removals=1,
    )
```

Never hardcode customer/station string IDs. Never use segment slice [0:1].
Return CodingAgentResponse JSON with metadata and source_code.
