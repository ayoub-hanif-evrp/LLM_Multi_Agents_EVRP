"""Unit tests for SLM-Evo AST patch applicator."""
from __future__ import annotations

from pathlib import Path

import pytest

from evrptw_autolab.slm_evo.patch_apply import apply_ops, parse_proposal_json
from evrptw_autolab.slm_evo.types import PatchOp

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "tests" / "fixtures" / "feasible_parent" / "solver.py"


@pytest.fixture
def parent_src() -> str:
    assert FROZEN.exists(), f"missing frozen solver {FROZEN}"
    return FROZEN.read_text(encoding="utf-8")


def test_add_helper_then_replace_solve(parent_src: str) -> None:
    helper = (
        "def pack_hint(instance):\n"
        "    return list(instance.customer_ids)\n"
    )
    new_solve = (
        "def solve(instance, seed: int, time_limit_s: float):\n"
        "    from evrptw_autolab.problem.physics import propagate_route\n"
        "    depot = instance.depot_id\n"
        "    routes = []\n"
        "    for cid in pack_hint(instance):\n"
        "        route = [depot, cid, depot]\n"
        "        states = propagate_route(instance, route)\n"
        "        if all(s.battery_arrival >= 0 for s in states):\n"
        "            routes.append(route)\n"
        "            continue\n"
        "        for station_id in instance.station_ids:\n"
        "            for i in range(1, len(route)):\n"
        "                new_route = route[:i] + [station_id] + route[i:]\n"
        "                new_states = propagate_route(instance, new_route)\n"
        "                if all(s.battery_arrival >= 0 for s in new_states):\n"
        "                    routes.append(new_route)\n"
        "                    break\n"
        "            else:\n"
        "                continue\n"
        "            break\n"
        "    return {'routes': routes, 'metadata': {'seed': seed}}\n"
    )
    result = apply_ops(
        parent_src,
        [
            PatchOp("ADD", "pack_hint", helper),
            PatchOp("REPLACE", "solve", new_solve),
        ],
    )
    assert result.ok, result.error
    assert "def pack_hint" in result.source
    assert "def solve" in result.source
    assert "pack_hint(instance)" in result.source


def test_remove_helper(parent_src: str) -> None:
    helper = "def tmp_fn(x):\n    return x\n"
    added = apply_ops(parent_src, [PatchOp("ADD", "tmp_fn", helper)])
    assert added.ok
    removed = apply_ops(added.source, [PatchOp("REMOVE", "tmp_fn", "")])
    assert removed.ok
    assert "def tmp_fn" not in removed.source
    assert "def solve" in removed.source


def test_reject_remove_solve_alone(parent_src: str) -> None:
    result = apply_ops(parent_src, [PatchOp("REMOVE", "solve", "")])
    assert not result.ok
    assert "solve" in result.error.lower()


def test_reject_add_collision(parent_src: str) -> None:
    result = apply_ops(
        parent_src,
        [PatchOp("ADD", "solve", "def solve(instance, seed: int, time_limit_s: float):\n    return {'routes': [], 'metadata': {}}\n")],
    )
    assert not result.ok
    assert "collision" in result.error.lower()


def test_reject_replace_missing(parent_src: str) -> None:
    result = apply_ops(
        parent_src,
        [PatchOp("REPLACE", "nope", "def nope():\n    return 1\n")],
    )
    assert not result.ok


def test_parse_proposal_json() -> None:
    prop = parse_proposal_json(
        {
            "hypothesis": "add helper",
            "ops": [{"action": "ADD", "symbol": "f", "code": "def f():\n    return 1\n"}],
        },
        role="routing",
        seed=11,
    )
    assert prop.role == "routing"
    assert prop.ops[0].action == "ADD"
