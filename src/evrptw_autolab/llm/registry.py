"""Central model registry. Missing models are SKIPPED_NOT_INSTALLED, never substituted."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.openai_compatible import OpenAICompatibleBackend

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODELS = ROOT / "configs" / "models.yaml"
SKIPPED_NOT_INSTALLED = "SKIPPED_NOT_INSTALLED"


class FakeBackend:
    """Deterministic fixture backend for tests. Maps role -> JSON text or a sequence of replies."""

    def __init__(self, replies: dict[str, str | list[str]]) -> None:
        self.replies = {key: ([value] if isinstance(value, str) else list(value)) for key, value in replies.items()}
        self.indexes = dict.fromkeys(self.replies, 0)
        self.calls: list[str] = []
        self.last_usage = None

    def complete(self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True) -> str:
        self.calls.append(role)
        if role not in self.replies:
            raise KeyError(f"FakeBackend has no reply for role={role}")
        sequence = self.replies[role]
        index = min(self.indexes[role], len(sequence) - 1)
        self.indexes[role] += 1
        return sequence[index]


@dataclass(frozen=True)
class ModelProfile:
    id: str
    provider: str
    model: str
    enabled: bool = True
    timeout_s: float = 300.0
    num_ctx: int = 8192
    temperatures: dict[str, float] | None = None
    base_url: str | None = None


def load_models_config(path: Path | None = None) -> dict[str, Any]:
    with (path or DEFAULT_MODELS).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def list_profiles(config: dict[str, Any] | None = None) -> list[ModelProfile]:
    cfg = config if config is not None else load_models_config()
    profiles: list[ModelProfile] = []
    for model_id, raw in (cfg.get("models") or {}).items():
        profiles.append(
            ModelProfile(
                id=str(model_id),
                provider=str(raw.get("provider", "ollama")),
                model=str(raw["model"]),
                enabled=bool(raw.get("enabled", True)),
                timeout_s=float(raw.get("timeout_s", (cfg.get("provider_defaults") or {}).get("ollama", {}).get("timeout_s", 300))),
                num_ctx=int(raw.get("num_ctx", 8192)),
                temperatures=dict(raw.get("temperature_defaults") or {}),
                base_url=raw.get("base_url"),
            )
        )
    return profiles


def resolve_profile(model_id: str, config: dict[str, Any] | None = None) -> ModelProfile:
    for profile in list_profiles(config):
        if profile.id == model_id:
            return profile
    raise KeyError(f"unknown model profile: {model_id}")


def availability(profile: ModelProfile, backend: OllamaBackend | None = None) -> str:
    if profile.provider != "ollama":
        return "configured"
    ollama = backend or OllamaBackend()
    if not ollama.available():
        return "SKIPPED_OLLAMA_UNAVAILABLE"
    installed = ollama.installed_models()
    if profile.model in installed or profile.model.split(":")[0] in installed:
        return "installed"
    return SKIPPED_NOT_INSTALLED


def make_backend(profile: ModelProfile, *, ollama_host: str = "http://127.0.0.1:11434") -> Any:
    if profile.provider == "ollama":
        return OllamaBackend(host=ollama_host, timeout_s=profile.timeout_s, num_ctx=profile.num_ctx)
    if profile.provider == "openai_compatible":
        return OpenAICompatibleBackend(
            base_url=profile.base_url or "https://api.openai.com/v1", timeout_s=profile.timeout_s
        )
    raise ValueError(f"unsupported provider: {profile.provider}")
