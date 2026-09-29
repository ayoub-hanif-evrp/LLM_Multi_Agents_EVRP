"""Integration-style tests for solver evolution with FakeBackend."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from evrptw_autolab.evolution.evolve import run_evolution
from evrptw_autolab.evolution.patch_apply import apply_ops
from evrptw_autolab.evolution.types import PatchOp
from evrptw_autolab.llm.registry import FakeBackend

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "tests" / "fixtures" / "feasible_parent" / "solver.py"


def _reply(ops: list[dict], hypothesis: str = "h") -> str:
    return json.dumps({"hypothesis": hypothesis, "ops": ops})


def test_fake_generation_rejects_crash_patch(tmp_path: Path) -> None:
    assert FROZEN.exists()
    # REPLACE solve with crashing body
    crash = _reply(
        [
            {
                "action": "REPLACE",
                "symbol": "solve",
                "code": (
                    "def solve(instance, seed: int, time_limit_s: float):\n"
                    "    raise RuntimeError('boom')\n"
                ),
            }
        ],
        "crash",
    )
    backend = FakeBackend({role: [crash] for role in (
        "architect", "routing", "charging", "search", "critic_inventor"
    )})
    result = run_evolution(
        model="fake",
        backend=backend,
        workspace=tmp_path / "evo",
        parent_solver=FROZEN,
        max_generations=1,
        candidates_per_role=1,
        beam_size=2,
        max_llm_calls=40,
    )
    assert result["milestone_hit"] is False
    # best remains parent hash
    parent_hash = result["parent_hash"]
    assert result["best_hash"] == parent_hash


def test_apply_improving_structural_patch_preserves_feasibility() -> None:
    """Hand-crafted ADD that does not change behavior remains feasible apply."""
    src = FROZEN.read_text(encoding="utf-8")
    result = apply_ops(
        src,
        [PatchOp("ADD", "identity_helper", "def identity_helper(x):\n    return x\n")],
    )
    assert result.ok
    assert "def identity_helper" in result.source
    assert "def solve" in result.source


def test_fake_empty_ops_recorded(tmp_path: Path) -> None:
    backend = FakeBackend(
        {role: ["not-json"] for role in ("architect", "routing", "charging", "search", "critic_inventor")}
    )
    result = run_evolution(
        model="fake",
        backend=backend,
        workspace=tmp_path / "evo2",
        parent_solver=FROZEN,
        max_generations=1,
        candidates_per_role=1,
        beam_size=2,
        max_llm_calls=40,
    )
    assert result["generations"] == 1
    reps = result["generation_reports"][0]["candidates"]
    assert any(c.get("reject_reason") == "empty_ops" for c in reps)


def test_milestone_instances_detects_four_vehicle_win() -> None:
    from evrptw_autolab.evolution.evaluate import milestone_instances
    from evrptw_autolab.evolution.types import PanelMetrics

    metrics = PanelMetrics(
        feasible=4,
        total=4,
        vehicles_sum=19,
        distance_sum=900.0,
        by_instance={
            "c101C5": {"ok": True, "vehicles": 4, "distance": 200.0},
            "c103C5": {"ok": True, "vehicles": 5, "distance": 200.0},
            "r104C5": {"ok": True, "vehicles": 5, "distance": 250.0},
            "r105C5": {"ok": True, "vehicles": 5, "distance": 250.0},
        },
    )
    assert milestone_instances(metrics, threshold=4) == ["c101C5"]


def test_freeze_artifact_on_vehicle_milestone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate lex-better panel with a 5→4 instance win and assert freeze + all-C5 path."""
    from evrptw_autolab.evolution import evolve as evolve_mod
    from evrptw_autolab.evolution.types import PanelMetrics

    parent_panel = PanelMetrics(
        feasible=4,
        total=4,
        vehicles_sum=20,
        distance_sum=951.0,
        by_instance={
            "c101C5": {"ok": True, "vehicles": 5, "distance": 296.0},
            "c103C5": {"ok": True, "vehicles": 5, "distance": 207.0},
            "r104C5": {"ok": True, "vehicles": 5, "distance": 223.0},
            "r105C5": {"ok": True, "vehicles": 5, "distance": 225.0},
        },
    )
    win_panel = PanelMetrics(
        feasible=4,
        total=4,
        vehicles_sum=19,
        distance_sum=940.0,
        by_instance={
            "c101C5": {"ok": True, "vehicles": 4, "distance": 285.0},
            "c103C5": {"ok": True, "vehicles": 5, "distance": 207.0},
            "r104C5": {"ok": True, "vehicles": 5, "distance": 223.0},
            "r105C5": {"ok": True, "vehicles": 5, "distance": 225.0},
        },
    )
    parent_c5 = PanelMetrics(
        feasible=12,
        total=12,
        vehicles_sum=60,
        distance_sum=3000.0,
        by_instance={},
    )
    win_c5 = PanelMetrics(
        feasible=12,
        total=12,
        vehicles_sum=59,
        distance_sum=2800.0,
        by_instance={"c101C5": {"ok": True, "vehicles": 4, "distance": 285.0}},
    )

    panel_i = {"n": 0}
    c5_i = {"n": 0}

    def fake_eval(solver_dir, instances, *, limits=None):  # noqa: ANN001
        if len(instances) > 4:
            c5_i["n"] += 1
            return (parent_c5 if c5_i["n"] == 1 else win_c5), []
        panel_i["n"] += 1
        if panel_i["n"] == 1:
            return parent_panel, []
        return win_panel, []

    monkeypatch.setattr(evolve_mod, "evaluate_panel", fake_eval)
    monkeypatch.setattr(evolve_mod, "validate_source", lambda *a, **k: (True, "ok"))

    good = _reply(
        [
            {
                "action": "ADD",
                "symbol": "merge_hint",
                "code": "def merge_hint(x):\n    return x\n",
            }
        ],
        "fleet win stub",
    )
    backend = FakeBackend(
        {role: [good] for role in ("architect", "routing", "charging", "search", "critic_inventor")}
    )
    result = run_evolution(
        model="fake",
        backend=backend,
        workspace=tmp_path / "evo_win",
        parent_solver=FROZEN,
        max_generations=1,
        candidates_per_role=1,
        beam_size=2,
        max_llm_calls=40,
        seed_base=11,
        campaign_id="paper_seed11",
        stop_on_milestone=False,
    )
    assert result["milestone_hit"] is True
    assert result["milestone_instance"] == "c101C5"
    assert result["improved_vs_parent"] is True
    assert len(result["trajectory"]) >= 2
    freeze = result.get("freeze_dir")
    assert freeze
    freeze_path = Path(freeze)
    assert freeze_path.name.startswith("seed11_")
    assert freeze_path.exists()
    assert (freeze_path / "solver.py").exists()
    meta = json.loads((freeze_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["all_c5"]["feasible"] == 12
    import shutil

    shutil.rmtree(freeze_path, ignore_errors=True)


def test_proposal_seed_formula() -> None:
    from evrptw_autolab.evolution.propose import proposal_seed

    assert proposal_seed(11, 0, 0, 0) == 110000
    assert proposal_seed(11, 1, 2, 1) == 110000 + 100 + 20 + 1


def test_freeze_refuses_published_solvers() -> None:
    import pytest as _pytest

    from evrptw_autolab.evolution.freeze import IMMUTABLE_DIR, assert_not_immutable

    with _pytest.raises(RuntimeError):
        assert_not_immutable(IMMUTABLE_DIR)


def test_stop_on_milestone_false_continues(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from evrptw_autolab.evolution import evolve as evolve_mod
    from evrptw_autolab.evolution.types import PanelMetrics

    parent_panel = PanelMetrics(
        feasible=4,
        total=4,
        vehicles_sum=20,
        distance_sum=951.0,
        by_instance={
            "c101C5": {"ok": True, "vehicles": 5, "distance": 1.0},
            "c103C5": {"ok": True, "vehicles": 5, "distance": 1.0},
            "r104C5": {"ok": True, "vehicles": 5, "distance": 1.0},
            "r105C5": {"ok": True, "vehicles": 5, "distance": 1.0},
        },
    )
    win_panel = PanelMetrics(
        feasible=4,
        total=4,
        vehicles_sum=19,
        distance_sum=940.0,
        by_instance={
            "c101C5": {"ok": True, "vehicles": 4, "distance": 1.0},
            "c103C5": {"ok": True, "vehicles": 5, "distance": 1.0},
            "r104C5": {"ok": True, "vehicles": 5, "distance": 1.0},
            "r105C5": {"ok": True, "vehicles": 5, "distance": 1.0},
        },
    )
    c5 = PanelMetrics(feasible=12, total=12, vehicles_sum=60, distance_sum=1.0, by_instance={})

    def fake_eval(solver_dir, instances, *, limits=None):  # noqa: ANN001
        if len(instances) > 4:
            return c5, []
        # always return win after first so milestone hits early but run continues
        return win_panel if "candidates" in str(solver_dir) else parent_panel, []

    monkeypatch.setattr(evolve_mod, "evaluate_panel", fake_eval)
    monkeypatch.setattr(evolve_mod, "validate_source", lambda *a, **k: (True, "ok"))
    good = _reply(
        [{"action": "ADD", "symbol": "h2", "code": "def h2(x):\n    return x\n"}],
        "x",
    )
    # Distinct symbols per role to avoid ADD collisions across generations
    replies = {
        "architect": [good],
        "routing": [_reply([{"action": "ADD", "symbol": "h3", "code": "def h3(x):\n    return x\n"}])],
        "charging": [_reply([{"action": "ADD", "symbol": "h4", "code": "def h4(x):\n    return x\n"}])],
        "search": [_reply([{"action": "ADD", "symbol": "h5", "code": "def h5(x):\n    return x\n"}])],
        "critic_inventor": [
            _reply([{"action": "ADD", "symbol": "h6", "code": "def h6(x):\n    return x\n"}])
        ],
    }
    backend = FakeBackend(replies)
    result = run_evolution(
        model="fake",
        backend=backend,
        workspace=tmp_path / "evo_cont",
        parent_solver=FROZEN,
        max_generations=2,
        candidates_per_role=1,
        beam_size=1,
        max_llm_calls=80,
        stop_on_milestone=False,
        seed_base=22,
    )
    assert result["generations"] == 2
    assert result["milestone_hit"] is True

