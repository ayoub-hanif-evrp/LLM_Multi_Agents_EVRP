"""Ollama chat backend. Failures stay failed after one JSON-repair retry.

Empty ``message.content`` is never treated as a valid solver, even when
``message.thinking`` is present. Thinking text is recorded separately on usage.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from evrptw_autolab.llm.usage import LLMUsage

ROLE_CODE = {
    "architect": 1,
    "routing": 2,
    "charging": 3,
    "search": 4,
    "critic": 5,
    "single": 6,
    "critic_inventor": 7,
}


def derived_call_seed(base_seed: int, call_index: int, role: str) -> int:
    """Reproducible per-call seed. The run seed stays fixed; each generation differs."""
    role_code = ROLE_CODE.get(role, 9)
    return int(base_seed) * 10000 + int(call_index) * 10 + role_code


@dataclass
class ModelInfo:
    """Immutable snapshot of an installed Ollama model."""

    name: str
    digest: str | None = None
    size_bytes: int | None = None
    family: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class OllamaScheduler:
    """Serialize large-model generations on a single GPU by default."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active_model: str | None = None

    def acquire(self, model: str) -> None:
        self._lock.acquire()
        self.active_model = model

    def release(self) -> None:
        self.active_model = None
        self._lock.release()


_GLOBAL_SCHEDULER = OllamaScheduler()


