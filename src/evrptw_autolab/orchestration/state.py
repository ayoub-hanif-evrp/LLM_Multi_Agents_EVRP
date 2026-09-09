"""Persisted campaign state."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class CampaignState:
    campaign_id: str
    model: str
    model_id: str = ""
    team_mode: str = "five_agent"
    cycle: int = 0
    elite_id: str | None = None
    activated_history: list[dict[str, object]] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CampaignState:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(**raw)
