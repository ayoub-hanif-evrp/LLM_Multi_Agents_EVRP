import json
from pathlib import Path

from tests.conftest import DATA_ROOT
from tests.helpers import ARCHITECT_BOOTSTRAP, SOLVER_PY, _proposal, fake_team_replies

from evrptw_autolab.evaluation.runner import check_f0
from evrptw_autolab.experiments.synthesis_campaign import run_campaign
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.orchestration.cycle import run_cycle
from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver
from evrptw_autolab.synthesis.compile_repair import role_for_f0_errors


def test_check_f0_catches_helper_syntax(tmp_path: Path) -> None:
    (tmp_path / "solver.py").write_text(
        "def solve(instance, seed, time_limit_s):\n    return {'routes': []}\n", encoding="utf-8"
    )
    (tmp_path / "charging.py").write_text("def broken(\n", encoding="utf-8")
    errors = check_f0(tmp_path)
    assert any("charging.py" in item and "syntax" in item for item in errors)
    assert role_for_f0_errors(errors) == "charging"
    assert not any(item.startswith("smoke:") for item in errors)


def test_check_f0_requires_module_level_solve(tmp_path: Path) -> None:
    (tmp_path / "solver.py").write_text(
        "class Solve:\n    def solve(self, instance, seed, time_limit_s):\n        return {'routes': []}\n",
        encoding="utf-8",
    )
    errors = check_f0(tmp_path)
    assert "missing:solve" in errors
    assert not any(item.startswith("smoke:") for item in errors)


def test_check_f0_rejects_redefined_instance_and_stub(tmp_path: Path) -> None:
    (tmp_path / "solver.py").write_text(
        "class EVRPTWInstance:\n    pass\n\n"
        "def solve(instance, seed, time_limit_s):\n    return None\n",
        encoding="utf-8",
    )
    errors = check_f0(tmp_path)
    assert any("redefine_EVRPTWInstance" in item for item in errors)
    assert any("stub" in item for item in errors)
    assert not any(item.startswith("smoke:") for item in errors)


def test_check_f0_rejects_bad_solve_signature(tmp_path: Path) -> None:
    (tmp_path / "solver.py").write_text(
        "def solve(customer_ids, n_customers):\n    return {'routes': []}\n",
        encoding="utf-8",
    )
    errors = check_f0(tmp_path)
    assert any("bad_solve_signature" in item for item in errors)


def test_bootstrap_uses_all_five_roles_even_if_architect_omits_bootstrap(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    replies = fake_team_replies()
    replies["architect"] = [
        json.dumps({**ARCHITECT_BOOTSTRAP, "target": "ROUTING", "agents_to_activate": ["routing"]})
    ]
    backend = FakeBackend(replies)
    result = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    assert set(result["activated"]) == {"architect", "routing", "charging", "search", "critic"}
    assert {"routing", "charging", "search"}.issubset(set(backend.calls))


def test_compile_repair_restores_missing_solve(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    replies = fake_team_replies()
    broken = (
        "from routing import dedicated_routes\n\n"
        "def not_the_entry(instance):\n    return dedicated_routes(instance)\n"
    )
    replies["search"] = [
        json.dumps(_proposal("search", "solver.py", broken)),
        json.dumps(_proposal("search", "solver.py", SOLVER_PY)),
    ]
    backend = FakeBackend(replies)
    result = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    assert not result["f0_errors"]
    assert "def solve" in Path(result["path"]).joinpath("solver.py").read_text(encoding="utf-8")
    assert backend.calls.count("search") >= 2


def test_cycle_from_existing_s000(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    backend = FakeBackend(fake_team_replies())
    boot = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    cycle = run_cycle(
        tmp_path, backend, model="fake-model", parent_id=boot["solver_id"], instance=instance
    )
    assert cycle["solver_id"] != boot["solver_id"]
    assert cycle["elite_id"] in {boot["solver_id"], cycle["solver_id"]}
    assert (tmp_path / "candidates" / cycle["solver_id"]).exists()
    assert cycle["phase"] == "OPTIMIZE"


def test_debug_cycle_calls_architect_and_search_only(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    backend = FakeBackend(fake_team_replies())
    boot = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    solver = tmp_path / "candidates" / boot["solver_id"] / "solver.py"
    solver.write_text(
        "def solve(instance, seed, time_limit_s):\n    raise RuntimeError('boom')\n",
        encoding="utf-8",
    )
    calls_before = list(backend.calls)
    cycle = run_cycle(
        tmp_path, backend, model="fake-model", parent_id=boot["solver_id"], instance=instance
    )
    assert cycle["phase"] == "DEBUG"
    assert cycle["activated"] == ["architect", "search", "critic"]
    assert cycle["decision"] in {"RETAIN", "REVISE"}
    if cycle["decision"] == "RETAIN":
        assert cycle["elite_id"] == cycle["solver_id"]
    assert "architect" in backend.calls[len(calls_before) :]
    assert "search" in backend.calls[len(calls_before) :]
    assert "routing" not in backend.calls[len(calls_before) :]


def test_runtime_repair_rewrites_crashing_solve(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    replies = fake_team_replies()
    crash = "def solve(instance, seed, time_limit_s):\n    raise RuntimeError('boom')\n"
    replies["search"] = [
        json.dumps(_proposal("search", "solver.py", crash)),
        json.dumps(_proposal("search", "solver.py", SOLVER_PY)),
    ]
    backend = FakeBackend(replies)
    result = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    assert backend.calls.count("search") >= 2
    report = run_solver(Path(result["path"]), instance, seed=0)
    assert not report.crashed


def test_campaign_resumes_existing_s000_without_second_bootstrap(tmp_path: Path) -> None:
    backend = FakeBackend(fake_team_replies())
    bootstrap_solver(
        tmp_path, backend, model="fake-model", instance=load_instance(DATA_ROOT / "c101C5.txt")
    )
    calls_after_boot = list(backend.calls)
    state = run_campaign(
        model="fake-model",
        backend=backend,
        workspace=tmp_path,
        cycles=1,
        campaign_id="c1",
        model_id="fake",
        data_root=DATA_ROOT,
    )
    assert state.elite_id
    assert state.cycle == 1
    assert backend.calls[: len(calls_after_boot)] == calls_after_boot
    assert "architect" in backend.calls[len(calls_after_boot) :]
