"""Write comparison tables for homogeneous five-agent × model experiments."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_model_table(rows: list[dict[str, Any]], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
    lines = ["model_id,model,team_mode,status,feasible,vehicles,distance"]
    for row in rows:
        lines.append(
            ",".join(
                str(row.get(key, ""))
                for key in ("model_id", "model", "team_mode", "status", "feasible", "vehicles", "distance")
            )
        )
    path.with_suffix(".csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
