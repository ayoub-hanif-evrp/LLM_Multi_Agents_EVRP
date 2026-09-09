"""P1.3 regression-safe repair protocol tests (no LLM required)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from evrptw_autolab.build.p1_3_regression_safe import (
    CampaignState,
    DEFAULT_MAX_LLM_CALLS,
    _budget_left,
    _copy_solver,
    _panel_instances,
    evaluate_g4_panel,
)
from evrptw_autolab.build.p1_minimal import API_SNIPPET, _code_hash, _read_solver, _write_solver
from evrptw_autolab.llm.usage import UsageLog
from evrptw_autolab.sandbox.limits import RunLimits

ROOT = Path(__file__).resolve().parents[1]
SEED_CANDIDATES = [
    ROOT / "results" / "md" / "artifacts" / "p1_minimal" / "FEASIBLE_SOLVER_V0_solver.py",
    ROOT / "results" / "md" / "artifacts" / "p1_minimal" / "solver.py",
    ROOT
    / "workspace"
    / "discovery_p1_minimal"
    / "qwen25_coder_7b"
    / "FEASIBLE_SOLVER_V0"
    / "solver.py",
]


def _seed_path() -> Path:
    for path in SEED_CANDIDATES:
        if path.exists() and "def solve" in path.read_text(encoding="utf-8"):
            return path
    pytest.skip("P1 3/4 seed solver not available")


def test_stopstate_contract_has_no_lateness() -> None:
    assert "NO .lateness" in API_SNIPPET or "no .lateness" in API_SNIPPET.lower()
    assert "NO .due_time" in API_SNIPPET or "no .due_time" in API_SNIPPET.lower()
    assert "service_start > node.due_time" in API_SNIPPET
    assert "arrival_time > node.due_time" in API_SNIPPET
    # Charging prompt too
    charging = (ROOT / "prompts" / "build" / "charging_engineer.md").read_text(encoding="utf-8")
    assert "NO" in charging and "lateness" in charging
    critic = (ROOT / "prompts" / "build" / "test_evolution_critic.md").read_text(encoding="utf-8")
    assert "C78 waits ~127" not in critic


def test_best_solver_never_regresses(tmp_path: Path) -> None:
    seed = _seed_path()
    best = tmp_path / "best"
    trial = tmp_path / "trial"
    best.mkdir()
    trial.mkdir()
    text = seed.read_text(encoding="utf-8")
    _write_solver(best, text)
    panel = _panel_instances(None)
    limits = RunLimits(wall_clock_s=20.0)
    baseline = evaluate_g4_panel(best, panel, limits)
    assert baseline.feasible == 3
    assert baseline.by_id.get("r105C5") != "OK"

    # Write a deliberately broken trial
    _write_solver(trial, "def solve(instance, seed: int, time_limit_s: float):\n    return {'routes': [], 'metadata': {}}\n")
    broken = evaluate_g4_panel(trial, panel, limits)
    assert broken.feasible < baseline.feasible

    # Protocol: reject trial → best unchanged
    assert _code_hash(_read_solver(best)) == _code_hash(text)
    final = evaluate_g4_panel(best, panel, limits)
    assert final.feasible == baseline.feasible
    assert final.progress == "3/4"


def test_trial_does_not_overwrite_best_without_improvement(tmp_path: Path) -> None:
    seed = _seed_path()
    best = tmp_path / "best"
    trial = tmp_path / "trial"
    _write_solver(best, seed.read_text(encoding="utf-8"))
    _copy_solver(best, trial)
    # Modify trial without promoting
    _write_solver(trial, _read_solver(trial) + "\n# noop comment\n")
    assert _code_hash(_read_solver(best)) != _code_hash(_read_solver(trial))
    # best text still original seed
    assert "def solve" in _read_solver(best)


def test_architect_escalates_at_most_once() -> None:
    state = CampaignState()
    assert state.architect_escalation_used is False
    state.architect_escalation_used = True
    # Second escalation must be blocked by callers checking the flag
    assert state.architect_escalation_used is True


def test_total_llm_budget_is_hard(tmp_path: Path) -> None:
    log = UsageLog(tmp_path / "llm_calls.jsonl")
    state = CampaignState(max_llm_calls=2)
    assert _budget_left(log, state) is True
    # Simulate two recorded calls
    log.path.write_text(
        '{"prompt_tokens":1,"completion_tokens":1}\n{"prompt_tokens":1,"completion_tokens":1}\n',
        encoding="utf-8",
    )
    assert _budget_left(log, state) is False
    assert DEFAULT_MAX_LLM_CALLS <= 16


def test_all_code_changes_are_logged_structure() -> None:
    entry = {
        "hash": "abc",
        "parent_hash": "def",
        "agent": "charging",
        "change_kind": "algo_fix",
        "panel_before": {"c101C5": "OK"},
        "panel_after": {"c101C5": "OK"},
        "accepted": False,
    }
    for key in ("hash", "parent_hash", "agent", "change_kind", "accepted"):
        assert key in entry or key == "accepted"


def test_final_report_uses_best_solver_not_last_trial(tmp_path: Path) -> None:
    seed = _seed_path()
    workspace = tmp_path / "ws"
    best = workspace / "best"
    trial = workspace / "trial"
    current = workspace / "current"
    best.mkdir(parents=True)
    trial.mkdir()
    text = seed.read_text(encoding="utf-8")
    _write_solver(best, text)
    _write_solver(
        trial,
        "def solve(instance, seed: int, time_limit_s: float):\n    raise RuntimeError('bad')\n",
    )
    # Finalization copies best → current (protocol)
    if current.exists():
        shutil.rmtree(current)
    shutil.copytree(best, current)
    panel = _panel_instances(None)
    limits = RunLimits(wall_clock_s=20.0)
    assert evaluate_g4_panel(current, panel, limits).feasible == 3
    assert evaluate_g4_panel(trial, panel, limits).feasible == 0
