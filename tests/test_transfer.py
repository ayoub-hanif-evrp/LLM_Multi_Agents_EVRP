"""Cross-variant transfer helpers (no LLM required)."""
from __future__ import annotations

from evrptw_autolab.components.evolution.archive import BundleCandidate
from evrptw_autolab.components.evolution.fitness import InstanceEval, build_panel_evaluation
from evrptw_autolab.components.evolution.transfer import (
    apply_transfer,
    component_compatible,
    evaluate_transfer_effect,
    retrieve_transferable_components,
)
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
from evrptw_autolab.problem.v2.types import CapabilityFlags, ProblemSpecV2


def _spec(family: str, *, battery: bool) -> ProblemSpecV2:
    return ProblemSpecV2(
        instance_id=f"{family}_x",
        family=family,  # type: ignore[arg-type]
        capabilities=CapabilityFlags(euclidean_distances=True, battery=battery, time_windows=True),
        nodes=(),
        vehicle_types=(),
        depot_ids=(),
    )


def test_station_score_incompatible_without_battery() -> None:
    assert component_compatible("station_score", _spec("schneider", battery=True))
    assert not component_compatible("station_score", _spec("synthetic", battery=False))


def test_retrieve_and_measure_negative_transfer() -> None:
    donor = BundleCandidate(
        candidate_id="donor",
        sources={
            "insertion_score": "def insertion_score(a,b,c,d,e):\n    return a*2\n",
            "station_score": DEFAULT_SOURCES["station_score"],
            "removal_priority": DEFAULT_SOURCES["removal_priority"],
        },
        owners={},
        generation=1,
        lineage={
            "insertion_score": {
                "llm_generated": True,
                "human_default_used": False,
                "executed_source_hash": "abc",
            }
        },
        metadata={"source_families": ["montoya"]},
    )
    targets = [_spec("schneider", battery=True)]
    found = retrieve_transferable_components(
        [donor], target_families={"schneider"}, target_specs=targets
    )
    assert found
    before = build_panel_evaluation(
        [
            InstanceEval(
                family="schneider",
                instance_id="x",
                seed=0,
                feasible=True,
                objective_key=(2.0, 100.0),
                runtime_s=1.0,
            )
        ]
    )
    after = build_panel_evaluation(
        [
            InstanceEval(
                family="schneider",
                instance_id="x",
                seed=0,
                feasible=True,
                objective_key=(3.0, 100.0),
                runtime_s=1.0,
            )
        ]
    )
    rec = evaluate_transfer_effect(
        kind="insertion_score",
        source_family="montoya",
        target_family="schneider",
        donor=donor,
        before=before,
        after=after,
        compatible=True,
    )
    assert rec.worsened
    assert not rec.improved
    base = dict(DEFAULT_SOURCES)
    transferred = apply_transfer(base, donor, "insertion_score")
    assert transferred["insertion_score"] == donor.sources["insertion_score"]
