"""The next evolution run uses one shared mutation operator and selection rule."""
from __future__ import annotations

from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.experiments.generational_compare import _apply_component, _selected
from evrptw_autolab.experiments.matched_pilot import KINDS, _comparison_summary, _select
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_VERSION


def _row(candidate_id: str, instance_id: str, key: list[float]) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "instance_id": instance_id,
        "seed": 7,
        "feasible": True,
        "objective_key": key,
    }


def test_selector_keeps_the_accepted_candidate_with_more_wins() -> None:
    baseline = [
        {"instance_id": "a", "seed": 7, "feasible": True, "objective_key": [10.0]},
        {"instance_id": "b", "seed": 7, "feasible": True, "objective_key": [10.0]},
    ]
    early = [_row("early", "a", [9.0]), _row("early", "b", [10.0])]
    later = [_row("later", "a", [9.0]), _row("later", "b", [8.0])]
    selected = _select(baseline, early + later)
    assert selected["selected_candidate_id"] == "later"


def test_selector_breaks_equal_wins_toward_the_earlier_candidate() -> None:
    baseline = [{"instance_id": "a", "seed": 7, "feasible": True, "objective_key": [10.0]}]
    rows = [_row("early", "a", [9.0]), _row("later", "a", [8.0])]
    selected = _select(baseline, rows)
    assert selected["selected_candidate_id"] == "early"


def test_comparison_summary_includes_the_classical_key() -> None:
    summary = _comparison_summary(
        [{"instance_id": "a", "feasible": True, "objective_key": [1.0], "first_fault": ""}],
        [{"instance_id": "a", "feasible": True, "objective_key": [2.0], "first_fault": ""}],
    )
    assert summary[0]["classical_key"] == [2.0]
    assert summary[0]["candidate_key"] == [1.0]


def test_parent_mutation_replaces_only_the_scheduled_component() -> None:
    parent = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    sources, schema = _apply_component(
        parent,
        FEATURE_SCHEMA_VERSION,
        "removal_priority",
        "replacement-source",
        "2026-10-18.v2",
    )
    assert sources["removal_priority"] == "replacement-source"
    assert sources["insertion_score"] == parent["insertion_score"]
    assert sources["station_score"] == parent["station_score"]
    assert schema == FEATURE_SCHEMA_VERSION


def test_generational_selection_prefers_more_wins() -> None:
    history = [
        {"accepted": True, "generation": 0, "candidate_id": "g0", "decision": {"wins": 1}},
        {"accepted": False, "generation": 1, "candidate_id": "g1", "decision": {"wins": 4}},
        {"accepted": True, "generation": 2, "candidate_id": "g2", "decision": {"wins": 3}},
    ]
    assert _selected(history) == "g2"


def test_unified_and_role_split_use_different_model_roles() -> None:
    import json

    from evrptw_autolab.experiments.matched_pilot import (
        _architect_text,
        _propose_component,
        _propose_unified_component,
    )
    from evrptw_autolab.llm.registry import FakeBackend
    from evrptw_autolab.llm.usage import UsageCollector

    expression = json.dumps(
        {"component": "insertion_score", "expression": "max(0, capacity_slack - demand) + abs(delta_distance)"}
    )
    backend = FakeBackend(
        {
            "unified": expression,
            "architect": json.dumps({"hypothesis": "Lower delta_distance to reduce travel distance"}),
            "routing": expression,
        },
        token_sequence=[4],
    )
    collector = UsageCollector(max_calls=4, max_tokens=100)
    _code, row, _schema = _propose_unified_component(
        collector, backend, "fake", "insertion_score", context="test"
    )
    hypothesis = _architect_text(collector, backend, "fake", context="test")["hypothesis"]
    _code, specialist, _schema = _propose_component(
        collector, backend, "fake", "insertion_score", context="test"
    )
    assert backend.calls == ["unified", "architect", "routing"]
    assert row["agent_role"] == "unified"
    assert specialist["agent_role"] == "routing"
    assert hypothesis == "Lower delta_distance to reduce travel distance"


def test_ungrounded_architect_hypothesis_is_rejected() -> None:
    import json

    from evrptw_autolab.experiments.matched_pilot import _architect_text
    from evrptw_autolab.llm.registry import FakeBackend
    from evrptw_autolab.llm.usage import UsageCollector

    backend = FakeBackend(
        {"architect": json.dumps({"hypothesis": "improve insertion speed and data structures"})},
        token_sequence=[3],
    )
    collector = UsageCollector(max_calls=4, max_tokens=100)
    result = _architect_text(collector, backend, "fake", context="routing test")
    assert result["grounded"] is False
    assert backend.calls == ["architect", "architect"]


