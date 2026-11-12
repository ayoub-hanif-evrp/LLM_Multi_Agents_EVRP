"""P0 research-validity fixes: gates, evidence prompts, preconditions, expression checks."""

from __future__ import annotations

import json

import pytest

from evrptw_autolab.discovery.controller import (
    CallBudget,
    _critic_prompt,
    _specialist_prompt,
    admit,
    operator_fingerprint,
    run_cycle,
)
from evrptw_autolab.discovery.messages import Hypothesis
from evrptw_autolab.discovery.policy_language import (
    PolicyError,
    normalize_expression,
    validate_expression,
)
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.problem.v2.report import EvaluationReportV2
from evrptw_autolab.problem.v2.types import CapabilityFlags
from evrptw_autolab.research.live_signal import paired_outcome, run_signal
from evrptw_autolab.research.panel import development_case
from evrptw_autolab.transfer.context_features import context_for_operator, search_context
from evrptw_autolab.transfer.hard_compatibility import compatibility_failures
from evrptw_autolab.transfer.selective_controller import select_operator


def _operator(**overrides: object) -> OperatorSpec:
    payload = {
        "operator_id": "long_detour",
        "version": "1",
        "source_agent": "test",
        "description": "Prefer the longer detour.",
        "operator_family": "repair",
        "implementation_reference": "repair_greedy",
        "required_capabilities": ["time_windows"],
        "applicability_rule": "1",
        "candidate_scoring_policy": "-1 * delta_distance",
        "fallback_operator": "classical_default",
    }
    payload.update(overrides)
    return OperatorSpec.model_validate(payload)


def test_true_is_normalized_to_numeric_one() -> None:
    assert normalize_expression("true") == "1"
    assert normalize_expression("FALSE") == "0"
    assert validate_expression("true", {"route_utilization"}) == "1"


def test_unknown_feature_is_rejected_before_search() -> None:
    with pytest.raises(PolicyError, match="unknown feature"):
        validate_expression("not_a_feature - 0.1", {"route_utilization"})


def test_hard_precondition_is_evaluated_at_runtime() -> None:
    operator = _operator(hard_preconditions=["route_utilization - 0.95"])
    flags = CapabilityFlags(time_windows=True)
    low = {"route_utilization": 0.2, "customer_count": 3.0}
    high = {"route_utilization": 0.99, "customer_count": 3.0}
    assert "hard precondition not satisfied" in compatibility_failures(
        operator, flags, available_features=set(low), context=low
    )[0]
    assert compatibility_failures(operator, flags, available_features=set(high), context=high) == []
    assert select_operator(operator, flags, low).action == "classical_default"
    assert select_operator(operator, flags, high).action == "apply"


def test_required_feature_checked_against_runtime_map() -> None:
    operator = _operator(required_features=["battery_slack"])
    flags = CapabilityFlags(time_windows=True, battery=True)
    failures = compatibility_failures(
        operator,
        flags,
        available_features={"route_utilization"},
        context={"route_utilization": 0.5},
    )
    assert any("missing required feature battery_slack" in item for item in failures)


def test_expensive_context_fills_battery_slack_when_rule_needs_it() -> None:
    spec, solution, _removed = development_case()
    cheap = search_context(spec, solution, expensive=False)
    assert cheap["battery_slack"] == 0.0
    operator = _operator(applicability_rule="battery_slack + 1")
    rich = context_for_operator(spec, solution, operator)
    # Development microcase has battery capacity; slack is computed, not left as the cheap zero path.
    assert "battery_slack" in rich


def test_critic_revision_recomputes_source_hash() -> None:
    hypothesis = Hypothesis(
        hypothesis="Negative distance weight lengthens insertions under high utilization.",
        target_bottleneck="insertion ranking",
        affected_capabilities=["time_windows"],
        proposed_operator_id="long_detour",
        expected_useful_conditions="high route utilization",
        expected_failure_conditions="low route utilization",
        measurable_prediction="native objective increases on this repair",
    )
    proposal = _operator()
    backend = FakeBackend(
        {
            "architect": hypothesis.model_dump_json(),
            "routing_specialist": proposal.model_dump_json(),
            "critic": json.dumps(
                {
                    "what_failed": "longer detour raised the native objective",
                    "operator_should_change": False,
                    "applicability_should_change": True,
                    "evidence_too_weak": False,
                    "revised_applicability_rule": "route_utilization - 0.9",
                }
            ),
        }
    )
    spec, solution, removed = development_case()
    result = run_cycle(
        backend,
        spec,
        solution,
        removed,
        partition="development",
        budget=CallBudget(4, model="controlled"),
    )
    assert result["critic_revised"] is True
    revised = OperatorSpec.model_validate(result["operator"])
    assert revised.applicability_rule == "route_utilization - 0.9"
    assert revised.source_hash == operator_fingerprint(revised)
    assert revised.source_hash != operator_fingerprint(proposal)


def test_specialist_and_critic_prompts_carry_evidence() -> None:
    hypothesis = Hypothesis(
        hypothesis="Use shorter detours when utilization is high.",
        target_bottleneck="insertion ranking",
        affected_capabilities=["time_windows"],
        proposed_operator_id="short_detour",
        expected_useful_conditions="high utilization",
        expected_failure_conditions="empty routes",
        measurable_prediction="distance falls on the development repair",
    )
    operator = _operator()
    specialist = _specialist_prompt(hypothesis)
    critic = _critic_prompt(hypothesis, operator, [{"counterexample_id": "cx-1"}])
    assert "Use shorter detours when utilization is high." in specialist
    assert "delta_distance" in specialist
    assert "route_utilization" in specialist
    assert "cx-1" in critic
    assert operator.operator_id in critic


def test_admit_rejects_bare_true_only_after_normalization_is_legal() -> None:
    digest = admit(
        _operator(applicability_rule="true"),
        set(),
        CapabilityFlags(time_windows=True),
    )
    assert isinstance(digest, str) and len(digest) == 16


def test_paired_outcome_marks_feasible_worsening() -> None:
    classical = EvaluationReportV2(feasible=True, objective_key=(3272.0,), vehicles=13)
    worse = EvaluationReportV2(feasible=True, objective_key=(3276.0,), vehicles=13)
    better = EvaluationReportV2(feasible=True, objective_key=(3200.0,), vehicles=13)
    assert paired_outcome(classical, worse) == "objective_regression"
    assert paired_outcome(classical, better) == "improved"
    assert paired_outcome(classical, classical) == "tie"


def test_fake_live_signal_reports_hiermann_regression_as_failure() -> None:
    payload = run_signal(backend="fake", max_calls=4)
    assert payload["gate"] == "objective_regression"
    assert "hiermann" in (payload.get("diagnosis") or "")
    by_family = {row["family"]: row for row in payload["paired"]}
    assert by_family["schneider"]["outcome"] == "tie"
    assert by_family["hiermann"]["outcome"] == "objective_regression"
    assert by_family["hiermann"]["candidate_objective_key"][0] > by_family["hiermann"]["classical_objective_key"][0]
