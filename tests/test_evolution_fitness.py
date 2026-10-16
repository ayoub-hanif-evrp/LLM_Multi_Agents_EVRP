"""Adversarial tests for panel fitness and lexicographic ranking."""
from __future__ import annotations

from evrptw_autolab.components.evolution.archive import (
    BundleCandidate,
    CandidateArchive,
    apply_panel,
)
from evrptw_autolab.components.evolution.fitness import (
    InstanceEval,
    build_panel_evaluation,
    compare_panel,
    fitness_from_report,
    panel_is_better,
)
from evrptw_autolab.problem.v2.report import EvaluationReportV2


def _row(
    *,
    family: str,
    instance_id: str,
    feasible: bool,
    objective_key: tuple[float, ...],
    seed: int = 0,
    runtime_s: float = 1.0,
) -> InstanceEval:
    return InstanceEval(
        family=family,
        instance_id=instance_id,
        seed=seed,
        feasible=feasible,
        objective_key=objective_key,
        runtime_s=runtime_s,
    )


def test_schneider_one_vehicle_beats_two_when_both_feasible() -> None:
    """Lexicographic: fewer vehicles always ranks above more, even with worse distance."""
    one = build_panel_evaluation(
        [_row(family="schneider", instance_id="r105C5", feasible=True, objective_key=(1.0, 999.0))]
    )
    two = build_panel_evaluation(
        [_row(family="schneider", instance_id="r105C5", feasible=True, objective_key=(2.0, 100.0))]
    )
    assert panel_is_better(one, two)
    assert compare_panel(one, two) < 0
    # Scalar helper must also not let distance overturn vehicles.
    r1 = EvaluationReportV2(feasible=True, objective=1.0, objective_key=(1.0, 999.0))
    r2 = EvaluationReportV2(feasible=True, objective=2.0, objective_key=(2.0, 100.0))
    assert fitness_from_report(r1, 1.0) > fitness_from_report(r2, 1.0)


def test_incomparable_panels_cannot_outrank_via_easy_instance_only() -> None:
    """A candidate tested only on an easy instance does not beat a fuller panel via scalar luck."""
    easy_only = build_panel_evaluation(
        [_row(family="schneider", instance_id="c101C5", feasible=True, objective_key=(1.0, 10.0))]
    )
    hard_panel = build_panel_evaluation(
        [
            _row(family="schneider", instance_id="c101C5", feasible=True, objective_key=(1.0, 12.0)),
            _row(family="schneider", instance_id="r105C5", feasible=True, objective_key=(2.0, 150.0)),
        ]
    )
    # More feasible instances ranks higher.
    assert panel_is_better(hard_panel, easy_only)


def test_partial_family_feasibility_is_not_universally_feasible() -> None:
    panel = build_panel_evaluation(
        [
            _row(family="schneider", instance_id="c101C5", feasible=True, objective_key=(2.0, 100.0)),
            _row(family="montoya", instance_id="tc0c10s2cf1", feasible=False, objective_key=(99.0,)),
        ]
    )
    assert panel.instances_feasible == 1
    assert panel.fully_feasible_on_panel is False
    cand = BundleCandidate(
        candidate_id="partial",
        sources={},
        owners={},
        generation=0,
    )
    apply_panel(cand, panel, validation_status="ok")
    assert cand.feasible is False
    assert cand.fully_feasible_on_panel is False


def test_infeasible_cannot_be_official_best_feasible() -> None:
    archive = CandidateArchive(capacity=4)
    bad = BundleCandidate(candidate_id="bad", sources={"a": "1"}, owners={}, generation=0)
    apply_panel(
        bad,
        build_panel_evaluation(
            [_row(family="schneider", instance_id="x", feasible=False, objective_key=(3.0, 1.0))]
        ),
        validation_status="ok",
    )
    archive.add(bad)
    assert archive.best() is None
    good = BundleCandidate(candidate_id="good", sources={"a": "2"}, owners={}, generation=1)
    apply_panel(
        good,
        build_panel_evaluation(
            [_row(family="schneider", instance_id="x", feasible=True, objective_key=(2.0, 50.0))]
        ),
        validation_status="ok",
    )
    archive.add(good)
    best = archive.best()
    assert best is not None
    assert best.candidate_id == "good"
    assert best.fully_feasible_on_panel is True


