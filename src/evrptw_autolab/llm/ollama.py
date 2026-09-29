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
        self.pending_usages: list[LLMUsage] = []

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

    def _post_chat(
        self, prompt: str, model: str, temperature: float, *, json_mode: bool
    ) -> dict[str, Any]:
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
        if not isinstance(payload, dict):
            raise ValueError("Ollama response was not an object")
        return payload

    def _remember(
        self, payload: dict[str, Any], *, role: str, model: str, latency_s: float, repair: bool
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
            seed=self.seed,
            model_tag=tag,
        )
        self.pending_usages.append(usage)
        self.last_usage = usage

    def complete(
        self, *, prompt: str, role: str, temperature: float, model: str, json_mode: bool = True
    ) -> str:
        """Return model text. Every completed generation is appended to pending_usages."""
        self.pending_usages = []

        def once(text: str, *, repair: bool) -> str:
            started = time.monotonic()
            payload = self._post_chat(text, model, temperature, json_mode=json_mode)
            self._remember(
                payload, role=role, model=model, latency_s=time.monotonic() - started, repair=repair
            )
            content = str(payload.get("message", {}).get("content") or "")
            if not content:
                raise ValueError("empty Ollama content")
            return content

        try:
            return once(prompt, repair=False)
        except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as first:
            repair_prompt = prompt + (
                "\n\nReply with ONLY one valid JSON object."
                if json_mode
                else "\n\nReply with ONLY Python source. No JSON."
            )
            try:
                return once(repair_prompt, repair=True)
            except (ValueError, json.JSONDecodeError, urllib.error.URLError, TimeoutError) as second:
                raise RuntimeError(f"Ollama failed for role={role} model={model}: {second}") from first
