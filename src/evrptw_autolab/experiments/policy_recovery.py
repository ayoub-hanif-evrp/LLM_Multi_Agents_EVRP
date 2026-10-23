"""Primary track after dd5949d: LLM policies on the frozen classical backbone.

Direct route generation is not called here. A charging DP or ALNS result is
never labeled as an LLM discovery. This module rejects a policy that does not
change a ranking or a selected move before any extra solver work.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evrptw_autolab.components.expressions import wrap_expression
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.loader import load_bundle
from evrptw_autolab.experiments.bundle_selection import random_component_expression
from evrptw_autolab.experiments.generational_compare import _probe_trace
from evrptw_autolab.experiments.matched_pilot import KINDS

BASELINE_COMMIT = "dd5949d0a5a7f679f3ba14a411539a23110c0d0a"
PRIMARY_TRACK = "llm_guided_heuristic_design"
DIRECT_AGENT_TRACK = "exploratory_direct_routes"
MAX_LIVE_CALLS = 12


def default_sources() -> dict[ComponentKind, str]:
    return {kind: DEFAULT_SOURCES[kind] for kind in KINDS}


def flipping_insertion_sources() -> dict[ComponentKind, str]:
    sources = default_sources()
    sources["insertion_score"] = wrap_expression("insertion_score", "0.0 - delta_distance")
    return sources


def gate1_probes() -> dict[str, Any]:
    """No model calls. The default policy must not look like a new decision."""
    baseline = _probe_trace(default_sources())
    flipped = _probe_trace(flipping_insertion_sources())
    ok = (
        not baseline["selected_move_changed"]
        and not baseline["ranking_changed"]
        and bool(flipped["selected_move_changed"])
        and not flipped["load_errors"]
    )
    return {"ok": ok, "baseline": baseline, "flipped": flipped, "llm_calls": 0}


def solver_selected_moves(sources: dict[ComponentKind, str], *, seed: int = 1) -> dict[str, Any]:
    """Run the frozen backbone on Schneider c101C5 and return the moves it recorded."""
    from evrptw_autolab.agentic_v2.instance_context import load_family_instance
    from evrptw_autolab.backbone.solver import solve_classical
    from evrptw_autolab.backbone.util import evaluate

    spec, _path = load_family_instance("schneider", "c101C5")
    bundle, errors = load_bundle(sources, {kind: "policy_recovery" for kind in sources})
    if errors:
        return {"ok": False, "errors": errors, "selected_moves": [], "feasible": False}
    solution = solve_classical(spec, seed=seed, time_limit_s=2.0, alns_iterations=8, policy=bundle)
    report = evaluate(spec, solution)
    return {
        "ok": True,
        "errors": [],
        "selected_moves": list(solution.metadata.get("selected_moves") or []),
        "feasible": bool(report.feasible),
        "objective_key": [float(value) for value in report.objective_key],
        "method": "classical_alns",
        "policy_origin": "supplied_expression",
        "llm_calls": 0,
    }


def write_gate1(directory: Path) -> dict[str, Any]:
    payload = {
        "baseline_commit": BASELINE_COMMIT,
        "track": PRIMARY_TRACK,
        "direct_agent_track": DIRECT_AGENT_TRACK,
        "gate": gate1_probes(),
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "gate1.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def run_live_proof(backend: Any, model: str, directory: Path) -> dict[str, Any]:
    """At most 12 model calls. Stops when a proposal does not change a decision."""
    from evrptw_autolab.experiments.matched_pilot import (
        _architect_text,
        _propose_component,
        _propose_unified_component,
    )
    from evrptw_autolab.llm.usage import UsageCollector

    gate = gate1_probes()
    directory.mkdir(parents=True, exist_ok=True)
    if not gate["ok"]:
        payload = {"status": "ENGINEERING_BLOCKED", "gate": gate, "llm_calls": 0, "track": PRIMARY_TRACK}
        (directory / "live_proof.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload
    started = time.perf_counter()
    collector = UsageCollector(max_calls=MAX_LIVE_CALLS, max_tokens=12000)
    context = (
        "Schneider c101C5. Native objective: minimize vehicle count, then travel distance. "
        "Allowed feature: delta_distance."
    )
    architect = _architect_text(collector, backend, model, context=context)
    hypothesis = architect["hypothesis"] if architect.get("grounded") else ""
    code, row, _schema = _propose_component(
        collector,
        backend,
        model,
        "insertion_score",
        context=f"Hypothesis: {hypothesis or 'rejected ungrounded hypothesis'}. {context}",
    )
    sources = default_sources()
    sources["insertion_score"] = code
    probe = _probe_trace(sources)
    critic_called = False
    critic_effect = False
    if not (probe["ranking_changed"] or probe["selected_move_changed"]):
        critic_called = True
        critic = collector.complete(
            backend,
            prompt=(
                "You are the Critic. The insertion policy did not change the selected move. "
                "Name the feature the next routing expression must use. "
                'Return JSON {"reason":"...","next_feature":"delta_distance"}.\n'
                + json.dumps(probe)
            ),
            role="critic",
            temperature=0.0,
            model=model,
            json_mode=True,
        )
        repaired, repaired_row, _schema = _propose_component(
            collector,
            backend,
            model,
            "insertion_score",
            context=f"Critic rejected the previous expression. {critic}. {context}",
        )
        critic_effect = repaired != code
        code, row = repaired, repaired_row
        sources["insertion_score"] = code
        probe = _probe_trace(sources)
    single_code, single_row, _schema = _propose_unified_component(
        collector, backend, model, "insertion_score", context=context
    )
    single_sources = default_sources()
    single_sources["insertion_score"] = single_code
    single_probe = _probe_trace(single_sources)
    random_row = random_candidate(7)
    behavior = bool(probe["ranking_changed"] or probe["selected_move_changed"])
    single_behavior = bool(single_probe["ranking_changed"] or single_probe["selected_move_changed"])
    solves: dict[str, Any] = {}
    if behavior or single_behavior:
        solves["classical_default"] = solver_selected_moves(default_sources())
    if behavior:
        solves["multi_agent"] = solver_selected_moves(sources)
        solves["multi_agent"]["policy_origin"] = "llm_insertion_expression"
        solves["multi_agent"]["charging"] = "classical_backbone"
    if single_behavior:
        solves["single_agent"] = solver_selected_moves(single_sources)
        solves["single_agent"]["policy_origin"] = "llm_insertion_expression"
        solves["single_agent"]["charging"] = "classical_backbone"
    def _moves_differ(arm: str) -> bool:
        return bool(solves.get(arm)) and solves[arm]["selected_moves"] != solves["classical_default"]["selected_moves"]

    solver_changed = _moves_differ("multi_agent") or _moves_differ("single_agent")
    status = "LLM_POLICY_GENERATED" if solver_changed else "POLICY_INTERFACE_VALIDATED"
    from evrptw_autolab.experiments.generational_compare import _ollama_digest

    payload = {
        "status": status,
        "baseline_commit": BASELINE_COMMIT,
        "track": PRIMARY_TRACK,
        "model": model,
        "model_digest": _ollama_digest(model),
        "llm_calls": collector.logical_calls,
        "llm_tokens": collector.total_tokens,
        "wall_s": round(time.perf_counter() - started, 3),
        "architect": architect,
        "multi_agent": {"source": code, "attribution": row, "probe": probe, "critic_changed_source": critic_effect},
        "single_agent": {"source": single_code, "attribution": single_row, "probe": single_probe},
        "random": random_row,
        "solves": solves,
        "critic_called": critic_called,
        "solver_decision_changed": solver_changed,
        "confirmation_run": False,
        "direct_agent_campaign": False,
    }
    (directory / "live_proof.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def random_candidate(seed: int) -> dict[str, Any]:
    import random

    rng = random.Random(seed)
    sources = default_sources()
    sources["insertion_score"] = wrap_expression(
        "insertion_score", random_component_expression("insertion_score", rng)
    )
    probe = _probe_trace(sources)
    return {
        "arm": "random",
        "llm_calls": 0,
        "sources": sources,
        "behavior_changed": bool(probe["ranking_changed"] or probe["selected_move_changed"]),
        "probe": probe,
        "method": "random_grammar",
    }
