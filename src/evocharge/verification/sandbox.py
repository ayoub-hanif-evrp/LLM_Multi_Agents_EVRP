"""Plan validation and sandbox execution for generated operators."""

from __future__ import annotations

import multiprocessing as mp
import traceback
from typing import Any, Literal

from pydantic import BaseModel, Field

from evocharge.operators.generated_api import (
    OperatorPlan,
    RandomSource,
    ReadOnlySearchState,
)
from evocharge.operators.primitives import PRIMITIVE_IDS


def _as_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        return int(value)
    return default


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return [str(value)]


class PlanValidationReport(BaseModel):
    accepted: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    estimated_work: int = 0


class DynamicVerificationReport(BaseModel):
    accepted: bool
    level_results: dict[str, bool] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    runtime_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""


def validate_plan(
    plan: OperatorPlan,
    *,
    state: ReadOnlySearchState,
    max_removals: int = 20,
    allowed_primitives: set[str] | None = None,
) -> PlanValidationReport:
    allowed = allowed_primitives or PRIMITIVE_IDS
    errors: list[str] = []
    warnings: list[str] = []
    customers = set(state.instance.customer_ids)
    stations = set(state.instance.station_ids)
    removals = 0
    seen_actions: set[str] = set()

    from evocharge.verification.semantic_plan import validate_plan_semantics

    sem = validate_plan_semantics(plan)
    errors.extend(sem.errors)
    warnings.extend(sem.warnings)
    if not plan.applicable:
        return PlanValidationReport(
            accepted=not errors,
            errors=sorted(set(errors)),
            warnings=sorted(set(warnings)),
            estimated_work=0,
        )

    for action in plan.actions:
        if action.action_id in seen_actions:
            errors.append(f"duplicate_action_id:{action.action_id}")
        seen_actions.add(action.action_id)
        if action.primitive_id not in allowed:
            errors.append(f"primitive_not_permitted:{action.primitive_id}")
        args = dict(action.arguments)
        if "route_id" in args and "route_index" not in args:
            args["route_index"] = args["route_id"]
        if action.primitive_id == "plan_customer_removal":
            ids = _as_str_list(args.get("customer_ids"))
            removals += len(ids)
            for cid in ids:
                if cid not in customers:
                    errors.append(f"unknown_customer:{cid}")
        if action.primitive_id == "plan_segment_removal":
            ri = _as_int(args.get("route_index"), -1)
            if ri < 0 or ri >= len(state.solution.routes):
                errors.append(f"bad_route_index:{ri}")
            else:
                start = _as_int(args.get("start_index"), 0)
                end = _as_int(args.get("end_index"), 0)
                route = state.solution.routes[ri]
                cust_ids = set(state.instance.customer_ids)
                segment_custs = [
                    n for n in route.node_ids[start:end] if n in cust_ids
                ]
                if start == 0 and end == 1 and not segment_custs:
                    errors.append("depot_only_segment_slice")
                removals += len(segment_custs)
        if action.primitive_id in {
            "plan_station_removal",
            "plan_station_replacement",
        }:
            sid = str(
                args.get("station_id")
                or args.get("old_station_id")
                or ""
            )
            if sid and sid not in stations:
                errors.append(f"unknown_station:{sid}")
            ri = _as_int(args.get("route_index"), -1)
            if ri < 0 or ri >= len(state.solution.routes):
                errors.append(f"bad_route_index:{ri}")
            if action.primitive_id == "plan_station_replacement":
                old = str(args.get("old_station_id") or args.get("station_id") or "")
                new = str(args.get("new_station_id") or "")
                if old and new and old == new:
                    errors.append("identical_station_replacement")
                if ri >= 0 and ri < len(state.solution.routes) and old:
                    route_stations = {
                        n
                        for n in state.solution.routes[ri].node_ids
                        if n in stations
                    }
                    if old not in route_stations:
                        errors.append(f"station_not_on_route:{old}")
        if action.primitive_id == "plan_charging_reconstruction":
            ri = _as_int(args.get("route_index"), -1)
            if ri < 0 or ri >= len(state.solution.routes):
                errors.append(f"bad_route_index:{ri}")

    if removals > max_removals:
        errors.append(f"too_many_removals:{removals}")
    if plan.estimated_removals > max_removals:
        warnings.append("estimated_removals_high")

    return PlanValidationReport(
        accepted=not errors,
        errors=sorted(set(errors)),
        warnings=sorted(set(warnings)),
        estimated_work=removals + len(plan.actions),
    )


