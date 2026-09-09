"""Snapshot of a generated solver candidate."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CandidateSolver:
    solver_id: str
    path: Path
    parent: str | None = None
    model: str = ""
    hypothesis: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
