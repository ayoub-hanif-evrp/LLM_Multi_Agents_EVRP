"""Agent / Ollama configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RoleTemperatureConfig(BaseModel):
    analyst: float = 0.10
    scientist: float = 0.55


class OllamaConfig(BaseModel):
    model: str = "qwen3:4b"
    fallback_model: str | None = None
    base_url: str = "http://127.0.0.1:11434"
    num_ctx: int = 8192
    stream: bool = False
    keep_alive: str = "30m"
    seed: int = 42
    request_timeout_seconds: float = 300.0
    max_schema_retries: int = 2
    temperatures: RoleTemperatureConfig = Field(default_factory=RoleTemperatureConfig)


class AgentLimitsConfig(BaseModel):
    max_mechanisms: int = 5
    required_hypotheses: int = 3
    evidence_value_tolerance: float = 1e-6
    diversity_text_similarity_max: float = 0.85
    diversity_primitive_overlap_max: float = 0.75
    diversity_mechanism_overlap_max: float = 0.75


class AgentsConfig(BaseModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    limits: AgentLimitsConfig = Field(default_factory=AgentLimitsConfig)
    backend: str = "ollama"  # ollama | mock | replay
    mock_fixture_dir: str | None = None
    replay_dir: str | None = None


def load_agents_config(path: Path | None = None) -> AgentsConfig:
    if path is None:
        return AgentsConfig()
    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    ollama_raw = dict(raw.get("ollama") or {})
    temps = ollama_raw.pop("temperatures", None) or {}
    agents_raw = dict(raw.get("agents") or {})
    if "analyst" in agents_raw and "temperature" in agents_raw["analyst"]:
        temps = {**temps, "analyst": agents_raw["analyst"]["temperature"]}
    if "scientist" in agents_raw and "temperature" in agents_raw["scientist"]:
        temps = {**temps, "scientist": agents_raw["scientist"]["temperature"]}
    ollama_raw["temperatures"] = temps
    limits = dict(raw.get("agent_limits") or agents_raw.get("limits") or {})
    return AgentsConfig(
        ollama=OllamaConfig.model_validate(ollama_raw),
        limits=AgentLimitsConfig.model_validate(limits),
        backend=str(raw.get("agent_backend") or agents_raw.get("backend") or "ollama"),
        mock_fixture_dir=raw.get("mock_fixture_dir") or agents_raw.get("mock_fixture_dir"),
        replay_dir=raw.get("replay_dir") or agents_raw.get("replay_dir"),
    )
