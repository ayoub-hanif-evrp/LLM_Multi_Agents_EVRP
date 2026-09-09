from pathlib import Path

from tests.conftest import DATA_ROOT
from tests.helpers import fake_team_replies

from evrptw_autolab.evaluation.runner import evaluate_fidelity
from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.problem.schneider import load_instance
from evrptw_autolab.sandbox.limits import RunLimits
from evrptw_autolab.sandbox.runner import run_solver
from evrptw_autolab.synthesis.bootstrap import bootstrap_solver
from evrptw_autolab.synthesis.code_graph import CodeGraph
from evrptw_autolab.synthesis.export import export_solver


def test_end_to_end_fake_llm_smoke(tmp_path: Path) -> None:
    instance = load_instance(DATA_ROOT / "c101C5.txt")
    backend = FakeBackend(fake_team_replies())
    result = bootstrap_solver(tmp_path, backend, model="fake-model", instance=instance)
    assert result["solver_id"] == "S000"
    assert set(result["activated"]) >= {"routing", "charging", "search", "critic"}
    assert result["critic"]["decision"] in {"RETAIN", "REVISE", "REVERT", "ABANDON"}
    solver_dir = Path(result["path"])
    report = run_solver(solver_dir, instance, seed=0, limits=RunLimits(wall_clock_s=8.0))
    assert report.parse_ok
    assert not report.crashed
    assert report.all_customers_served_once
    f1 = evaluate_fidelity(solver_dir, [instance], "F1", seeds=[0], max_instances=1)
    assert f1["level"] == "F1"
    graph = CodeGraph(tmp_path / "code_graph")
    assert graph.get("S000").model == "fake-model"
    exported = export_solver(solver_dir, tmp_path / "export")
    assert (exported / "solver.py").exists()
    assert "No LLM" in (exported / "README.md").read_text(encoding="utf-8")
    exported_report = run_solver(exported, instance, seed=0, limits=RunLimits(wall_clock_s=8.0))
    assert exported_report.parse_ok
    assert "ollama" not in (exported / "solver.py").read_text(encoding="utf-8").lower()
