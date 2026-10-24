"""A compatible operator is applied only when the development rule says it is useful."""

from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import CapabilityFlags
from evrptw_autolab.transfer.selective_controller import select_operator


def _operator() -> OperatorSpec:
    return OperatorSpec(
        operator_id="extra_vehicle",
        version="1",
        source_agent="test",
        description="Open another vehicle when routes are saturated.",
        operator_family="fleet",
        implementation_reference="classical_default",
        required_capabilities=["capacity"],
        candidate_scoring_policy="route_utilization - 0.9",
        fallback_operator="classical_default",
    )


def test_low_utilization_keeps_the_classical_operator() -> None:
    flags = CapabilityFlags(capacity=True, time_windows=True)
    decision = select_operator(_operator(), flags, {"route_utilization": 0.2})
    assert decision.action == "classical_default"


def test_high_utilization_applies_the_operator() -> None:
    flags = CapabilityFlags(capacity=True)
    decision = select_operator(_operator(), flags, {"route_utilization": 0.95})
    assert decision.action == "apply"


def test_missing_capability_overrides_a_positive_rule() -> None:
    flags = CapabilityFlags(time_windows=True)
    decision = select_operator(_operator(), flags, {"route_utilization": 0.95})
    assert decision.action == "classical_default"
    assert "capacity" in decision.reason


def test_an_unknown_feature_abstains() -> None:
    flags = CapabilityFlags(capacity=True)
    decision = select_operator(_operator(), flags, {})
    assert decision.action == "abstain"


def test_a_benchmark_name_cannot_be_a_feature() -> None:
    flags = CapabilityFlags(capacity=True)
    decision = select_operator(_operator(), flags, {"route_utilization": 0.95, "filename": 1.0})
    assert decision.action == "abstain"
