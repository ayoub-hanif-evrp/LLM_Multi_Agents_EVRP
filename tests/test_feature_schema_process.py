"""Feature-schema version survives the real hard-timeout solver process."""
from __future__ import annotations

from pathlib import Path

import pytest

from evrptw_autolab.backbone.solver import solve_classical
from evrptw_autolab.components.expressions import repair_prompt, wrap_expression
from evrptw_autolab.components.loader import load_bundle, write_bundle
from evrptw_autolab.problem.datasets.montoya import load_montoya
from evrptw_autolab.problem.v2.features import FEATURE_SCHEMA_V2, FEATURE_SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]


def _bundle(schema: str):
    bundle, errors = load_bundle(
        {
            "insertion_score": wrap_expression("insertion_score", "delta_distance"),
            "station_score": wrap_expression("station_score", "battery_arrival"),
            "removal_priority": wrap_expression("removal_priority", "due_time"),
        },
        feature_schema=schema,
    )
    assert not errors
    return bundle


def test_unknown_schema_is_rejected_and_bundle_json_records_the_version(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown station feature schema"):
        load_bundle({}, feature_schema="2099-01-01.v9")
    bundle = _bundle(FEATURE_SCHEMA_V2)
    path = write_bundle(bundle, tmp_path)
    text = path.read_text(encoding="utf-8")
    assert FEATURE_SCHEMA_V2 in text
    assert "battery_arrival is physical energy" in repair_prompt("station_score", "bad")


def test_solver_process_restores_v1_physical_and_v2_ratio_battery() -> None:
    spec = load_montoya(ROOT / "dataset" / "montoya-et-al-2017" / "tc0c10s2cf1.xml")
    observed: dict[str, float] = {}
    for schema, expect_ratio in ((FEATURE_SCHEMA_VERSION, False), (FEATURE_SCHEMA_V2, True)):
        solution = solve_classical(
            spec,
            seed=7,
            time_limit_s=4.0,
            alns_iterations=15,
            policy=_bundle(schema),
        )
        assert solution.metadata["feature_schema"] == schema
        calls = int((solution.metadata.get("scorer_calls") or {}).get("station_score") or 0)
        assert calls > 0
        battery_max = float(solution.metadata["station_battery_argument_max"])
        observed[schema] = battery_max
        if expect_ratio:
            assert 0.0 <= battery_max <= 1.0
        else:
            assert battery_max > 1.0
    assert observed[FEATURE_SCHEMA_VERSION] > observed[FEATURE_SCHEMA_V2]
