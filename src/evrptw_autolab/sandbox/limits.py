"""Runtime limits for sandboxed generated solvers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RunLimits:
    wall_clock_s: float = 10.0
    memory_mb: int = 1024


def limits_from_synthesis(*, default_s: float = 20.0) -> RunLimits:
    path = ROOT / "configs" / "synthesis.yaml"
    wall = default_s
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        wall = float((raw.get("cycle") or {}).get("wall_clock_s") or default_s)
    return RunLimits(wall_clock_s=wall)
