from __future__ import annotations

from pathlib import Path

import pytest

from evrptw_autolab.problem.schneider import load_instance

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "dataset" / "schneider" / "raw_instances"


@pytest.fixture
def c101c5():
    return load_instance(DATA_ROOT / "c101C5.txt")
