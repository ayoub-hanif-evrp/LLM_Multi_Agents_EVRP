"""Bounded check that a backend emits executable nondefault scoring expressions."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evrptw_autolab.agents.base import extract_json
from evrptw_autolab.components.expressions import materialize_component, repair_prompt
from evrptw_autolab.components.interfaces import DEFAULT_SOURCES, ComponentKind
from evrptw_autolab.components.loader import validate_component_source

KINDS: tuple[ComponentKind, ...] = ("insertion_score", "station_score", "removal_priority")
PROMPTS = {
    "insertion_score": "routing",
    "station_score": "charging",
    "removal_priority": "search",
}


def _prompt(name: str) -> str:
    path = Path(__file__).resolve().parents[3] / "prompts" / "components" / f"{name}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def probe_expressions(backend: Any, *, model: str = "fake") -> dict[str, Any]:
    """One generation attempt per component, plus one repair if the first fails."""
    rows = []
    for kind in KINDS:
        role = PROMPTS[kind]
        raw = backend.complete(
            prompt=_prompt(role),
            role=role,
            temperature=0.2,
            model=model,
            json_mode=True,
        )
        payload = extract_json(raw)
        source, status = materialize_component(kind, payload)
        ok = bool(source) and bool(validate_component_source(kind, source).get("ok"))
        repaired = False
        if not ok:
            raw2 = backend.complete(
                prompt=repair_prompt(kind, status),
                role=role,
                temperature=0.0,
                model=model,
                json_mode=True,
            )
            payload = extract_json(raw2)
            source, status = materialize_component(kind, payload)
            ok = bool(source) and bool(validate_component_source(kind, source).get("ok"))
            repaired = True
        is_default = bool(source) and source.strip() == DEFAULT_SOURCES[kind].strip()
        rows.append(
            {
                "component": kind,
                "status": status,
                "expression": str(payload.get("expression") or ""),
                "validated": ok,
                "repaired": repaired,
                "nondefault": bool(ok and not is_default),
                "fallback": not ok,
            }
        )
    n = len(rows)
    return {
        "model": model,
        "n": n,
        "validated": sum(1 for row in rows if row["validated"]),
        "nondefault": sum(1 for row in rows if row["nondefault"]),
        "fallback": sum(1 for row in rows if row["fallback"]),
        "rows": rows,
    }


def write_probe(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
