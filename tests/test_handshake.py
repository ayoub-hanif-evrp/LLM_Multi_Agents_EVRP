from pathlib import Path

from tests.conftest import DATA_ROOT
from tests.helpers import ROUTING_PY, fake_team_replies

from evrptw_autolab.evaluation.runner import check_component_f0
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.orchestration.handshake import owner_for_family
from evrptw_autolab.problem.evaluator import first_fault
from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.problem.types import CandidateSolution
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver


def test_first_fault_empty_routes_is_visit() -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    packet = first_fault(instance, CandidateSolution(routes=[]))
    assert packet["family"] == "VISIT"
    assert packet["node_id"] in instance.customer_ids


def test_first_fault_ok_on_dedicated_routes() -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    packet = first_fault(instance, CandidateSolution(routes=routes))
    assert packet["family"] == "OK"


def test_owner_mapping() -> None:
    assert owner_for_family("BATTERY") == "charging"
    assert owner_for_family("VISIT") == "routing"
    assert owner_for_family("CRASH") == "search"


def test_component_gate_allows_routing_before_solver(tmp_path: Path) -> None:
    (tmp_path / "routing.py").write_text(ROUTING_PY, encoding="utf-8")
    assert check_component_f0(tmp_path, "routing") == []
    assert any("solver" in item for item in check_component_f0(tmp_path, "search"))


def test_bootstrap_keeps_incumbent_feasible(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    backend = FakeBackend(fake_team_replies())
    result = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    report = run_solver(Path(result["path"]), instance, seed=0, limits=RunLimits(wall_clock_s=8.0))
    assert not report.crashed
    assert report.feasible
    assert report.first_fault.get("family") == "OK"
    assert (tmp_path / "trajectories.jsonl").exists()
    assert backend.calls[0] == "architect"
    assert backend.calls.index("routing") < backend.calls.index("charging")
    assert backend.calls.index("charging") < backend.calls.index("search")


def test_pick_cycle_instance_prefers_infeasible(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    hard = load_instance(DATA_ROOT / "r105C5.txt")
    backend = FakeBackend(fake_team_replies())
    result = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    from evrptw_autolab.orchestration.handshake import pick_cycle_instance

    chosen, report = pick_cycle_instance(
        Path(result["path"]),
        [instance, hard],
        limits=RunLimits(wall_clock_s=8.0),
    )
    assert chosen.instance_id == "r105C5"
    assert not report.feasible
    assert report.first_fault.get("family") in {"BATTERY", "WINDOW", "CAPACITY", "VISIT", "DEPOT"}


def test_pick_cycle_instance_uses_smoke_when_crashed(tmp_path: Path) -> None:
    from evrptw_autolab.orchestration.handshake import pick_cycle_instance

    (tmp_path / "solver.py").write_text(
        "def solve(instance, seed, time_limit_s):\n    raise RuntimeError('boom')\n",
        encoding="utf-8",
    )
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    chosen, report = pick_cycle_instance(
        tmp_path, [instance], limits=RunLimits(wall_clock_s=3.0)
    )
    assert chosen.instance_id == "smoke_c1"
    assert report.crashed


def test_recover_python_stub_replaces_placeholder(tmp_path: Path) -> None:
    from evrptw_autolab.agents.charging_engineer import ChargingEngineer
    from evrptw_autolab.orchestration.handshake import recover_python_stub
    from tests.helpers import CHARGING_PY

    (tmp_path / "charging.py").write_text("# python source of charging helpers\n", encoding="utf-8")
    backend = FakeBackend({"charging": [CHARGING_PY]})
    agent = ChargingEngineer(backend, model="fake-model", temperature=0.0)
    assert recover_python_stub(tmp_path, {"charging": agent}, "charging", {})
    text = (tmp_path / "charging.py").read_text(encoding="utf-8")
    assert "def " in text
    assert "insert_stations" in text
