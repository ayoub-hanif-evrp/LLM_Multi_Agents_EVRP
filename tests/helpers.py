"""Deterministic fake-LLM payloads for tests. Not a hidden production solver."""
from __future__ import annotations

import json

ROUTING_PY = """
def dedicated_routes(instance):
    depot = instance.depot_id
    return [[depot, cid, depot] for cid in instance.customer_ids]
"""

CHARGING_PY = """
def insert_stations(instance, route):
    return list(route)

def repair_energy(instance, routes):
    return [list(route) for route in routes]
"""

SOLVER_PY = """
from routing import dedicated_routes
from charging import insert_stations

def solve(instance, seed, time_limit_s):
    routes = [insert_stations(instance, route) for route in dedicated_routes(instance)]
    return {"routes": routes, "metadata": {"seed": int(seed), "time_limit_s": float(time_limit_s)}}
"""

ARCHITECT_BOOTSTRAP = {
    "hypothesis": "dedicated routes then optional charging repair",
    "target": "BOOTSTRAP",
    "evidence": ["generation 0"],
    "agents_to_activate": ["routing", "charging", "search", "critic"],
    "files_or_components": ["routing.py", "charging.py", "solver.py"],
    "success_criteria": ["runs without crash", "valid routes schema"],
    "budget": {"max_proposals": 2, "max_evaluation_fidelity": "F1"},
}

ARCHITECT_CYCLE = {
    "hypothesis": "charging repair if battery fails",
    "target": "CHARGING",
    "evidence": ["parent executed"],
    "agents_to_activate": ["charging", "critic"],
    "files_or_components": ["charging.py"],
    "success_criteria": ["no crash"],
    "budget": {"max_proposals": 1, "max_evaluation_fidelity": "F1"},
}

CRITIC = {
    "decision": "REVISE",
    "primary_cause": "smoke pipeline",
    "evidence": ["sandbox executed"],
    "credited_components": ["routing.py"],
    "blamed_components": [],
    "next_target": "CHARGING",
    "lesson": "Dedicated routes establish a valid solver interface before energy repair.",
}


def _proposal(role: str, path: str, content: str, change: str = "CREATE") -> dict:
    return {
        "proposal_id": f"{role}-001",
        "role": role,
        "parent_solver_id": "S000",
        "hypothesis": f"{role} component",
        "change_type": change,
        "files": [{"path": path, "operation": "create", "content": content}],
        "expected_effect": {"feasibility": "valid schema"},
        "requested_tests": ["F1"],
    }


def fake_team_replies() -> dict[str, list[str]]:
    return {
        "architect": [json.dumps(ARCHITECT_BOOTSTRAP), json.dumps(ARCHITECT_CYCLE)],
        "routing": [json.dumps(_proposal("routing", "routing.py", ROUTING_PY))],
        "charging": [json.dumps(_proposal("charging", "charging.py", CHARGING_PY))],
        "search": [json.dumps(_proposal("search", "solver.py", SOLVER_PY))],
        "critic": [json.dumps(CRITIC)],
    }