def test_panel_ranking_deterministic() -> None:
    a = build_panel_evaluation(
        [
            _row(family="goeke", instance_id="rc105C6", feasible=True, objective_key=(2.0, 240.0)),
            _row(family="bezzi", instance_id="R105-5", feasible=True, objective_key=(206.0,)),
        ]
    )
    b = build_panel_evaluation(
        [
            _row(family="goeke", instance_id="rc105C6", feasible=True, objective_key=(2.0, 241.0)),
            _row(family="bezzi", instance_id="R105-5", feasible=True, objective_key=(206.0,)),
        ]
    )
    assert compare_panel(a, b) == compare_panel(a, b)
    assert compare_panel(a, b) < 0
    assert compare_panel(a, a) == 0


def test_first_instance_win_does_not_override_panel_majority() -> None:
    """Candidate A narrowly wins instance 1 but loses badly on 2 and 3 → B ranks better.

    Guards against early-exit ranking that only inspects the first ordered instance.
    """
    from evrptw_autolab.components.evolution.fitness import pairwise_panel_score

    # Instance order: a, b, c — A wins only on "a".
    cand_a = build_panel_evaluation(
        [
            _row(family="schneider", instance_id="a", feasible=True, objective_key=(2.0, 100.0)),
            _row(family="schneider", instance_id="b", feasible=True, objective_key=(3.0, 500.0)),
            _row(family="schneider", instance_id="c", feasible=True, objective_key=(3.0, 500.0)),
        ]
    )
    cand_b = build_panel_evaluation(
        [
            _row(family="schneider", instance_id="a", feasible=True, objective_key=(2.0, 101.0)),
            _row(family="schneider", instance_id="b", feasible=True, objective_key=(2.0, 150.0)),
            _row(family="schneider", instance_id="c", feasible=True, objective_key=(2.0, 150.0)),
        ]
    )
    score = pairwise_panel_score(cand_a, cand_b)
    assert score.wins_b == 2
    assert score.wins_a == 1
    assert panel_is_better(cand_b, cand_a)
    assert compare_panel(cand_b, cand_a) < 0


def test_inherited_llm_lineage_counts_after_failed_mutation() -> None:
    from evrptw_autolab.components.evolution.archive import classify_attribution

    lineage = {
        "insertion_score": {
            "llm_generated": True,
            "human_default_used": False,
            "fallback_applied": False,
            "origin_candidate_id": "parent_llm",
        },
        "station_score": {"llm_generated": False, "human_default_used": True},
        "removal_priority": {"llm_generated": False, "human_default_used": True},
    }
    # Current generation mutation failed → attr_rows only show fallbacks.
    attr_rows = [
        {
            "kind": "insertion_score",
            "llm_generated": False,
            "fallback_applied": True,
            "human_default_used": True,
        }
    ]
    # Executed sources still carry the inherited LLM insertion code (non-default text).
    sources = {
        "insertion_score": "def insertion_score(a,b,c,d,e):\n    return a + 0.5\n",
        "station_score": __import__(
            "evrptw_autolab.components.interfaces", fromlist=["DEFAULT_SOURCES"]
        ).DEFAULT_SOURCES["station_score"],
        "removal_priority": __import__(
            "evrptw_autolab.components.interfaces", fromlist=["DEFAULT_SOURCES"]
        ).DEFAULT_SOURCES["removal_priority"],
    }
    category, genuine = classify_attribution(attr_rows, sources, lineage=lineage)
    assert category == "hybrid_llm"
    assert genuine >= 1
