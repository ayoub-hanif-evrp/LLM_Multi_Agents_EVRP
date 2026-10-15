"""Classical baseline pilot smoke (small panel subset)."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.baselines.classical_pilot import development_panel, run_one, write_results


def test_development_panel_covers_five_families() -> None:
    panel = development_panel()
    families = {item.family for item in panel}
    assert families == {"schneider", "montoya", "bezzi", "goeke", "hiermann"}


def test_write_results_roundtrip(tmp_path: Path) -> None:
    panel = [item for item in development_panel() if item.family == "schneider"][:1]
    assert panel
    row = run_one(panel[0], seed=1)
    paths = write_results([row], tmp_path)
    assert paths["json"].exists()
    assert paths["csv"].exists()
    assert paths["summary"].exists()
