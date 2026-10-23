"""FakeBackend proof that five agents produce a checked SolutionV2 and never call ALNS."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evrptw_autolab.agentic_v2.executor import execute_generated_solver
from evrptw_autolab.agentic_v2.instance_context import load_family_instance
from evrptw_autolab.agentic_v2.orchestrator import solve_with_agents
from evrptw_autolab.agentic_v2.run_manager import already_recorded, write_run
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.problem.v2.types import (
    CapabilityFlags,
    NodeV2,
    ProblemSpecV2,
    VehicleTypeV2,
)


def _spec(customer_count: int = 2, battery: float = 1000.0) -> ProblemSpecV2:
    nodes = [
        NodeV2("D0", "depot", 0.0, 0.0, due_time=10000.0),
        NodeV2("S0", "station", 1.0, 1.0, recharging_rate=10.0),
    ]
    for index in range(customer_count):
        nodes.append(NodeV2(f"C{index}", "customer", float(index + 1), 0.0, demand=1.0, due_time=10000.0))
    return ProblemSpecV2(
        instance_id="tiny",
        family="micro",
        capabilities=CapabilityFlags(time_windows=True, capacity=True, battery=True, full_recharge=True),
        nodes=tuple(nodes),
        vehicle_types=(
            VehicleTypeV2("EV", capacity=100.0, battery_capacity=battery, consumption_rate=1.0, velocity=1.0),
        ),
        depot_ids=("D0",),
    )


def _backend(customers: list[str]) -> FakeBackend:
    route = json.dumps({"routes": [{"vehicle_type": "EV", "customers": customers}]})
    return FakeBackend(
        {
            "architect": json.dumps(
                {"objective": "minimize distance", "hard_constraints": ["battery"], "strategy": "one route", "activate": ["routing"]}
            ),
            "routing": route,
            "charging": json.dumps({"insertions": []}),
            "optimization": json.dumps({"moves": []}),
            "critic": json.dumps({"assign_to": "routing", "fault": "", "instruction": "none", "accept": True}),
        }
    )


def test_five_roles_produce_a_checked_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    def _forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("classical ALNS was called")

    monkeypatch.setattr("evrptw_autolab.backbone.solver.solve_classical", _forbidden)
    record = solve_with_agents(_spec(), backend=_backend(["C0", "C1"]), model="fake")
    assert record["classical_alns_used"] is False
    assert record["method"] == "agentic_v2"
    assert record["feasible"] is True
    assert record["status"] == "FEASIBLE"
    roles = [item["role"] for item in record["agent_trace"] if item["role"] != "controller"]
    assert roles[:5] == ["architect", "routing", "charging", "optimization", "critic"]
    assert record["solution"]["routes"][0][0]["event"] == "depot"
    assert record["evaluation"]["feasible"] is True


def test_infeasible_attempt_keeps_the_evaluator_fault() -> None:
    record = solve_with_agents(_spec(), backend=_backend(["NO_SUCH"]), model="fake", max_rounds=1)
    assert record["status"] == "INFEASIBLE_OUTPUT"
    assert record["solution"] is not None
    assert record["evaluation"]["first_fault"]
    assert record["classical_alns_used"] is False


def test_missing_customer_is_repaired_on_the_next_round() -> None:
    backend = FakeBackend(
        {
            "architect": json.dumps({"hard_constraints": ["capacity"], "strategy": "repair"}),
            "routing": [
                json.dumps({"routes": [{"vehicle_type": "EV", "customers": ["C0"]}]}),
                json.dumps({"routes": [{"vehicle_type": "EV", "customers": ["C0", "C1"]}]}),
            ],
            "charging": json.dumps({"insertions": []}),
            "optimization": json.dumps({"moves": []}),
            "critic": json.dumps({"assign_to": "routing", "instruction": "add the missing customer", "accept": False}),
        }
    )
    record = solve_with_agents(_spec(), backend=backend, model="fake", max_rounds=2)
    assert record["feasible"] is True
    assert backend.calls.count("routing") == 2


def test_generated_solver_runs_without_classical_code() -> None:
    source = (
        "def solve(instance):\n"
        "    vehicle = instance['vehicles'][0]['type_id']\n"
        "    return {'routes': [{'vehicle_type': vehicle, 'customers': instance['customer_ids']}]}\n"
    )
    spec = _spec(16)
    from evrptw_autolab.agentic_v2.instance_context import spec_payload

    executed = execute_generated_solver(source, spec_payload(spec))
    assert executed["ok"] is True
    blocked = execute_generated_solver(source + "\nsolve_classical()\n", spec_payload(spec))
    assert blocked["ok"] is False
    backend = FakeBackend(
        {
            "architect": json.dumps({"hard_constraints": [], "strategy": "generate"}),
            "routing": json.dumps({"code": source}),
            "charging": json.dumps({"insertions": []}),
            "optimization": json.dumps({"moves": []}),
            "critic": json.dumps({"assign_to": "routing", "accept": True}),
        }
    )
    record = solve_with_agents(spec, backend=backend, model="fake", max_rounds=1)
    assert record["mode"] == "generated_solver"
    assert record["feasible"] is True
    assert record["classical_alns_used"] is False


def test_battery_fault_can_be_repaired_by_generated_code() -> None:
    nodes = [
        NodeV2("D0", "depot", 0.0, 0.0, due_time=10000.0),
        NodeV2("C0", "customer", 1.0, 0.0, demand=1.0, due_time=10000.0),
        NodeV2("C1", "customer", 0.0, 1.0, demand=1.0, due_time=10000.0),
    ]
    spec = ProblemSpecV2(
        instance_id="split",
        family="micro",
        capabilities=CapabilityFlags(time_windows=True, capacity=True, battery=True, full_recharge=True),
        nodes=tuple(nodes),
        vehicle_types=(VehicleTypeV2("EV", capacity=100.0, battery_capacity=3.0, consumption_rate=1.0, velocity=1.0),),
        depot_ids=("D0",),
    )
    code = (
        "def solve(instance):\n"
        "    vehicle = instance['vehicles'][0]['type_id']\n"
        "    return {'routes': [{'vehicle_type': vehicle, 'customers': [cid]} for cid in instance['customer_ids']]}\n"
    )
    backend = FakeBackend(
        {
            "architect": json.dumps({"hard_constraints": ["battery"], "strategy": "split"}),
            "routing": [
                json.dumps({"routes": [{"vehicle_type": "EV", "customers": ["C0", "C1"]}]}),
                json.dumps({"code": code}),
            ],
            "charging": json.dumps({"insertions": []}),
            "optimization": json.dumps({"moves": []}),
            "critic": json.dumps({"assign_to": "charging", "accept": False}),
        }
    )
    record = solve_with_agents(spec, backend=backend, model="fake", max_rounds=2)
    assert record["feasible"] is True
    assert record["solution"]["vehicle_assignments"].count("EV") == 2


def test_real_schneider_instance_loads() -> None:
    spec, path = load_family_instance("schneider", "c101C5")
    assert spec.family == "schneider"
    assert spec.instance_id
    assert path.name == "c101C5.txt"


def test_checkpoint_resume(tmp_path: Path) -> None:
    record = {"family": "schneider", "instance_id": "c101C5", "status": "FEASIBLE"}
    write_run(record, tmp_path)
    assert already_recorded("schneider", "c101C5", tmp_path)
    assert not already_recorded("schneider", "c102C5", tmp_path)
