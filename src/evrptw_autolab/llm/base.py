"""LLM backend protocol."""
from __future__ import annotations

from typing import Protocol


class LLMBackend(Protocol):
    def complete(self, *, prompt: str, role: str, temperature: float, model: str) -> str: ...
