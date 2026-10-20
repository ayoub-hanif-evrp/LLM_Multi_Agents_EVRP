"""Save one agentic run. Historical ALNS results are not written here."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "results" / "agentic_v2" / "runs"


def write_run(record: dict[str, Any], directory: Path | None = None) -> Path:
    out = directory or RUNS
    out.mkdir(parents=True, exist_ok=True)
    name = f"{record.get('family')}_{record.get('instance_id')}.json"
    path = out / name
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    if directory is None:
        _write_piece("solutions", name, record.get("solution"))
        _write_piece("evaluations", name, record.get("evaluation"))
        _write_piece("agent_traces", name, record.get("agent_trace"))
    return path


def _write_piece(folder: str, name: str, payload: Any) -> None:
    if payload is None:
        return
    destination = ROOT / "results" / "agentic_v2" / folder
    destination.mkdir(parents=True, exist_ok=True)
    (destination / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def already_recorded(family: str, instance_id: str, directory: Path | None = None) -> bool:
    path = (directory or RUNS) / f"{family}_{instance_id}.json"
    return path.exists()
