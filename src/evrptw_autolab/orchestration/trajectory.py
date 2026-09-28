"""Append-only algorithm-development trajectories. Not a solver."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def append_trajectory(workspace: Path, record: dict[str, Any]) -> Path:
    path = Path(workspace) / "trajectories.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp": datetime.now(UTC).isoformat(), **record}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")
    return path


def load_trajectories(workspace: Path) -> list[dict[str, Any]]:
    path = Path(workspace) / "trajectories.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
