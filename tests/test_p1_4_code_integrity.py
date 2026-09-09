"""P1.4 code-integrity tests (no LLM)."""
from __future__ import annotations

from pathlib import Path

import pytest

from evrptw_autolab.agents.base import Agent
from evrptw_autolab.build.code_integrity import (
    REASONING_ROLES,
    assert_coding_role,
    ast_valid,
    try_commit_solver,
)
from evrptw_autolab.build.p1_minimal import _read_solver, _write_solver


VALID = '''
from evrptw_autolab.problem.physics import propagate_route

def solve(instance, seed: int, time_limit_s: float):
    depot = instance.depot_id
    routes = [[depot, cid, depot] for cid in instance.customer_ids]
    return {"routes": routes, "metadata": {"seed": seed}}
'''.strip()

CORRUPT = '''
def solve(instance, seed: int, time_limit_s: float):
    remaining_energy -= energy_required_forupervisor: The mechanism-level lesson is that charging fails.
    return {"routes": [], "metadata": {}}
'''.strip()


def test_ast_rejects_prose_splice() -> None:
    ok, reason = ast_valid(CORRUPT)
    assert ok is False
    assert "SyntaxError" in reason


def test_ast_accepts_valid_solver() -> None:
    ok, reason = ast_valid(VALID)
    assert ok is True
    assert reason == "ok"


def test_invalid_syntax_does_not_overwrite(tmp_path: Path) -> None:
    solver_dir = tmp_path / "current"
    _write_solver(solver_dir, VALID)
    before = _read_solver(solver_dir)
    result = try_commit_solver(
        solver_dir,
        CORRUPT,
        role="charging",
        agent=None,
        gate="G2",
        raw=CORRUPT,
        max_syntax_repairs=0,
    )
    assert result.committed is False
    assert _read_solver(solver_dir) == before


def test_valid_candidate_commits(tmp_path: Path) -> None:
    solver_dir = tmp_path / "current"
    _write_solver(solver_dir, VALID)
    improved = VALID + "\n# touch\n"
    result = try_commit_solver(
        solver_dir,
        improved,
        role="routing",
        agent=None,
        gate="G1",
        max_syntax_repairs=0,
    )
    assert result.committed is True
    assert "# touch" in _read_solver(solver_dir)


def test_reasoning_roles_cannot_assert_write() -> None:
    for role in REASONING_ROLES:
        with pytest.raises(PermissionError):
            assert_coding_role(role)
    assert_coding_role("charging")
    assert_coding_role("routing")
    assert_coding_role("search")


def test_critic_agent_has_no_write_python_override() -> None:
    """Critic uses Agent.run (JSON), not a custom file writer."""
    from evrptw_autolab.agents.architect import ArchitectAgent
    from evrptw_autolab.agents.critic import CriticAgent

    assert issubclass(CriticAgent, Agent)
    assert issubclass(ArchitectAgent, Agent)
    assert CriticAgent.role == "critic"
    assert ArchitectAgent.role == "architect"
