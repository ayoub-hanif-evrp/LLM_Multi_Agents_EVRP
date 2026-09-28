"""Baseline-only tests. Recovery solver is not part of synthesis."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from baselines.handcrafted_recovery_baseline import force_executable_entry  # noqa: E402

from evrptw_autolab.problem.private import smoke_instance  # noqa: E402
from evrptw_autolab.sandbox.limits import RunLimits  # noqa: E402
from evrptw_autolab.sandbox.runner import run_solver  # noqa: E402


def test_handcrafted_baseline_is_feasible_on_smoke(tmp_path: Path) -> None:
    force_executable_entry(tmp_path)
    report = run_solver(tmp_path, smoke_instance(2), seed=0, limits=RunLimits(wall_clock_s=5))
    assert not report.crashed
    assert report.feasible
    assert report.vehicles >= 1
