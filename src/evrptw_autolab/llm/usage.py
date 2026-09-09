"""Usage records for every LLM call."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class LLMUsage:
    model_id: str
    provider: str
    role: str
    latency_s: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    retry_count: int = 0
    parse_valid: bool = False
    code_valid: bool = False
    digest: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class UsageLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, usage: LLMUsage) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(usage.as_dict()) + "\n")

    def all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
