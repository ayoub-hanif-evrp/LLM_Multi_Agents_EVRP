"""Agent schemas, the mockable discovery/revision loop, and Ollama backend failure handling."""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from chargecegis.agents import (
    AnalystReport,
    Challenge,
    CounterexamplePlan,
    CriticReport,
    MockBackend,
    OllamaBackend,
    ScientistHypothesis,
    discovery_loop,
)

_ANALYST = {
    "dominant_failure": "excess_charging_detours",
    "supporting_metrics": ["delta_charging_distance"],
    "alternative_explanations": ["poor initial routing"],
    "uncertainty": 0.3,
    "missing_evidence": [],
}
_SCIENTIST = {
    "hypothesis": "prefer moves with lower charging detour",
    "target_mechanism": "station_detour_contribution",
    "required_features": ["delta_charging_distance"],
    "expected_behavior": "fewer redundant station visits",
    "no_action_conditions": ["no stations in solution"],
    "invariants": ["relabeling customers must not change ranking"],
    "falsification_condition": "policy ignores delta_charging_distance",
}
_POLICY = {"op": "neg", "arg": {"feature": "delta_charging_distance"}}
_PLAN = {"challenges": [
    {"type": "CUSTOMER_RELABEL", "target_failure": "label_sensitivity",
     "state_requirements": ["feasible solution"], "expected_invariant": "ranking unchanged"},
]}
_CRITIC_RETAIN = {"decision": "RETAIN", "evidence": ["all challenges passed"],
                   "failure_class": "none", "revision_instruction": "", "claim_limit": "single instance family"}
_CRITIC_REVISE = {"decision": "REVISE_ONCE", "evidence": ["fails CUSTOMER_RELABEL"],
                   "failure_class": "label_sensitivity", "revision_instruction": "use relative features only",
                   "claim_limit": "single instance family"}


def test_pydantic_schemas_accept_valid_and_reject_out_of_range_payloads() -> None:
    AnalystReport.model_validate(_ANALYST)
    ScientistHypothesis.model_validate(_SCIENTIST)
    CounterexamplePlan.model_validate(_PLAN)
    Challenge.model_validate(_PLAN["challenges"][0])
    CriticReport.model_validate(_CRITIC_RETAIN)
    with pytest.raises(ValidationError):
        AnalystReport.model_validate({**_ANALYST, "uncertainty": 1.5})


def test_discovery_loop_with_mock_backend_retains_on_first_pass() -> None:
    fixtures = {
        "analyst": _ANALYST, "scientist": _SCIENTIST, "synthesizer": _POLICY,
        "counterexample": _PLAN, "critic": _CRITIC_RETAIN,
    }
    backend = MockBackend(fixtures)
    result = discovery_loop(
        backend, diagnostics={}, archive=[],
        deterministic_evaluate=lambda policy, challenges: {"passed": True},
    )
    assert result["policy"] == _POLICY
    assert result["critic"].decision == "RETAIN"
    assert result["revised_once"] is False
    assert "lineage" not in result


class _SequencedBackend:
    """Per-role response queue: the last entry repeats once exhausted, roles called once
    (analyst/scientist) need only a single fixture."""

    def __init__(self, fixtures: dict[str, list[Any]]) -> None:
        self.fixtures = {role: list(values) for role, values in fixtures.items()}
        self.calls: list[str] = []

    def __call__(self, *, prompt: str, role: str, model: str, temperature: float) -> Any:
        self.calls.append(role)
        queue = self.fixtures[role]
        return queue.pop(0) if len(queue) > 1 else queue[0]


def test_discovery_loop_performs_exactly_one_revision_when_critic_requests_it() -> None:
    backend = _SequencedBackend({
        "analyst": [_ANALYST], "scientist": [_SCIENTIST],
        "synthesizer": [_POLICY, {"feature": "delta_distance_estimate"}],
        "counterexample": [_PLAN, _PLAN],
        "critic": [_CRITIC_REVISE, _CRITIC_RETAIN],
    })
    evaluations: Iterator[dict[str, Any]] = iter(
        [{"passed": False, "failures": ["CUSTOMER_RELABEL"]}, {"passed": True}]
    )
    result = discovery_loop(
        backend, diagnostics={}, archive=[],
        deterministic_evaluate=lambda policy, challenges: next(evaluations),
    )
    assert result["revised_once"] is True
    assert result["critic"].decision == "RETAIN"
    assert result["policy"] == {"feature": "delta_distance_estimate"}
    assert result["lineage"]["revision_reason"] == "label_sensitivity"
    assert backend.calls.count("synthesizer") == 2
    assert backend.calls.count("critic") == 2


def test_ollama_backend_stays_failed_after_repair_retry_also_fails() -> None:
    backend = OllamaBackend(config={"ollama": {"model": "test-model"}, "temperatures": {"analyst": 0.1}})
    with patch.object(backend, "_request", side_effect=ValueError("bad json")) as mocked:
        with pytest.raises(RuntimeError, match="failed for role='analyst'"):
            backend(prompt="p", role="analyst", model="test-model", temperature=0.1)
    assert mocked.call_count == 2  # first attempt + one repair retry, then it must give up


def test_ollama_backend_recovers_via_repair_prompt_on_first_failure() -> None:
    backend = OllamaBackend(config={"ollama": {"model": "test-model"}, "temperatures": {"analyst": 0.1}})
    with patch.object(backend, "_request", side_effect=[ValueError("bad json"), '{"ok": true}']) as mocked:
        result = backend(prompt="p", role="analyst", model="test-model", temperature=0.1)
    assert result == '{"ok": true}'
    assert mocked.call_count == 2
    second_call_prompt = mocked.call_args_list[1].args[0]
    assert "valid JSON" in second_call_prompt