def test_score_change_without_a_ranking_change_is_recorded_separately() -> None:
    from evrptw_autolab.components.expressions import wrap_expression
    from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
    from evrptw_autolab.experiments.generational_compare import _probe_trace

    doubled = wrap_expression(
        "removal_priority",
        "2.0 * ((0.0 if due_time >= 1000000.0 else due_time) + 10.0 * route_distance_share + 0.01 * rng_value)",
    )
    sources = dict(DEFAULT_SOURCES)
    sources["removal_priority"] = doubled
    trace = _probe_trace(sources)
    assert trace["score_changed"] is True
    assert trace["ranking_changed"] is False
    assert trace["selected_move_changed"] is False


def test_fixed_cost_feature_can_change_the_selected_insertion() -> None:
    from evrptw_autolab.backbone.util import call_scorer
    from evrptw_autolab.components.expressions import wrap_expression
    from evrptw_autolab.components.loader import load_bundle
    from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V3

    distance_only = wrap_expression("insertion_score", "delta_distance", FEATURE_SCHEMA_V3)
    with_fixed = wrap_expression(
        "insertion_score",
        "delta_distance + new_route_fixed_cost",
        FEATURE_SCHEMA_V3,
    )
    points = (
        {"delta_distance": 1.0, "due_time": 10.0, "ready_time": 0.0, "demand": 1.0, "capacity_slack": 5.0, "vehicle_fixed_cost": 10.0, "marginal_energy": 0.0, "new_route_fixed_cost": 100.0},
        {"delta_distance": 2.0, "due_time": 10.0, "ready_time": 0.0, "demand": 1.0, "capacity_slack": 5.0, "vehicle_fixed_cost": 10.0, "marginal_energy": 0.0, "new_route_fixed_cost": 0.0},
    )
    left, _ = load_bundle({"insertion_score": distance_only}, feature_schema=FEATURE_SCHEMA_V3)
    right, errors = load_bundle({"insertion_score": with_fixed}, feature_schema=FEATURE_SCHEMA_V3)
    assert errors == []
    left_scores = [call_scorer(left.insertion_score, point, ()) for point in points]
    right_scores = [call_scorer(right.insertion_score, point, ()) for point in points]
    assert left_scores.index(min(left_scores)) == 0
    assert right_scores.index(min(right_scores)) == 1


def test_v3_default_formulas_match_v1_on_shared_features() -> None:
    from evrptw_autolab.backbone.util import call_scorer
    from evrptw_autolab.components.expressions import ARGUMENT_NAMES, default_sources
    from evrptw_autolab.components.loader import load_bundle
    from evrptw_autolab.experiments.generational_compare import _PROBES
    from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V3, FEATURE_SCHEMA_VERSION

    v1, _ = load_bundle(default_sources(FEATURE_SCHEMA_VERSION), feature_schema=FEATURE_SCHEMA_VERSION)
    v3, errors = load_bundle(default_sources(FEATURE_SCHEMA_V3), feature_schema=FEATURE_SCHEMA_V3)
    assert errors == []
    for kind, points in _PROBES.items():
        left = getattr(v1, kind)
        right = getattr(v3, kind)
        for point in points:
            assert call_scorer(left, point, ARGUMENT_NAMES[kind]) == call_scorer(
                right, point, ARGUMENT_NAMES[kind]
            )


def test_late_candidate_does_not_beat_an_on_time_baseline() -> None:
    from evrptw_autolab.experiments.bundle_selection import conservative_decision
    from evrptw_autolab.experiments.matched_pilot import _pairs

    baseline = [
        {
            "instance_id": "c101_21",
            "seed": 7,
            "feasible": True,
            "objective_key": [100.0],
            "completed_within_budget": True,
        }
    ]
    candidate = [
        {
            "instance_id": "c101_21",
            "seed": 7,
            "feasible": True,
            "objective_key": [90.0],
            "completed_within_budget": False,
        }
    ]
    pairs = _pairs(baseline, candidate)
    decision = conservative_decision(pairs)
    assert pairs[0]["deadline_regression"] is True
    assert pairs[0]["paired_outcome"] == "baseline"
    assert decision["accepted"] is False
    assert decision["reason"] == "deadline_regression"
