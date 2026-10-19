"""Four-arm pilot with equal candidate evaluation counts.

Classical is one deployment of the default policy. Random, single-agent, and
five-agent each receive ``SEARCH_CANDIDATES`` bundle evaluations on the same
instances, seed, time limits, and iteration caps. Each search candidate
replaces one scheduled component. The five-agent critic is an extra model
call and does not add a solver evaluation.

Selection keeps the conservatively accepted candidate with the most wins.
An earlier candidate wins a tie. The robust rule is recorded and is not used
to choose the deployed bundle.
"""
from __future__ import annotations

import json
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evrptw_autolab.agents.base import extract_json
from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.backbone.util import evaluate
from evrptw_autolab.components.expressions import (
    ARGUMENT_NAMES_V3,
    EXPRESSION_EXAMPLES,
    argument_names,
    materialize_component,
    repair_prompt,
    wrap_expression,
)
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.loader import load_bundle, validate_component_source
from evrptw_autolab.experiments.bundle_selection import (
    conservative_decision,
    random_component_expression,
    robust_decision,
)
from evrptw_autolab.experiments.fair_budget import (
    DECLARED_SELECTION_RULE,
    SEARCH_CANDIDATES,
    solver_passes,
)
from evrptw_autolab.experiments.family_gate import gate_panel
from evrptw_autolab.experiments.policy_sensitivity import paired_feasible_outcome
from evrptw_autolab.llm.usage import UsageCollector
from evrptw_autolab.problem.v2.features import (
    FEATURE_SCHEMA_V3,
    FEATURE_SCHEMA_VERSION,
    feature_schema_prompt,
    insertion_feature_prompt,
    normalize_feature_schema,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2

KINDS: tuple[ComponentKind, ...] = ("insertion_score", "station_score", "removal_priority")
ROOT = Path(__file__).resolve().parents[3]


@dataclass
class PanelItem:
    family: str
    instance_id: str
    spec: ProblemSpecV2
    time_limit_s: float
    alns_iterations: int


@dataclass
class MatchedPilotConfig:
    seed: int = 7
    fake: bool = True
    profile: str = "qwen3_coder_30b"
    candidates: int = SEARCH_CANDIDATES
    micro: bool = False
    time_limit_s: float | None = None
    alns_iterations: int | None = None
    out_dir: Path | None = None
    max_llm_calls: int = 80
    max_llm_tokens: int | None = 80_000
    use_critic: bool = True
    apply_selection: bool = True
    ablation: str = "primary"


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _panel(cfg: MatchedPilotConfig) -> list[PanelItem]:
    if cfg.micro:
        from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
        from evrptw_autolab.problem.micro import micro_g1_one_customer

        spec = load_schneider_v2(micro_g1_one_customer().metadata["source_path"])
        return [
            PanelItem(
                "schneider",
                spec.instance_id,
                spec,
                float(cfg.time_limit_s if cfg.time_limit_s is not None else 1.0),
                int(cfg.alns_iterations if cfg.alns_iterations is not None else 5),
            )
        ]
    items: list[PanelItem] = []
    for item in gate_panel():
        items.append(
            PanelItem(
                item.family,
                item.instance_id,
                item.loader(item.path),
                float(cfg.time_limit_s if cfg.time_limit_s is not None else item.time_limit_s),
                int(cfg.alns_iterations if cfg.alns_iterations is not None else item.alns_iterations),
            )
        )
    return items


_OBJECTIVES = {
    "schneider": "minimize vehicle count, then travel distance",
    "goeke": "minimize vehicle count, then travel distance",
    "montoya": "minimize total route duration",
    "bezzi": "minimize recharge cost",
    "hiermann": "minimize fixed vehicle cost plus fuel and electricity cost",
    "micro": "minimize travel distance on a synthetic instance",
}

_OBJECTIVE_WORDS = (
    "vehicle",
    "distance",
    "duration",
    "recharge",
    "battery",
    "fleet",
    "charge",
    "energy",
    "capacity",
    "cost",
    "time window",
)


def _routing_brief(panel: list[Any], schema: str | None = None) -> str:
    """State the native objective and constraints. This is not a software-performance task."""
    lines = [
        "You are scoring routes for an electric-vehicle routing problem.",
        "A feasible route must respect capacity, battery, and charging limits.",
        "Time windows apply only when the instance has them. A due time of 1000000 means there is no useful window.",
        "Do not discuss insertion speed, data structures, memory, or software resources.",
    ]
    seen: set[str] = set()
    for item in panel:
        family = str(getattr(item, "family", ""))
        if family in seen:
            continue
        seen.add(family)
        objective = _OBJECTIVES.get(family, "minimize the family's native objective")
        caps = getattr(getattr(item, "spec", None), "capabilities", None)
        flags: list[str] = []
        if caps is not None:
            if caps.time_windows:
                flags.append("time windows")
            if caps.capacity:
                flags.append("capacity")
            if caps.battery:
                flags.append("battery")
            if caps.heterogeneous_fleet:
                flags.append("heterogeneous fleet and vehicle fixed cost")
            if caps.partial_recharge:
                flags.append("partial recharge")
            if caps.multiple_charge_technologies:
                flags.append("multiple charging technologies")
            if caps.pickup_delivery:
                flags.append("pickup and delivery")
        instance_id = str(getattr(item, "instance_id", ""))
        lines.append(
            f"{family} {instance_id}: {objective}. Constraints: {', '.join(flags) or 'see the instance'}."
        )
    lines.append(
        "Allowed insertion names: " + ", ".join(argument_names("insertion_score", schema)) + "."
    )
    if schema == FEATURE_SCHEMA_V3:
        lines.append(insertion_feature_prompt())
    return "\n".join(lines)


def _hypothesis_grounded(text: str) -> bool:
    """A usable hypothesis names one scoring feature and the routing objective it should change."""
    lowered = text.lower()
    names = [name for kind_names in ARGUMENT_NAMES_V3.values() for name in kind_names]
    has_feature = any(name in lowered for name in names)
    has_objective = any(word in lowered for word in _OBJECTIVE_WORDS)
    return has_feature and has_objective


def _expression_prompt(kind: ComponentKind, *, context: str, schema: str | None = None) -> str:
    names = ", ".join(argument_names(kind, schema))
    schema_text = feature_schema_prompt() + "\n" if kind == "station_score" else ""
    return (
        "Return one arithmetic expression for an electric-vehicle routing score. "
        f"Component: {kind}. No def, no imports, no assignments.\n"
        f"Allowed names: {names}. Allowed calls: abs min max float int round.\n"
        f"Example: {EXPRESSION_EXAMPLES[kind]}\n"
        f"{schema_text}"
        + (insertion_feature_prompt() + "\n" if schema == FEATURE_SCHEMA_V3 else "")
        + f"{context}\n"
        + '{"component":"'
        + kind
        + '","expression":"...","rationale":"...","mechanism":"expression"}'
    )


def _accept_expression(
    kind: ComponentKind,
    payload: dict[str, Any],
    collector: UsageCollector,
    backend: Any,
    model: str,
    schema: str | None = None,
) -> tuple[str, dict[str, Any]]:
    code, status = materialize_component(kind, payload, schema)
    ok = bool(code) and bool(validate_component_source(kind, code).get("ok"))
    if not ok:
        repaired = extract_json(
            collector.complete(
                backend,
                prompt=repair_prompt(kind, status),
                role="unified",
                temperature=0.0,
                model=model,
                json_mode=True,
            )
        )
        code, status = materialize_component(kind, repaired, schema)
        ok = bool(code) and bool(validate_component_source(kind, code).get("ok"))
    if not ok:
        code = DEFAULT_SOURCES[kind]
    generated = ok and code.strip() != DEFAULT_SOURCES[kind].strip()
    return code, {
        "component": kind,
        "status": status if ok else f"fallback:{status}",
        "llm_generated": generated,
        "source": code,
    }


_COMPONENT_ROLES: dict[ComponentKind, str] = {
    "insertion_score": "routing",
    "station_score": "charging",
    "removal_priority": "search",
}


def _propose_component(
    collector: UsageCollector,
    backend: Any,
    model: str,
    kind: ComponentKind,
    *,
    context: str,
    schema: str | None = None,
) -> tuple[str, dict[str, Any], str]:
    """Ask for one component expression. The caller copies the parent bundle."""
    raw = collector.complete(
        backend,
        prompt=_expression_prompt(kind, context=context, schema=schema),
        role=_COMPONENT_ROLES[kind],
        temperature=0.4,
        model=model,
        json_mode=True,
    )
    payload = extract_json(raw)
    code, row = _accept_expression(kind, payload, collector, backend, model, schema)
    row["agent_role"] = _COMPONENT_ROLES[kind]
    resolved = schema or FEATURE_SCHEMA_VERSION
    if kind == "station_score" and row["llm_generated"] and resolved == FEATURE_SCHEMA_VERSION:
        resolved = normalize_feature_schema(payload.get("feature_schema"))
    return code, row, resolved


def _propose_unified_component(
    collector: UsageCollector,
    backend: Any,
    model: str,
    kind: ComponentKind,
    *,
    context: str,
    schema: str | None = None,
) -> tuple[str, dict[str, Any], str]:
    """One designer proposes the scheduled component. No specialist role is used."""
    raw = collector.complete(
        backend,
        prompt=(
            "You are one unified electric-vehicle routing designer. "
            + _expression_prompt(kind, context=context, schema=schema)
        ),
        role="unified",
        temperature=0.4,
        model=model,
        json_mode=True,
    )
    payload = extract_json(raw)
    code, row = _accept_expression(kind, payload, collector, backend, model, schema)
    row["agent_role"] = "unified"
    resolved = schema or FEATURE_SCHEMA_VERSION
    if kind == "station_score" and row["llm_generated"] and resolved == FEATURE_SCHEMA_VERSION:
        resolved = normalize_feature_schema(payload.get("feature_schema"))
    return code, row, resolved


def _architect_text(
    collector: UsageCollector,
    backend: Any,
    model: str,
    *,
    context: str,
) -> dict[str, Any]:
    """Ask for a routing hypothesis. A hypothesis that names no feature is not passed downstream."""
    prompt = (
        "You are the Architect for an electric-vehicle routing heuristic.\n"
        "State one testable hypothesis about the scheduled scoring component.\n"
        "Name one allowed feature and the native objective you expect to improve.\n"
        "Do not write the expression. Do not discuss software speed or data structures.\n"
        'Return JSON: {"hypothesis":"...","prediction":"...","feature":"..."}\n'
        + context
    )
    raw = collector.complete(
        backend,
        prompt=prompt,
        role="architect",
        temperature=0.3,
        model=model,
        json_mode=True,
    )
    plan = extract_json(raw)
    text = str(plan.get("hypothesis") or plan.get("summary") or "")
    grounded = _hypothesis_grounded(text)
    if not grounded:
        raw = collector.complete(
            backend,
            prompt=(
                "The previous hypothesis was rejected because it did not name both an allowed "
                "routing feature and the native objective.\n"
                + prompt
            ),
            role="architect",
            temperature=0.0,
            model=model,
            json_mode=True,
        )
        plan = extract_json(raw)
        text = str(plan.get("hypothesis") or "")
        grounded = _hypothesis_grounded(text)
    return {"hypothesis": text, "grounded": grounded, "prediction": str(plan.get("prediction") or "")}


def _propose_single(
    collector: UsageCollector,
    backend: Any,
    model: str,
    *,
    families: list[str],
    index: int,
    feedback: str = "",
) -> tuple[dict[ComponentKind, str], list[dict[str, Any]], str]:
    raw = collector.complete(
        backend,
        prompt=(
            "You are one unified heuristic designer. Return JSON with an arithmetic "
            "expression for each of insertion_score, station_score, and removal_priority. "
            f"Candidate {index}. Families={families}. "
            f"Parent measurements: {feedback or 'none yet'}. "
            + feature_schema_prompt()
            + '\n{"feature_schema":"2026-10-18.v1","components":['
            '{"component":"insertion_score","expression":"delta_distance"},'
            '{"component":"station_score","expression":"detour"},'
            '{"component":"removal_priority","expression":"due_time"}]}'
        ),
        role="unified",
        temperature=0.4,
        model=model,
        json_mode=True,
    )
    payload = extract_json(raw)
    listed = payload.get("components")
    by_kind: dict[str, dict[str, Any]] = {}
    if isinstance(listed, list):
        for entry in listed:
            if isinstance(entry, dict) and entry.get("component"):
                by_kind[str(entry["component"])] = entry
    sources: dict[ComponentKind, str] = {}
    attribution: list[dict[str, Any]] = []
    for kind in KINDS:
        code, row = _accept_expression(kind, by_kind.get(kind, {}), collector, backend, model)
        sources[kind] = code
        attribution.append(row)
    schema = normalize_feature_schema(payload.get("feature_schema"))
    if schema != FEATURE_SCHEMA_VERSION and not any(
        row["component"] == "station_score" and row["llm_generated"] for row in attribution
    ):
        schema = FEATURE_SCHEMA_VERSION
    return sources, attribution, schema


def _propose_five(
    collector: UsageCollector,
    backend: Any,
    model: str,
    *,
    families: list[str],
    index: int,
    critic_text: str,
) -> tuple[dict[ComponentKind, str], list[dict[str, Any]], str, dict[str, Any]]:
    plan_raw = collector.complete(
        backend,
        prompt=(
            "You are the Architect. Propose one testable hypothesis and which components "
            "to change. Return JSON with summary, components, and hypothesis. "
            f"Candidate {index}. Families={families}. Prior critic: {critic_text}"
        ),
        role="architect",
        temperature=0.3,
        model=model,
        json_mode=True,
    )
    plan = extract_json(plan_raw)
    hypothesis = str(plan.get("hypothesis") or plan.get("summary") or "")
    sources: dict[ComponentKind, str] = {}
    attribution: list[dict[str, Any]] = []
    schema = FEATURE_SCHEMA_VERSION
    context = f"Hypothesis: {hypothesis}\nPrior critic: {critic_text}"
    for kind in KINDS:
        role = {"insertion_score": "routing", "station_score": "charging", "removal_priority": "search"}[kind]
        raw = collector.complete(
            backend,
            prompt=_expression_prompt(kind, context=context),
            role=role,
            temperature=0.4,
            model=model,
            json_mode=True,
        )
        payload = extract_json(raw)
        code, row = _accept_expression(kind, payload, collector, backend, model)
        sources[kind] = code
        row["agent_role"] = role
        attribution.append(row)
        if kind == "station_score" and row["llm_generated"]:
            schema = normalize_feature_schema(payload.get("feature_schema"))
    return sources, attribution, schema, {"hypothesis": hypothesis, "summary": str(plan.get("summary") or "")}


def _comparison_summary(
    rows: list[dict[str, Any]],
    baseline: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    base = {str(row["instance_id"]): row for row in baseline or []}
    summary = []
    for row in rows:
        other = base.get(str(row["instance_id"]))
        summary.append(
            {
                "instance_id": row["instance_id"],
                "candidate_feasible": row["feasible"],
                "candidate_key": row["objective_key"],
                "candidate_fault": row["first_fault"],
                "classical_feasible": None if other is None else other["feasible"],
                "classical_key": None if other is None else other["objective_key"],
            }
        )
    return summary


def _critic(
    collector: UsageCollector,
    backend: Any,
    model: str,
    rows: list[dict[str, Any]],
    baseline: list[dict[str, Any]] | None = None,
) -> str:
    summary = _comparison_summary(rows, baseline)
    raw = collector.complete(
        backend,
        prompt=(
            "You are the Critic. Explain feasibility failures, regressions, and stagnation "
            "from these paired rows. Return JSON with verdict, reason, and next_component.\n"
            + json.dumps(summary)
        ),
        role="critic",
        temperature=0.2,
        model=model,
        json_mode=True,
    )
    data = extract_json(raw)
    return str(data.get("reason") or data.get("verdict") or "")


def _evaluate(
    arm: str,
    candidate_id: str,
    sources: dict[ComponentKind, str],
    schema: str,
    panel: list[PanelItem],
    seed: int,
    *,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    owners = {kind: "matched_pilot" for kind in sources}
    bundle, errors = load_bundle(sources, owners, feature_schema=schema)
    rows: list[dict[str, Any]] = []
    for item in panel:
        started = time.monotonic()
        solution = solve_classical(
            item.spec,
            seed=seed,
            time_limit_s=item.time_limit_s,
            alns_iterations=item.alns_iterations,
            policy=bundle,
        )
        report = evaluate(item.spec, solution)
        fault = ""
        if report.first_fault is not None:
            fault = f"{report.first_fault.family}: {report.first_fault.detail}"
        row = {
            "arm": arm,
            "candidate_id": candidate_id,
            "family": item.family,
            "instance_id": item.instance_id,
            "seed": seed,
            "feasible": bool(report.feasible),
            "objective_key": [float(v) for v in report.objective_key],
            "vehicles": int(report.vehicles),
            "distance": float(report.total_distance),
            "duration": float(report.total_duration),
            "runtime_s": time.monotonic() - started,
            "time_limit_s": item.time_limit_s,
            "first_fault": fault,
            "completed_within_budget": solution.metadata.get("completed_within_budget"),
            "selected_moves": list(solution.metadata.get("selected_moves") or []),
            "load_errors": errors,
            "feature_schema": schema,
            "llm_generated_components": 0,
        }
        if extra:
            row.update(extra)
        rows.append(row)
    return rows


def _budget_flag(row: dict[str, Any]) -> bool | None:
    if "completed_within_budget" not in row or row.get("completed_within_budget") is None:
        return None
    return bool(row["completed_within_budget"])


def _pairs(baseline: list[dict[str, Any]], candidate: list[dict[str, Any]]) -> list[dict[str, Any]]:
    base = {row["instance_id"]: row for row in baseline}
    pairs: list[dict[str, Any]] = []
    for row in candidate:
        other = base[row["instance_id"]]
        outcome = paired_feasible_outcome(
            bool(other["feasible"]),
            tuple(float(v) for v in other["objective_key"]),
            bool(row["feasible"]),
            tuple(float(v) for v in row["objective_key"]),
        )
        candidate_budget = _budget_flag(row)
        baseline_budget = _budget_flag(other)
        deadline = False
        if bool(row["feasible"]) and candidate_budget is False:
            if outcome == "candidate" or (outcome == "tie" and baseline_budget is not False):
                outcome = "baseline"
                deadline = True
        pairs.append(
            {
                "instance_id": row["instance_id"],
                "seed": row["seed"],
                "baseline_feasible": bool(other["feasible"]),
                "candidate_feasible": bool(row["feasible"]),
                "baseline_on_time": baseline_budget,
                "candidate_on_time": candidate_budget,
                "deadline_regression": deadline,
                "paired_outcome": outcome,
            }
        )
    return pairs


def _select(
    baseline: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    *,
    apply_selection: bool = True,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in candidates:
        grouped.setdefault(str(row["candidate_id"]), []).append(row)
    decisions: list[dict[str, Any]] = []
    chosen = None
    for candidate_id, rows in grouped.items():
        pairs = _pairs(baseline, rows)
        conservative = conservative_decision(pairs)
        robust = robust_decision(pairs)
        item = {
            "candidate_id": candidate_id,
            "conservative": conservative,
            "robust": robust,
            "deployed": False,
        }
        decisions.append(item)
    accepted = [item for item in decisions if item["conservative"]["accepted"]]
    if apply_selection and accepted:
        chosen = max(
            accepted,
            key=lambda item: (int(item["conservative"]["wins"]), -decisions.index(item)),
        )
        chosen["deployed"] = True
    if not apply_selection and decisions:
        decisions[-1]["deployed"] = True
        chosen = decisions[-1]
    return {
        "rule": DECLARED_SELECTION_RULE if apply_selection else "selection_disabled",
        "selected_candidate_id": None if chosen is None else chosen["candidate_id"],
        "decisions": decisions,
    }


def _backend(cfg: MatchedPilotConfig) -> tuple[Any, str]:
    if cfg.fake:
        from evrptw_autolab.llm.registry import FakeBackend

        component = {
            "insertion_score": "delta_distance",
            "station_score": "detour",
            "removal_priority": "due_time + route_distance_share",
        }
        replies: dict[str, str | list[str]] = {
            "unified": json.dumps(
                {
                    "feature_schema": FEATURE_SCHEMA_VERSION,
                    "components": [
                        {"component": kind, "expression": component[kind]} for kind in KINDS
                    ],
                }
            ),
            "architect": json.dumps(
                {"summary": "try removal", "components": ["removal_priority"], "hypothesis": "urgency"}
            ),
            "critic": json.dumps({"verdict": "REVISE", "reason": "fake-critic", "next_component": "removal_priority"}),
        }
        for kind in KINDS:
            role = {"insertion_score": "routing", "station_score": "charging", "removal_priority": "search"}[kind]
            replies[role] = json.dumps({"component": kind, "expression": component[kind]})
        return FakeBackend(replies, token_sequence=[12] * 200), "fake"
    from evrptw_autolab.llm.ollama import OllamaBackend
    from evrptw_autolab.llm.registry import availability, make_backend, resolve_profile

    ollama = OllamaBackend()
    profile = resolve_profile(cfg.profile)
    status = availability(profile, ollama)
    if status != "installed":
        raise RuntimeError(f"profile {cfg.profile} status={status}")
    return make_backend(profile, ollama_host=ollama.host), profile.model


def run_matched_pilot(cfg: MatchedPilotConfig | None = None) -> dict[str, Any]:
    """Run the equal-budget pilot. A fake backend is a plumbing check, not Qwen evidence."""
    cfg = cfg or MatchedPilotConfig()
    panel = _panel(cfg)
    backend, model = _backend(cfg)
    seed = int(cfg.seed)
    solves = {arm: 0 for arm in ("classical", "random_evolution", "single_agent", "five_agent")}
    llm_calls = {arm: 0 for arm in solves}
    llm_tokens = {arm: 0 for arm in solves}
    rows: list[dict[str, Any]] = []

    classical_sources = {kind: DEFAULT_SOURCES[kind] for kind in KINDS}
    classical = _evaluate("classical", "default", classical_sources, FEATURE_SCHEMA_VERSION, panel, seed)
    rows.extend(classical)
    solves["classical"] += len(classical)

    rng = random.Random(0)
    for index in range(int(cfg.candidates)):
        sources = dict(classical_sources)
        kind = KINDS[index % len(KINDS)]
        expression = random_component_expression(kind, rng)
        sources[kind] = wrap_expression(kind, expression)
        evaluated = _evaluate(
            "random_evolution",
            f"random_{index}",
            sources,
            FEATURE_SCHEMA_VERSION,
            panel,
            seed,
            extra={"expression": expression, "component": kind, "origin": "grammar"},
        )
        rows.extend(evaluated)
        solves["random_evolution"] += len(evaluated)

    single_collector = UsageCollector(max_calls=cfg.max_llm_calls, max_tokens=cfg.max_llm_tokens)
    for index in range(int(cfg.candidates)):
        kind = KINDS[index % len(KINDS)]
        code, row, schema = _propose_unified_component(
            single_collector,
            backend,
            model,
            kind,
            context=_routing_brief(panel) + f"\nCandidate {index}. One-shot control; no fitness feedback.",
        )
        sources = dict(classical_sources)
        sources[kind] = code
        use_schema = schema if kind == "station_score" else FEATURE_SCHEMA_VERSION
        genuine = 1 if row.get("llm_generated") else 0
        evaluated = _evaluate(
            "single_agent",
            f"single_{index}",
            sources,
            use_schema,
            panel,
            seed,
            extra={"attribution": [row], "llm_generated_components": genuine, "origin": "single_agent", "component": kind},
        )
        rows.extend(evaluated)
        solves["single_agent"] += len(evaluated)
    llm_calls["single_agent"] = single_collector.logical_calls
    llm_tokens["single_agent"] = single_collector.total_tokens

    five_collector = UsageCollector(max_calls=cfg.max_llm_calls, max_tokens=cfg.max_llm_tokens)
    critic_text = ""
    for index in range(int(cfg.candidates)):
        kind = KINDS[index % len(KINDS)]
        plan_text = _architect_text(
            five_collector,
            backend,
            model,
            context=(
                _routing_brief(panel)
                + f"\nCandidate {index}. Scheduled component={kind}. Prior critic: {critic_text or 'none'}."
            ),
        )
        hypothesis = str(plan_text["hypothesis"]) if plan_text["grounded"] else ""
        code, row, schema = _propose_component(
            five_collector,
            backend,
            model,
            kind,
            context=(
                _routing_brief(panel)
                + f"\nCandidate {index}. Architect hypothesis: {hypothesis or 'rejected because it was not a routing hypothesis'}. "
                + f"Prior critic: {critic_text or 'none'}."
            ),
        )
        sources = dict(classical_sources)
        sources[kind] = code
        use_schema = schema if kind == "station_score" else FEATURE_SCHEMA_VERSION
        genuine = 1 if row.get("llm_generated") else 0
        plan = {
            "components": [kind],
            "hypothesis": hypothesis,
            "architect_grounded": bool(plan_text["grounded"]),
        }
        evaluated = _evaluate(
            "five_agent",
            f"five_{index}",
            sources,
            use_schema,
            panel,
            seed,
            extra={
                "attribution": [row],
                "plan": plan,
                "llm_generated_components": genuine,
                "origin": "five_agent",
                "component": kind,
            },
        )
        rows.extend(evaluated)
        solves["five_agent"] += len(evaluated)
        if cfg.use_critic:
            critic_text = _critic(five_collector, backend, model, evaluated, classical)
        else:
            critic_text = ""
    llm_calls["five_agent"] = five_collector.logical_calls
    llm_tokens["five_agent"] = five_collector.total_tokens

    expected = solver_passes(len(panel), candidates=int(cfg.candidates))
    if solves != expected:
        raise RuntimeError(f"solver solves {solves} != declared budget {expected}")

    selections = {
        "random_evolution": _select(
            classical,
            [row for row in rows if row["arm"] == "random_evolution"],
            apply_selection=cfg.apply_selection,
        ),
        "single_agent": _select(
            classical,
            [row for row in rows if row["arm"] == "single_agent"],
            apply_selection=cfg.apply_selection,
        ),
        "five_agent": _select(
            classical,
            [row for row in rows if row["arm"] == "five_agent"],
            apply_selection=cfg.apply_selection,
        ),
    }
    payload = {
        "experiment": "matched_four_arm_pilot",
        "ablation": cfg.ablation,
        "use_critic": cfg.use_critic,
        "apply_selection": cfg.apply_selection,
        "status": "completed",
        "fake": cfg.fake,
        "model": model,
        "git_commit": _git_head(),
        "seed": seed,
        "candidates": int(cfg.candidates),
        "selection_rule": DECLARED_SELECTION_RULE,
        "instances": [
            {
                "family": item.family,
                "instance_id": item.instance_id,
                "time_limit_s": item.time_limit_s,
                "alns_iterations": item.alns_iterations,
            }
            for item in panel
        ],
        "solver_solves": solves,
        "expected_solves": expected,
        "llm_calls": llm_calls,
        "llm_tokens": llm_tokens,
        "selections": selections,
        "rows": rows,
        "claim": (
            "FakeBackend plumbing check. Not evidence about qwen3-coder:30b."
            if cfg.fake
            else (
                "Development-seed comparison under the declared conservative rule. "
                "One seed is not a held-out result. Fallback expressions are not LLM discoveries."
            )
        ),
    }
    out = cfg.out_dir
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
        (out / "matched_pilot.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
