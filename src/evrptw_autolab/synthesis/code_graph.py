"""Directed solver lineage graph."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class SolverNode:
    solver_id: str
    parent: str | None
    code_hash: str
    agent_role: str
    model: str
    hypothesis: str
    status: str
    path: str
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    evaluation_summary: dict[str, Any] = field(default_factory=dict)


class CodeGraph:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "graph.json"
        self.nodes: dict[str, SolverNode] = {}
        if self.path.exists():
            for raw in json.loads(self.path.read_text(encoding="utf-8")):
                node = SolverNode(**raw)
                self.nodes[node.solver_id] = node

    def add(self, node: SolverNode) -> None:
        self.nodes[node.solver_id] = node
        self.save()

    def save(self) -> None:
        payload = [asdict(node) for node in self.nodes.values()]
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def get(self, solver_id: str) -> SolverNode:
        return self.nodes[solver_id]
