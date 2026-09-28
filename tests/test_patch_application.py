from pathlib import Path

from evrptw_autolab.agents.schemas import CodeFile, CodeProposal
from evrptw_autolab.synthesis.patching import (
    apply_proposal,
    code_hash,
    next_free_solver_id,
    rollback_to,
    snapshot_solver,
)


def _proposal(content: str, path: str = "solver.py") -> CodeProposal:
    return CodeProposal(
        proposal_id="p1",
        role="search",
        hypothesis="write solver",
        change_type="CREATE",
        files=[CodeFile(path=path, operation="create", content=content)],
    )


def test_file_replacement_and_hash(tmp_path: Path) -> None:
    apply_proposal(tmp_path, _proposal("def solve(instance, seed, time_limit_s):\n    return {'routes': []}\n"))
    first = code_hash(tmp_path)
    apply_proposal(tmp_path, _proposal("def solve(instance, seed, time_limit_s):\n    return {'routes': [[]]}\n"))
    second = code_hash(tmp_path)
    assert first != second


def test_rollback_restores_parent(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "child"
    apply_proposal(parent, _proposal("PARENT = 1\n"))
    snapshot_solver(parent, child)
    apply_proposal(child, _proposal("CHILD = 2\n"))
    assert "CHILD" in (child / "solver.py").read_text(encoding="utf-8")
    rollback_to(parent, child)
    assert "PARENT" in (child / "solver.py").read_text(encoding="utf-8")


def test_next_free_solver_id_skips_locked_or_existing_dirs(tmp_path: Path) -> None:
    (tmp_path / "S001").mkdir()
    assert next_free_solver_id(tmp_path, {"S000"}) == "S002"
