"""Hard capability checks reject an operator before any search."""

from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import CapabilityFlags
from evrptw_autolab.transfer.hard_compatibility import compatibility_failures


def _pickup_operator() -> OperatorSpec:
    return OperatorSpec(
        operator_id="pair_relocate",
        version="1",
        source_agent="test",
        description="Move one pickup-delivery pair.",
        operator_family="local_search",
        implementation_reference="optimization.operators.local_search.relocate_pairs",
        required_capabilities=["pickup_delivery"],
        forbidden_capabilities=["heterogeneous_fleet"],
        fallback_operator="classical_default",
    )


def test_pickup_operator_is_rejected_on_schneider_capabilities() -> None:
    flags = CapabilityFlags(time_windows=True, battery=True, full_recharge=True)
    failures = compatibility_failures(_pickup_operator(), flags)
    assert "missing required capability pickup_delivery" in failures


def test_pickup_operator_is_rejected_on_a_heterogeneous_fleet() -> None:
    flags = CapabilityFlags(pickup_delivery=True, heterogeneous_fleet=True)
    failures = compatibility_failures(_pickup_operator(), flags)
    assert "forbidden capability heterogeneous_fleet is present" in failures


def test_pickup_operator_is_allowed_when_the_capabilities_match() -> None:
    flags = CapabilityFlags(pickup_delivery=True, time_windows=True)
    assert compatibility_failures(_pickup_operator(), flags) == []
