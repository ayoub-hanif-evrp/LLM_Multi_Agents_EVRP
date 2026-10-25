"""B0–B6 on one family. Scripted arms are not a live-model result."""

from __future__ import annotations

import random
from typing import Any

from evrptw_autolab.backbone.alns import repair_greedy
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.discovery.schemas import OperatorSpec
from evrptw_autolab.problem.v2.types import ProblemSpecV2, SolutionV2
from evrptw_autolab.transfer.applicability import ApplicabilityExample, fit_stump
from evrptw_autolab.transfer.counterexamples import refuse_non_development

FINAL_TEST_BLOCKED = (
    "No untouched final set is declared. Schneider RC2 was already inspected and is not a blind test."
)
CANDIDATE_EXPRESSIONS = (
    "delta_distance",
    "-1 * delta_distance",
    "delta_distance + incremental_energy_cost",
)
MIN_SIGNIFICANCE_N = 5


def significance_allowed(sample_size: int) -> bool:
    return sample_size >= MIN_SIGNIFICANCE_N


def refuse_heldout_selection(partition: str) -> None:
    if partition == "heldout":
        raise RuntimeError(FINAL_TEST_BLOCKED)
    refuse_non_development(partition)


def _operator(scoring: str, rule: str, *, operator_id: str, mine: bool = True) -> OperatorSpec:
    return OperatorSpec(
        operator_id=operator_id,
        version="1",
        source_agent="comparison",
        description=scoring,
        operator_family="repair",
        implementation_reference="repair_greedy",
        required_capabilities=["time_windows"],
        applicability_rule=rule,
        candidate_scoring_policy=scoring,
        mine_counterexamples=mine,
        fallback_operator="classical_default",
    )


def _objective(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    operator: OperatorSpec | None,
    *,
    seed: int,
    partition: str,
) -> tuple[tuple[float, ...], dict[str, Any]]:
    repaired = repair_greedy(spec, solution, removed, random.Random(seed), operator, partition=partition)
    report = evaluate(spec, repaired)
    return tuple(float(value) for value in report.objective_key), repaired.metadata


def scripted_report() -> dict[str, Any]:
    from evrptw_autolab.research.panel import development_case

    spec, solution, removed = development_case()
    return run_comparison(spec, solution, removed, partition="development", seed=1)


def run_comparison(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    *,
    partition: str,
    seed: int = 1,
) -> dict[str, Any]:
    """Evaluate every arm on the same repair state. Selection uses only this partition."""
    refuse_heldout_selection(partition)
    baseline, _ = _objective(spec, solution, removed, None, seed=seed, partition=partition)
    pool = [
        _objective(spec, solution, removed, _operator(expr, "1", operator_id=f"pool-{index}"), seed=seed, partition=partition)
        for index, expr in enumerate(CANDIDATE_EXPRESSIONS)
    ]
    examples: list[ApplicabilityExample] = []
    context = {"route_utilization": 0.2, "customer_count": 3.0, "route_count": 1.0, "station_count": 0.0}
    for objective, _meta in pool:
        examples.append(
            ApplicabilityExample(
                features=dict(context),
                improved=bool(objective < baseline),
                partition=partition,
            )
        )
    stump = fit_stump(examples)
    arms: dict[str, tuple[float, ...]] = {"B0": baseline}
    arms["B1"] = min(objective for objective, _meta in pool)
    harmful = pool[1][0]
    safe = pool[0][0]
    arms["B2"] = safe if harmful > baseline else harmful
    arms["B3"] = harmful
    arms["B4"] = safe
    fallback = _operator("delta_distance", stump.rule(), operator_id="selective")
    arms["B5"], _ = _objective(spec, solution, removed, fallback, seed=seed, partition=partition)
    arms["B6"], _ = _objective(
        spec,
        solution,
        removed,
        _operator("delta_distance", stump.rule(), operator_id="contextual"),
        seed=seed,
        partition=partition,
    )
    paired = {
        name: _relation(objective, baseline)
        for name, objective in arms.items()
        if name != "B0"
    }
    return {
        "family": spec.family,
        "instance_id": spec.instance_id,
        "partition": partition,
        "seed": seed,
        "llm_calls": 0,
        "backend": "scripted",
        "objectives": {name: list(value) for name, value in arms.items()},
        "paired_against_b0": paired,
        "applicability_rule": stump.rule(),
        "significant": significance_allowed(1),
        "final_test": FINAL_TEST_BLOCKED,
    }


def evaluate_frozen(
    spec: ProblemSpecV2,
    solution: SolutionV2,
    removed: list[tuple[str, ...]],
    scoring: str,
    rule: str,
    *,
    seed: int,
    partition: str,
) -> tuple[float, ...]:
    """Score a frozen operator. The rule is not refit."""
    if partition == "heldout":
        raise RuntimeError(FINAL_TEST_BLOCKED)
    objective, _meta = _objective(
        spec,
        solution,
        removed,
        _operator(scoring, rule, operator_id="frozen", mine=False),
        seed=seed,
        partition=partition,
    )
    return objective


def _relation(candidate: tuple[float, ...], baseline: tuple[float, ...]) -> str:
    if candidate < baseline:
        return "win"
    if candidate > baseline:
        return "loss"
    return "tie"