class OllamaBackend:
    def __init__(
        self,
        *,
        host: str = "http://127.0.0.1:11434",
        timeout_s: float = 300.0,
        num_ctx: int = 8192,
        num_predict: int | None = None,
        top_p: float | None = None,
        keep_alive: str = "20m",
        seed: int | None = None,
        scheduler: OllamaScheduler | None = None,
        serialize_calls: bool = True,
    ) -> None:
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self.num_ctx = num_ctx
        self.num_predict = num_predict
        self.top_p = top_p
        self.keep_alive = keep_alive
        self.seed = seed
        self.diversify_calls = False
        self.serialize_calls = serialize_calls
        self.scheduler = scheduler or _GLOBAL_SCHEDULER
        self._call_index = 0
        self.last_derived_seed: int | None = None
        self.last_usage: LLMUsage | None = None
        self.last_thinking: str | None = None
        self.pending_usages: list[LLMUsage] = []
        self.ollama_version: str | None = None

    def available(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.host}/api/tags", timeout=2.0)
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def server_version(self) -> str | None:
        """Best-effort Ollama version from /api/version when available."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/version", timeout=3.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            version = str(payload.get("version") or "") or None
            self.ollama_version = version
            return version
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, TypeError):
            return self.ollama_version

    def installed_models(self) -> set[str]:
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return set()
        names: set[str] = set()
        for item in payload.get("models") or []:
            name = str(item.get("name") or "")
            if name:
                names.add(name)
                names.add(name.split(":")[0])
        return names

    def list_model_info(self) -> list[ModelInfo]:
        """Return installed models with digests/sizes from /api/tags."""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return []
        out: list[ModelInfo] = []
        for item in payload.get("models") or []:
            name = str(item.get("name") or "")
            if not name:
                continue
            details = dict(item.get("details") or {})
            out.append(
                ModelInfo(
                    name=name,
                    digest=str(item.get("digest") or "") or None,
                    size_bytes=int(item["size"]) if item.get("size") is not None else None,
                    family=str(details.get("family") or "") or None,
                    parameter_size=str(details.get("parameter_size") or "") or None,
                    quantization=str(details.get("quantization_level") or "") or None,
                    details=details,
                )
            )
        return out

    def show_model(self, model: str) -> dict[str, Any]:
        """Query /api/show for capabilities; empty dict on failure."""
        body = json.dumps({"name": model}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/show",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

    def capability_smoke(self, model: str) -> dict[str, Any]:
        """Cheap pre-flight: tags presence + /api/show details (no generation)."""
        installed = self.installed_models()
        present = model in installed or model.split(":")[0] in installed
        info = self.show_model(model) if present else {}
        digest = next((m.digest for m in self.list_model_info() if m.name == model), None)
        return {
            "model": model,
            "server_up": self.available(),
            "installed": present,
            "ollama_version": self.server_version(),
            "digest": digest,
            "details": dict(info.get("details") or {}),
            "capabilities": info.get("capabilities"),
        }

    def _seed_for(self, role: str) -> int | None:
        if self.seed is None:
            return None
        if not self.diversify_calls:
            return int(self.seed)
        self._call_index += 1
        derived = derived_call_seed(int(self.seed), self._call_index, role)
        self.last_derived_seed = derived
        return derived

    def _post_chat(
        self,
        prompt: str,
        model: str,
        temperature: float,
        *,
        json_mode: bool,
        role: str,
        format_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": temperature, "num_ctx": self.num_ctx}
        if self.num_predict is not None:
            options["num_predict"] = int(self.num_predict)
        if self.top_p is not None:
            options["top_p"] = float(self.top_p)
        call_seed = self._seed_for(role)
        if call_seed is not None:
            options["seed"] = int(call_seed)
        fmt: Any = False
        if format_schema is not None:
            fmt = format_schema
        elif json_mode:
            fmt = "json"
        body_obj: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": options,
        }
        if fmt is not False:
            body_obj["format"] = fmt
        body = json.dumps(body_obj).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Ollama response was not an object")
        return payload

    @staticmethod
    def extract_message_parts(payload: dict[str, Any]) -> tuple[str, str]:
        """Return (content, thinking). Thinking alone is never valid solver text."""
        message = payload.get("message") or {}
        if not isinstance(message, dict):
            return "", ""
        content = str(message.get("content") or "")
        thinking = str(message.get("thinking") or message.get("reasoning") or "")
        return content, thinking

    def _remember(
        self,
        payload: dict[str, Any],
        *,
        role: str,
        model: str,
        latency_s: float,
        repair: bool,
        thinking: str,
        content_empty: bool,
    ) -> None:
        tag = str(payload.get("model") or model)
        usage = LLMUsage(
            model_id=tag,
            provider="ollama",
            role=role,
            latency_s=latency_s,
            retry_count=1 if repair else 0,
            repair=repair,
            digest=str(payload.get("digest") or "") or None,
            prompt_tokens=int(payload.get("prompt_eval_count") or 0),
            completion_tokens=int(payload.get("eval_count") or 0),
            seed=self.last_derived_seed if self.diversify_calls else self.seed,
            base_seed=int(self.seed) if self.seed is not None else None,
            call_index=self._call_index if self.diversify_calls else None,
            model_tag=tag,
            thinking_chars=len(thinking) if thinking else 0,
            content_empty=content_empty,
            ollama_version=self.ollama_version,
            num_ctx=self.num_ctx,
        )
        self.pending_usages.append(usage)
        self.last_usage = usage

    def complete(
        self,
        *,
        prompt: str,
        role: str,
        temperature: float,
        model: str,
        json_mode: bool = True,
        format_schema: dict[str, Any] | None = None,
    ) -> str:
        """Return model text. Every completed generation is appended to pending_usages."""
        self.pending_usages = []
        self.last_thinking = None

        def once(text: str, *, repair: bool) -> str:
            started = time.monotonic()
            if self.serialize_calls:
                self.scheduler.acquire(model)
            try:
                payload = self._post_chat(
                    text,
                    model,
                    temperature,
                    json_mode=json_mode,
                    role=role,
                    format_schema=format_schema,
                )
            finally:
                if self.serialize_calls:
                    self.scheduler.release()
            content, thinking = self.extract_message_parts(payload)
            self.last_thinking = thinking or None
            self._remember(
                payload,
                role=role,
                model=model,
                latency_s=time.monotonic() - started,
                repair=repair,
                thinking=thinking,
                content_empty=not bool(content.strip()),
            )
            if not content.strip():
                raise ValueError(
                    "empty Ollama content"
                    + ("; thinking present but not accepted as solver output" if thinking else "")
                )
            return content

        try:
            return once(prompt, repair=False)
        except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as first:
            repair_prompt = prompt + (
                "\n\nReply with ONLY one valid JSON object."
                if json_mode or format_schema is not None
                else "\n\nReply with ONLY Python source. No JSON."
            )
            try:
                return once(repair_prompt, repair=True)
            except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as second:
                raise RuntimeError(f"Ollama failed for role={role} model={model}: {second}") from first
