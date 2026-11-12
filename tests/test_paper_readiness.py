"""Foundation tests for the paper-readiness path."""

import pytest

from evrptw_autolab.discovery.controller import CallBudget, admit
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import CapabilityFlags
from evrptw_autolab.research.live_signal import run_signal


def test_call_budget_is_fail_closed() -> None:
    class Backend:
        provider = "fake"
        last_usage = None
        calls: list[str] = []

        def complete(self, **kwargs):
            self.calls.append(kwargs["role"])
            return "{}"

    budget = CallBudget(1, model="x", max_tokens=10)
    with pytest.raises(RuntimeError, match="budget exhausted"):
        budget.charge(Backend(), "architect", "a")
        budget.charge(Backend(), "architect", "b")


def test_admit_rejects_unknown_required_feature() -> None:
    operator = OperatorSpec(
        operator_id="bad",
        version="1",
        source_agent="test",
        description="x",
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        required_features=["not_a_real_feature"],
        candidate_scoring_policy="delta_distance",
        applicability_rule="1",
    )
    with pytest.raises(ValueError, match="missing required feature"):
        admit(operator, set(), CapabilityFlags(time_windows=True))


def test_fake_live_signal_writes_paired_outcomes() -> None:
    payload = run_signal(backend="fake", max_calls=4)
    assert payload["backend"] == "fake"
    assert payload["llm_calls"] == 3
    # Scripted long-detour is worse on Hiermann; that must not be labeled successful.
    assert payload["gate"] == "objective_regression"
    assert len(payload["paired"]) == 2
    assert all(row["policy_executed"] for row in payload["paired"])
    assert all(row["source_hash"] for row in payload["paired"])
    assert all("outcome" in row for row in payload["paired"])
