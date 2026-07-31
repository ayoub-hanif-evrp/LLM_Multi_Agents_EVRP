"""Load verified generated plan builders and wrap as ALNS destroy operators."""

from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from evocharge.operators.api import DestroyResult, OperatorContext
from evocharge.operators.generated_api import (
    EntityReference,
    OperatorPlan,
    PlanAction,
    SelectionEvidence,
    RandomSource,
    ReadOnlySearchState,
)
from evocharge.operators.primitives import APPROVED_NAMESPACE, apply_operator_plan
from evocharge.verification.sandbox import run_in_sandbox, validate_plan


def load_candidate_source(candidate_dir: Path) -> str:
    path = Path(candidate_dir) / "source.py"
    if not path.is_file():
        raise FileNotFoundError(f"Missing source.py in {candidate_dir}")
    return path.read_text(encoding="utf-8")


def build_plan_in_sandbox(
    source: str,
    *,
    seed: int,
    timeout_seconds: float = 5.0,
) -> OperatorPlan | None:
    out = run_in_sandbox(
        source,
        operator_type="plan_builder",
        seed=seed,
        timeout_seconds=timeout_seconds,
    )
    if not out.get("ok"):
        return None
    return OperatorPlan.model_validate(out["plan"])


def compile_plan_builder(source: str) -> Callable[..., Any]:
    """Trusted in-process load for statically verified candidates."""
    ns: dict[str, Any] = {
        "OperatorPlan": OperatorPlan,
        "PlanAction": PlanAction,
        "PrimitiveAction": PlanAction,
        "EntityReference": EntityReference,
        "SelectionEvidence": SelectionEvidence,
        "ReadOnlySearchState": ReadOnlySearchState,
        "RandomSource": RandomSource,
        "OperatorContext": object,
        **APPROVED_NAMESPACE,
    }
    # Lightweight query stubs if not in APPROVED_NAMESPACE
    for name in (
        "query_time_slack",
        "query_charging_detour",
        "query_station_dependency",
        "query_energy_slack",
        "query_load_slack",
        "query_route_distance",
        "query_route_duration",
        "select_customers_by_score",
        "select_segments_by_score",
        "select_routes_by_score",
        "select_stations_by_score",
        "plan_station_replacement",
        "plan_segment_relocation",
        "plan_customer_swap",
        "plan_route_removal",
    ):
        if name not in ns:
            if name.startswith("query_"):
                ns[name] = lambda *a, **k: 1.0
            elif name.startswith("select_"):
                ns[name] = lambda candidates, scores=None, k=1, **kw: tuple(
                    list(candidates)[: int(k)]
                )
            elif name.startswith("plan_"):

                def _p(pid=name, *a, **kw):
                    from evocharge.operators.generated_api import PlanAction

                    args = dict(kw)
                    args.pop("action_id", None)
                    if "route_index" not in args:
                        args["route_index"] = int(a[0]) if a else 0
                    return PlanAction(
                        action_id=str(kw.get("action_id", "a")),
                        primitive_id=pid,
                        arguments=args,
                    )

                ns[name] = _p
    exec(compile(source, "<candidate>", "exec"), ns, ns)  # noqa: S102
    fn = ns.get("build_operator_plan")
    if not callable(fn):
        raise ValueError("source missing build_operator_plan")
    return cast(Callable[..., Any], fn)


def make_generated_destroy(
    source: str,
    *,
    operator_name: str = "generated_candidate",
    use_sandbox: bool = True,
) -> Callable[..., DestroyResult]:
    """Wrap a plan builder as a destroy operator that returns a fully applied solution."""
    builder = None if use_sandbox else compile_plan_builder(source)

    def _destroy(solution, context: OperatorContext, rng: random.Random) -> DestroyResult:
        seed = int(rng.random() * 1_000_000)
        try:
            if use_sandbox:
                plan = build_plan_in_sandbox(source, seed=seed)
            else:
                assert builder is not None
                state = ReadOnlySearchState(solution=solution, instance=context.instance)
                plan = builder(state, context, RandomSource(seed))
                if not isinstance(plan, OperatorPlan):
                    plan = OperatorPlan.model_validate(plan)
        except Exception as exc:  # noqa: BLE001 — evaluation must not crash ALNS
            return DestroyResult(
                solution=solution,
                removed_customers=(),
                operator=operator_name,
                metadata={"error": "plan_build_exception", "detail": str(exc)},
            )
        if plan is None:
            return DestroyResult(
                solution=solution,
                removed_customers=(),
                operator=operator_name,
                metadata={"error": "plan_build_failed"},
            )
        state = ReadOnlySearchState(solution=solution, instance=context.instance)
        pv = validate_plan(plan, state=state, max_removals=20)
        if not pv.accepted:
            return DestroyResult(
                solution=solution,
                removed_customers=(),
                operator=operator_name,
                metadata={"error": "plan_invalid", "errors": pv.errors, "plan": plan.model_dump()},
            )
        after = apply_operator_plan(state, context, plan)
        return DestroyResult(
            solution=after,
            removed_customers=(),
            operator=operator_name,
            metadata={
                "plan": plan.model_dump(),
                "n_actions": len(plan.actions),
                "plan_applied": True,
            },
        )

    _destroy.__name__ = operator_name
    return _destroy


def make_noop_destroy() -> Callable[..., DestroyResult]:
    def _noop(solution, context: OperatorContext, rng: random.Random) -> DestroyResult:
        _ = context, rng
        return DestroyResult(
            solution=solution,
            removed_customers=(),
            operator="noop_control",
            metadata={"plan_nonempty": False},
        )

    return _noop
