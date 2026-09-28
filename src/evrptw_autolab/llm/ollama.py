"""Ollama chat backend. Failures stay failed after one JSON-repair retry."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from evrptw_autolab.llm.usage import LLMUsage


class OllamaBackend:
    def __init__(
        self,
        *,
        host: str = "http://127.0.0.1:11434",
        timeout_s: float = 300.0,
        num_ctx: int = 8192,
        keep_alive: str = "20m",
        seed: int | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.timeout_s = timeout_s
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.seed = seed
        self.last_usage: LLMUsage | None = None

    def available(self) -> bool:
        try:
            urllib.request.urlopen(f"{self.host}/api/tags", timeout=2.0)
            return True
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

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

    def _chat(
        self, prompt: str, model: str, temperature: float, *, json_mode: bool = True
    ) -> tuple[str, dict[str, Any]]:
        options: dict[str, Any] = {"temperature": temperature, "num_ctx": self.num_ctx}
        if self.seed is not None:
            options["seed"] = int(self.seed)
        body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                **({"format": "json"} if json_mode else {}),
                "stream": False,
                "keep_alive": self.keep_alive,
                "options": options,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.host}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = str(payload.get("message", {}).get("content") or "")
        if not content:
            raise ValueError("empty Ollama content")
        return content, payload

    def complete(
        self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True
    ) -> str:
        retries = 0
        started = time.monotonic()
        try:
            content, payload = self._chat(prompt, model, temperature, json_mode=json_mode)
        except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as first:
            retries = 1
            repair = prompt + (
                "\n\nReply with ONLY one valid JSON object."
                if json_mode
                else "\n\nReply with ONLY Python source. No JSON."
            )
            try:
                content, payload = self._chat(repair, model, temperature, json_mode=json_mode)
            except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as second:
                raise RuntimeError(f"Ollama failed for role={role} model={model}: {second}") from first
        self.last_usage = LLMUsage(
            model_id=model,
            provider="ollama",
            role=role,
            latency_s=time.monotonic() - started,
            retry_count=retries,
            digest=str(payload.get("digest") or "") or None,
            prompt_tokens=int(payload.get("prompt_eval_count") or 0) or None,
            completion_tokens=int(payload.get("eval_count") or 0) or None,
        )
        return content
