"""Central model registry. Missing models are SKIPPED_NOT_INSTALLED, never substituted."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.openai_compatible import OpenAICompatibleBackend

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MODELS = ROOT / "configs" / "models.yaml"
SKIPPED_NOT_INSTALLED = "SKIPPED_NOT_INSTALLED"
SKIPPED_NO_CREDENTIAL = "SKIPPED_NO_CREDENTIAL"


class FakeBackend:
    """Deterministic fixture backend for tests. Maps role -> JSON text or a sequence of replies.

    Optional ``token_sequence`` injects known usage values for budget tests.
    Optional ``fail_then_succeed`` forces a first HTTP failure then a retry success.
    """

    def __init__(
        self,
        replies: dict[str, str | list[str]],
        *,
        token_sequence: list[int] | None = None,
        fail_first_n: int = 0,
    ) -> None:
        from evrptw_autolab.llm.usage import LLMUsage

        self.replies = {key: ([value] if isinstance(value, str) else list(value)) for key, value in replies.items()}
        self.indexes = dict.fromkeys(self.replies, 0)
        self.calls: list[str] = []
        self.last_usage: LLMUsage | None = None
        self.pending_usages: list[LLMUsage] = []
        self.token_sequence = list(token_sequence or [])
        self._token_index = 0
        self.fail_first_n = int(fail_first_n)
        self._fail_count = 0
        self.provider = "fake"

    @property
    def last_tokens(self) -> int:
        if self.pending_usages:
            return sum(u.total_tokens for u in self.pending_usages)
        if self.last_usage is not None:
            return self.last_usage.total_tokens
        return 0

    def _next_tokens(self) -> int:
        if self._token_index < len(self.token_sequence):
            value = int(self.token_sequence[self._token_index])
            self._token_index += 1
            return value
        return 0

    def complete(
        self,
        *,
        prompt: str,
        role: str,
        temperature: float,
        model: str,
        json_mode: bool = True,
        **kwargs: Any,
    ) -> str:
        from evrptw_autolab.llm.usage import LLMUsage

        self.calls.append(role)
        self.pending_usages = []
        if role not in self.replies:
            raise KeyError(f"FakeBackend has no reply for role={role}")

        def _record(*, repair: bool, failed: bool, tokens: int) -> None:
            usage = LLMUsage(
                model_id=model,
                provider="fake",
                role=role,
                latency_s=0.0,
                prompt_tokens=0,
                completion_tokens=tokens,
                retry_count=1 if repair else 0,
                repair=repair,
                failed=failed,
            )
            self.pending_usages.append(usage)
            self.last_usage = usage

        if self._fail_count < self.fail_first_n:
            self._fail_count += 1
            _record(repair=False, failed=True, tokens=self._next_tokens())
            # Successful retry attempt (mirrors Ollama's one repair).
            tokens = self._next_tokens()
            sequence = self.replies[role]
            index = min(self.indexes[role], len(sequence) - 1)
            self.indexes[role] += 1
            _record(repair=True, failed=False, tokens=tokens)
            return sequence[index]

        sequence = self.replies[role]
        index = min(self.indexes[role], len(sequence) - 1)
        self.indexes[role] += 1
        _record(repair=False, failed=False, tokens=self._next_tokens())
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
    api_key_env: str | None = None
    base_url_env: str | None = None
    default_base_url: str | None = None
    note: str | None = None


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
                timeout_s=float(
                    raw.get(
                        "timeout_s",
                        (cfg.get("provider_defaults") or {})
                        .get("ollama", {})
                        .get("timeout_s", 300),
                    )
                ),
                num_ctx=int(raw.get("num_ctx", 8192)),
                temperatures=dict(raw.get("temperature_defaults") or {}),
                base_url=raw.get("base_url"),
                api_key_env=str(raw["api_key_env"]) if raw.get("api_key_env") else None,
                base_url_env=str(raw["base_url_env"]) if raw.get("base_url_env") else None,
                default_base_url=(
                    str(raw["default_base_url"]) if raw.get("default_base_url") else None
                ),
                note=str(raw["note"]) if raw.get("note") else None,
            )
        )
    return profiles


def resolve_profile(model_id: str, config: dict[str, Any] | None = None) -> ModelProfile:
    for profile in list_profiles(config):
        if profile.id == model_id:
            return profile
    raise KeyError(f"unknown model profile: {model_id}")


def availability(profile: ModelProfile, backend: OllamaBackend | None = None) -> str:
    if profile.provider == "openai_compatible":
        env_name = profile.api_key_env or "OPENAI_API_KEY"
        key = os.environ.get(env_name, "")
        if key and str(key).strip():
            return "installed"
        return SKIPPED_NO_CREDENTIAL
    if profile.provider != "ollama":
        return "configured"
    ollama = backend or OllamaBackend()
    if not ollama.available():
        return "SKIPPED_OLLAMA_UNAVAILABLE"
    installed = ollama.installed_models()
    if profile.model in installed or profile.model.split(":")[0] in installed:
        return "installed"
    return SKIPPED_NOT_INSTALLED


def _resolve_openai_base_url(profile: ModelProfile) -> str:
    if profile.base_url:
        return str(profile.base_url)
    if profile.base_url_env:
        from_env = os.environ.get(profile.base_url_env, "")
        if from_env and from_env.strip():
            return from_env.strip()
    if profile.default_base_url:
        return str(profile.default_base_url)
    return "https://api.openai.com/v1"


def make_backend(profile: ModelProfile, *, ollama_host: str = "http://127.0.0.1:11434") -> Any:
    if profile.provider == "ollama":
        return OllamaBackend(host=ollama_host, timeout_s=profile.timeout_s, num_ctx=profile.num_ctx)
    if profile.provider == "openai_compatible":
        return OpenAICompatibleBackend(
            base_url=_resolve_openai_base_url(profile),
            api_key_env=profile.api_key_env or "OPENAI_API_KEY",
            timeout_s=profile.timeout_s,
        )
    raise ValueError(f"unsupported provider: {profile.provider}")
