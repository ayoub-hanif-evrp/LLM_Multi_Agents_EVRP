"""OpenAI-compatible HTTP chat backend."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from evrptw_autolab.llm.usage import LLMUsage


class OpenAICompatibleBackend:
    def __init__(self, *, base_url: str, api_key_env: str = "OPENAI_API_KEY",
                 timeout_s: float = 300.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.timeout_s = timeout_s
        self.last_usage: LLMUsage | None = None

    def complete(self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True) -> str:
        key = os.environ.get(self.api_key_env, "")
        payload = {
            "model": model,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise RuntimeError(f"OpenAI-compatible backend failed role={role}: {error}") from error
        content = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        self.last_usage = LLMUsage(
            model_id=model,
            provider="openai_compatible",
            role=role,
            latency_s=time.monotonic() - started,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
        return str(content)
