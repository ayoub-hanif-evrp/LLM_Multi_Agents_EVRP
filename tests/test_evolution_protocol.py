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
            "architect": json.dumps({"hypothesis": "prefer short insertions"}),
            "routing": expression,
        },
        token_sequence=[4],
    )
    collector = UsageCollector(max_calls=4, max_tokens=100)
    _code, row, _schema = _propose_unified_component(
        collector, backend, "fake", "insertion_score", context="test"
    )
    hypothesis = _architect_text(collector, backend, "fake", context="test")
    _code, specialist, _schema = _propose_component(
        collector, backend, "fake", "insertion_score", context="test"
    )
    assert backend.calls == ["unified", "architect", "routing"]
    assert row["agent_role"] == "unified"
    assert specialist["agent_role"] == "routing"
    assert hypothesis == "prefer short insertions"
