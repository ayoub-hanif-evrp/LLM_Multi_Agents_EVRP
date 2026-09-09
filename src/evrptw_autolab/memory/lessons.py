"""Persistent mechanism lessons. Not a sixth agent."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LessonMemory:
    def __init__(self, path: Path, *, max_total: int = 100) -> None:
        self.path = path
        self.max_total = max_total
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, lesson: dict[str, Any]) -> None:
        rows = self.all()
        rows.append(lesson)
        rows = rows[-self.max_total :]
        self.path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def retrieve(self, query: str | dict[str, Any], k: int = 5) -> list[dict[str, Any]]:
        """Score lessons by mechanism fields; accept legacy string queries."""
        if isinstance(query, str):
            query = {"target": query}
        target = str(query.get("target") or "").upper()
        family = str(query.get("family") or query.get("fault") or "").upper()
        instance_family = str(query.get("instance_family") or "").upper()
        component = str(query.get("component") or query.get("changed_function") or "").upper()
        scored: list[tuple[int, int, dict[str, Any]]] = []
        rows = self.all()
        for index, row in enumerate(rows):
            score = 0
            row_target = str(row.get("target") or row.get("next_target") or "").upper()
            row_family = str(row.get("family") or row.get("fault") or "").upper()
            row_ifam = str(row.get("instance_family") or row.get("family_name") or "").upper()
            row_comp = str(row.get("changed_function") or row.get("component") or "").upper()
            if target and target in row_target:
                score += 3
            if family and family == row_family:
                score += 3
            if instance_family and instance_family == row_ifam:
                score += 2
            if component and component and component in row_comp:
                score += 2
            if str(row.get("decision") or "").upper() == "RETAIN":
                score += 1
            # legacy substring fallback
            blob = json.dumps(row).upper()
            if score == 0 and target and target in blob:
                score += 1
            scored.append((score, index, row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [row for score, _, row in scored[:k] if score > 0 or not target]