def _sandbox_worker(payload: dict[str, Any], queue: Any) -> None:
    """Child process entry: execute generated function in restricted builtins."""
    try:
        source = payload["source"]
        op_type = payload["operator_type"]
        seed = int(payload.get("seed", 0))
        # Minimal builtins
        safe_builtins = {
            "len": len,
            "min": min,
            "max": max,
            "sum": sum,
            "abs": abs,
            "float": float,
            "int": int,
            "str": str,
            "bool": bool,
            "tuple": tuple,
            "list": list,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "sorted": sorted,
            "True": True,
            "False": False,
            "None": None,
        }
        # Stub primitives that return plans/scores without solver access
        stubs: dict[str, Any] = {}

        def _plan(pid: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raw = dict(kwargs)
            # Normalize common LLM aliases into catalogue argument names.
            if "route_id" in raw and "route_index" not in raw:
                raw["route_index"] = raw.pop("route_id")
            if "station" in raw and "station_id" not in raw:
                raw["station_id"] = raw.pop("station")
            if "customers" in raw and "customer_ids" not in raw:
                raw["customer_ids"] = raw.pop("customers")
            if "top_k" in raw and "k" not in raw:
                raw["k"] = raw.pop("top_k")
            # Positional fallbacks for common plan forms
            if pid == "plan_charging_reconstruction" and "route_index" not in raw:
                raw["route_index"] = int(args[0]) if args else 0
            if pid == "plan_customer_removal" and "customer_ids" not in raw and args:
                raw["customer_ids"] = list(args[0]) if not isinstance(args[0], str) else [args[0]]
            if pid == "plan_regret_reinsertion" and "customer_ids" not in raw and args:
                raw["customer_ids"] = list(args[0]) if not isinstance(args[0], str) else [args[0]]
            if pid == "plan_station_removal" and "route_index" not in raw:
                if args:
                    raw["route_index"] = int(args[0])
                if len(args) > 1 and "station_id" not in raw:
                    raw["station_id"] = str(args[1])
            if pid == "plan_station_replacement":
                if "route_index" not in raw:
                    raw["route_index"] = int(args[0]) if args else 0
                if "old_station_id" not in raw and "station_id" in raw:
                    raw["old_station_id"] = raw["station_id"]
                if "new_station_id" not in raw:
                    raw["new_station_id"] = str(raw.get("old_station_id") or "S1")
            if pid == "plan_segment_removal" and "route_index" not in raw:
                if args:
                    # allow segment tuple/dict or route_index
                    first = args[0]
                    if isinstance(first, dict):
                        raw.update({k: first[k] for k in first if k in {
                            "route_index", "start_index", "end_index"
                        }})
                    else:
                        raw["route_index"] = 0
                        raw["start_index"] = 1
                        raw["end_index"] = 2
            action_id = str(raw.pop("action_id", pid))
            if "route_index" not in raw:
                raw["route_index"] = 0
            return {
                "action_id": action_id,
                "primitive_id": pid,
                "arguments": raw,
                "rationale": "",
            }

        def _select(*args: Any, **kwargs: Any) -> tuple[Any, ...]:
            candidates = kwargs.get("candidates")
            scores = kwargs.get("scores")
            if candidates is None and args:
                candidates = args[0]
            if scores is None and len(args) > 1:
                scores = args[1]
            k = kwargs.get("k", kwargs.get("top_k", kwargs.get("n")))
            if k is None and len(args) > 2:
                k = args[2]
            if k is None:
                k = 1
            try:
                k_int = int(k)
            except (TypeError, ValueError):
                k_int = 1
            # If LLM passed (state, score_scalar) instead of candidates/scores
            if not isinstance(candidates, (list, tuple)):
                return ("C0",)[: max(0, k_int)]
            if not isinstance(scores, (list, tuple)):
                scores = [float(scores or 0.0)] * len(candidates)
            ranked = sorted(
                zip(scores, candidates, strict=False),
                key=lambda t: float(t[0]) if isinstance(t[0], (int, float)) else 0.0,
                reverse=True,
            )
            out: list[Any] = []
            for _, c in ranked[: max(0, k_int)]:
                if isinstance(c, dict):
                    out.append(c.get("entity_id", "C0"))
                else:
                    out.append(getattr(c, "entity_id", str(c)))
            return tuple(out)

        for pid in PRIMITIVE_IDS:
            if pid.startswith("plan_"):
                stubs[pid] = lambda *a, pid=pid, **kw: _plan(pid, *a, **kw)
            elif pid.startswith("query_"):
                stubs[pid] = lambda *a, pid=pid, seed=seed, **k: float(
                    1.0 + (seed % 7) * 0.01 + (len(a) * 0.001)
                )
            elif pid.startswith("select_"):
                stubs[pid] = _select
            elif pid.startswith("identify_"):
                stubs[pid] = lambda *a, **k: (0, 1)
            else:
                stubs[pid] = lambda *a, **k: None

        class _Plan:
            def __init__(
                self,
                actions=None,
                notes=None,
                estimated_removals=0,
                plan_version="1.1.0",
                applicable=True,
                no_action_reason=None,
                preconditions_checked=None,
                selected_entities=None,
                selection_evidence=None,
                expected_behavioral_effect="",
            ):
                self.actions = actions or []
                self.notes = notes or []
                self.estimated_removals = estimated_removals
                self.plan_version = plan_version
                self.applicable = applicable
                self.no_action_reason = no_action_reason
                self.preconditions_checked = preconditions_checked or []
                self.selected_entities = selected_entities or []
                self.selection_evidence = selection_evidence or []
                self.expected_behavioral_effect = expected_behavioral_effect

            def model_dump(self) -> dict[str, Any]:
                def _dump_ent(e: Any) -> dict[str, Any]:
                    if isinstance(e, dict):
                        return e
                    return {
                        "entity_type": getattr(e, "entity_type", "customer"),
                        "entity_id": getattr(e, "entity_id", ""),
                        "route_index": getattr(e, "route_index", None),
                        "start_index": getattr(e, "start_index", None),
                        "end_index": getattr(e, "end_index", None),
                    }

                def _dump_ev(e: Any) -> dict[str, Any]:
                    if isinstance(e, dict):
                        return e
                    return {
                        "entity_id": getattr(e, "entity_id", ""),
                        "query_id": getattr(e, "query_id", ""),
                        "score": float(getattr(e, "score", 0.0)),
                        "rationale": getattr(e, "rationale", ""),
                    }

                acts = []
                for a in self.actions:
                    if isinstance(a, dict):
                        acts.append(a)
                    else:
                        acts.append(
                            {
                                "action_id": getattr(a, "action_id", "a"),
                                "primitive_id": getattr(a, "primitive_id", ""),
                                "arguments": getattr(a, "arguments", {}),
                                "rationale": getattr(a, "rationale", ""),
                            }
                        )
                return {
                    "plan_version": self.plan_version,
                    "applicable": bool(self.applicable),
                    "no_action_reason": self.no_action_reason,
                    "preconditions_checked": list(self.preconditions_checked),
                    "selected_entities": [_dump_ent(e) for e in self.selected_entities],
                    "selection_evidence": [_dump_ev(e) for e in self.selection_evidence],
                    "actions": acts,
                    "expected_behavioral_effect": self.expected_behavioral_effect,
                    "notes": list(self.notes),
                    "estimated_removals": int(self.estimated_removals),
                }

        class _Action:
            def __init__(self, action_id="", primitive_id="", arguments=None, rationale=""):
                self.action_id = action_id
                self.primitive_id = primitive_id
                self.arguments = arguments or {}
                self.rationale = rationale

        class _EntityRef:
            def __init__(
                self,
                entity_type="customer",
                entity_id="",
                route_index=None,
                start_index=None,
                end_index=None,
            ):
                self.entity_type = entity_type
                self.entity_id = entity_id
                self.route_index = route_index
                self.start_index = start_index
                self.end_index = end_index

        class _Evidence:
            def __init__(self, entity_id="", query_id="", score=0.0, rationale=""):
                self.entity_id = entity_id
                self.query_id = query_id
                self.score = score
                self.rationale = rationale

        # Prefer real tiny instance so state queries work in-process sandbox
        from evocharge.domain.solution import Solution
        from evocharge.operators.generated_api import (
            EntityCandidate as RealEntityCandidate,
        )
        from evocharge.operators.generated_api import (
            EntityReference as RealEntityReference,
        )
        from evocharge.operators.generated_api import (
            ReadOnlySearchState as RealState,
        )
        from evocharge.operators.generated_api import (
            SelectionEvidence as RealSelectionEvidence,
        )
        from evocharge.operators.primitives import APPROVED_NAMESPACE
        from evocharge.solver.construction import construct_initial_solution
        from evocharge.verification.synth import make_tiny_instance

        tiny = make_tiny_instance()
        constructed = construct_initial_solution(tiny)
        sol = constructed.solution or Solution(routes=())
        real_state = RealState(solution=sol, instance=tiny)

        ns: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "OperatorPlan": _Plan,
            "PlanAction": _Action,
            "PrimitiveAction": _Action,
            "EntityCandidate": RealEntityCandidate,
            "EntityReference": RealEntityReference,
            "SelectionEvidence": RealSelectionEvidence,
            "OperatorContext": object,
            "ReadOnlySearchState": object,
            "RandomSource": object,
            **stubs,
            **APPROVED_NAMESPACE,
        }
        exec(compile(source, "<generated>", "exec"), ns, ns)  # noqa: S102 - sandbox child
        if op_type == "scoring":
            fn = ns["score_entities"]
            candidates = payload.get("candidates") or []
            # candidates as simple namespace objects
            class C:
                def __init__(self, d: dict[str, Any]) -> None:
                    self.__dict__.update(d)

            cand_objs = tuple(C(c) if isinstance(c, dict) else c for c in candidates)
            scores = fn(object(), cand_objs)
            queue.put({"ok": True, "scores": list(scores), "stdout": "", "stderr": ""})
        else:
            fn = ns["build_operator_plan"]
            rng = RandomSource(seed)

            class Ctx:
                pass

            result = fn(real_state, Ctx(), rng)
            if hasattr(result, "model_dump"):
                plan = result.model_dump()
            elif isinstance(result, dict):
                plan = result
            else:
                plan = _Plan(
                    actions=getattr(result, "actions", []),
                    notes=getattr(result, "notes", []),
                    estimated_removals=getattr(result, "estimated_removals", 0),
                    applicable=getattr(result, "applicable", True),
                    no_action_reason=getattr(result, "no_action_reason", None),
                    preconditions_checked=getattr(result, "preconditions_checked", []),
                    selected_entities=getattr(result, "selected_entities", []),
                    selection_evidence=getattr(result, "selection_evidence", []),
                    expected_behavioral_effect=getattr(
                        result, "expected_behavioral_effect", ""
                    ),
                ).model_dump()
            queue.put({"ok": True, "plan": plan, "stdout": "", "stderr": ""})
    except Exception as exc:  # noqa: BLE001
        queue.put(
            {
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "stdout": "",
                "stderr": "",
            }
        )


def run_in_sandbox(
    source: str,
    *,
    operator_type: Literal["scoring", "plan_builder"],
    candidates: list[dict[str, Any]] | None = None,
    seed: int = 0,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Execute generated code in a spawned child process.

    Research sandbox, not a perfect security boundary.
    """
    ctx = mp.get_context("spawn")
    queue: mp.Queue[dict[str, Any]] = ctx.Queue()
    payload = {
        "source": source,
        "operator_type": operator_type,
        "candidates": candidates or [],
        "seed": seed,
    }
    proc = ctx.Process(target=_sandbox_worker, args=(payload, queue))
    proc.start()
    proc.join(timeout_seconds)
    if proc.is_alive():
        proc.terminate()
        proc.join(1.0)
        if proc.is_alive():
            proc.kill()
            proc.join(1.0)
        return {
            "ok": False,
            "error": "timeout",
            "timeout": True,
            "stdout": "",
            "stderr": "",
        }
    if not queue.empty():
        return queue.get()
    return {"ok": False, "error": "no_result", "stdout": "", "stderr": ""}
