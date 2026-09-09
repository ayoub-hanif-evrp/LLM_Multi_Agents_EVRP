from pathlib import Path

from tests.helpers import SOLVER_PY

from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.sandbox.static_scan import scan_source


def _write_solver(tmp_path: Path, source: str, extra: dict[str, str] | None = None) -> Path:
    tmp_path.joinpath("solver.py").write_text(source, encoding="utf-8")
    for name, content in (extra or {}).items():
        tmp_path.joinpath(name).write_text(content, encoding="utf-8")
    return tmp_path


def test_rejects_forbidden_imports() -> None:
    errors = scan_source("import subprocess\n\ndef solve(instance, seed, time_limit_s):\n    return {'routes': []}\n")
    assert any("forbidden_import:subprocess" in item for item in errors)


def test_rejects_eval_and_heldout_hardcode() -> None:
    source = "def solve(instance, seed, time_limit_s):\n    eval('1')\n    return {'routes': [], 'note': 'rc201'}\n"
    errors = scan_source(source)
    assert any("forbidden_call:eval" in item for item in errors)
    assert any("possible_heldout_hardcode:rc201" in item for item in errors)


def test_rejects_evaluation_import() -> None:
    errors = scan_source("from evrptw_autolab.evaluation import load_all\n")
    assert any("forbidden_import" in item for item in errors)


def test_timeout_kills_infinite_loop(tmp_path: Path, c101c5) -> None:
    _write_solver(tmp_path, "def solve(instance, seed, time_limit_s):\n    while True:\n        pass\n")
    report = run_solver(tmp_path, c101c5, seed=0, limits=RunLimits(wall_clock_s=1.0))
    assert report.timed_out


def test_captures_exceptions(tmp_path: Path, c101c5) -> None:
    _write_solver(tmp_path, "def solve(instance, seed, time_limit_s):\n    raise RuntimeError('boom')\n")
    report = run_solver(tmp_path, c101c5, seed=0, limits=RunLimits(wall_clock_s=5.0))
    assert report.crashed
    assert "boom" in report.error
    assert "CONTRACT" in report.error


def test_isolates_workdir_and_runs_tiny_solver(tmp_path: Path, c101c5) -> None:
    from tests.helpers import CHARGING_PY, ROUTING_PY

    _write_solver(tmp_path, SOLVER_PY, {"routing.py": ROUTING_PY, "charging.py": CHARGING_PY})
    report = run_solver(tmp_path, c101c5, seed=0, limits=RunLimits(wall_clock_s=8.0))
    assert report.parse_ok
    assert not report.crashed
    assert report.all_customers_served_once
