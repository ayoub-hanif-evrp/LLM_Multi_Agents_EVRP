from pathlib import Path

from evrptw_autolab.synthesis.candidate import CandidateSolver
from evrptw_autolab.synthesis.code_graph import CodeGraph, SolverNode


def test_lineage_is_deterministic(tmp_path: Path) -> None:
    graph = CodeGraph(tmp_path / "graph")
    node = SolverNode(
        solver_id="S000",
        parent=None,
        code_hash="abc",
        agent_role="architect",
        model="fake",
        hypothesis="h",
        status="ELITE",
        path=str(tmp_path),
        evaluation_summary={"feasible": True},
        created_at="2026-01-01T00:00:00+00:00",
    )
    graph.add(node)
    reloaded = CodeGraph(tmp_path / "graph")
    assert reloaded.get("S000").code_hash == "abc"
    assert CandidateSolver(solver_id="S000", path=tmp_path).solver_id == "S000"
