"""Gate 0 and Gate 1 for heuristic policies. No model calls."""
from __future__ import annotations

import json
from pathlib import Path

from tests.test_agentic_v2 import _backend, _spec

from evrptw_autolab.agentic_v2.actions import validate_action_payload
from evrptw_autolab.agentic_v2.orchestrator import solve_with_agents
from evrptw_autolab.experiments.policy_recovery import (
    flipping_insertion_sources,
    gate1_probes,
    random_candidate,
    solver_selected_moves,
)
from evrptw_autolab.llm.registry import FakeBackend


def test_gate1_default_policy_does_not_change_the_selected_move() -> None:
    gate = gate1_probes()
    assert gate["llm_calls"] == 0
    assert gate["ok"] is True
    assert gate["baseline"]["selected_move_changed"] is False
    assert gate["flipped"]["selected_move_changed"] is True


def test_flipped_policy_changes_the_solver_move_and_stays_labeled() -> None:
    baseline = solver_selected_moves({kind: source for kind, source in flipping_insertion_sources().items()})
    # The helper above used the flipped sources. Compare with the default bundle.
    from evrptw_autolab.experiments.policy_recovery import default_sources

    default = solver_selected_moves(default_sources())
    flipped = solver_selected_moves(flipping_insertion_sources())
    assert default["feasible"] is True
    assert default["method"] == "classical_alns"
    assert flipped["ok"] is True
    assert default["selected_moves"] != flipped["selected_moves"]
    assert baseline["llm_calls"] == 0


def test_random_grammar_expression_loads() -> None:
    row = random_candidate(7)
    assert row["llm_calls"] == 0
    assert row["probe"]["load_errors"] == []


def test_malformed_where_is_rejected_by_the_orchestrator() -> None:
    rejected = validate_action_payload({"insertions": [{"where": "12", "station_id": "S0", "after_stop": "C0"}]})
    assert rejected == ["malformed_where:12"]
    backend = _backend(["C0", "C1"])
    backend.replies["charging"] = [
        json.dumps({"insertions": [{"where": "12", "station_id": "S0", "after_stop": "C0", "charge_amount": 1}]})
    ]
    record = solve_with_agents(_spec(), backend=backend, model="fake", max_rounds=1)
    nodes = [stop["node_id"] for route in record["solution"]["routes"] for stop in route]
    assert "S0" not in nodes
    controllers = [item for item in record["agent_trace"] if item.get("action") == "charging"]
    assert controllers
    assert any(str(error).startswith("malformed_where") for error in controllers[0]["errors"])
    assert record["classical_alns_used"] is False


def test_fake_policy_roles_are_not_a_live_result(tmp_path: Path) -> None:
    backend = FakeBackend(
        {
            "architect": json.dumps(
                {"hypothesis": "Lower delta_distance to reduce travel distance", "prediction": "fewer vehicles"}
            ),
            "routing": json.dumps({"component": "insertion_score", "expression": "0.0 - delta_distance"}),
            "unified": json.dumps({"component": "insertion_score", "expression": "delta_distance"}),
            "critic": json.dumps({"reason": "no change", "next_feature": "delta_distance"}),
        }
    )
    from evrptw_autolab.experiments.policy_recovery import run_live_proof

    payload = run_live_proof(backend, "fake", directory=tmp_path)
    assert payload["llm_calls"] <= 12
    assert payload["status"] in {"POLICY_INTERFACE_VALIDATED", "LLM_POLICY_GENERATED", "DISCOVERY_IMPROVEMENT"}
    assert payload["confirmation_run"] is False
    assert payload["direct_agent_campaign"] is False
