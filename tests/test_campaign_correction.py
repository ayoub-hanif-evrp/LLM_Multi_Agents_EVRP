"""Historical Qwen token correction and expression contract."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.components.expressions import (
    materialize_component,
    normalize_llm_source,
    wrap_expression,
)
from evrptw_autolab.components.interpret import UnsafeComponent, compile_component
from evrptw_autolab.experiments.correct_campaign import correct_campaign

ROOT = Path(__file__).resolve().parents[1]
QWEN = ROOT / "results" / "v2" / "campaigns" / "campaign_20261016T002039Z"


def test_qwen_evolution_tokens_are_not_multiplied(tmp_path: Path) -> None:
    summary = correct_campaign(QWEN, tmp_path)
    assert summary["evolution_llm_tokens"] == 2621
    assert summary["incorrect_sum_if_repeated_per_instance"] == 13105
    assert summary["winner_status"] == "NO_LLM_WINNER"
    assert summary["raw_files_modified"] is False
    runs = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(runs) == 1
    rows = (tmp_path / "instance_results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 5
    assert "2621" not in rows[0] or "llm_tokens" not in rows[0]


def test_expression_wraps_to_single_return() -> None:
    source = wrap_expression("station_score", "detour + 0.1 * station_rate")
    fn = compile_component("station_score", source)
    assert fn(2.0, 10.0, 1.0) == 2.1


def test_doubly_escaped_newlines_normalize() -> None:
    raw = (
        "def station_score(detour: float, battery_arrival: float, station_rate: float) -> float:\\n"
        "    return detour\\n"
    )
    fixed = normalize_llm_source(raw)
    assert "\n" in fixed
    assert "\\n" not in fixed
    fn = compile_component("station_score", fixed)
    assert fn(3.0, 0.0, 0.0) == 3.0


def test_expression_rejects_statements() -> None:
    try:
        wrap_expression("insertion_score", "import os")
    except UnsafeComponent:
        return
    raise AssertionError("import must be rejected")


def test_materialize_prefers_expression() -> None:
    source, status = materialize_component(
        "removal_priority",
        {"expression": "due_time + route_distance_share"},
    )
    assert status == "expression_wrapped"
    fn = compile_component("removal_priority", source)
    assert fn(10.0, 2.0, 0.0) == 12.0
