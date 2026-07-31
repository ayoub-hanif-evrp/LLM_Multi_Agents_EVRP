"""Ollama HTTP client and pluggable LLM backends for Milestone 6."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from evocharge.agents.model_config import OllamaConfig
from evocharge.agents.schemas import LLMCallRecord, StructuredGenerationResult
from evocharge.reproducibility import hash_mapping, sha256_text


class LLMBackend(Protocol):
    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        prompt_template_hashes: list[str],
        input_artifact_hashes: list[str],
        schema_retries_so_far: int = 0,
    ) -> StructuredGenerationResult: ...

    def health(self) -> dict[str, Any]: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 - local Ollama only
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


class OllamaBackend:
    """Live Ollama backend. Does not auto-pull models or auto-fallback."""

    def __init__(self, config: OllamaConfig, *, model_override: str | None = None) -> None:
        self.config = config
        self.model = model_override or config.model

    def health(self) -> dict[str, Any]:
        base = self.config.base_url.rstrip("/")
        out: dict[str, Any] = {
            "base_url": base,
            "requested_model": self.model,
            "server_reachable": False,
            "model_installed": False,
            "version": None,
            "models": [],
            "setup_hint": f'ollama pull {self.model}',
        }
        try:
            tags = _http_json("GET", f"{base}/api/tags", timeout=10.0)
            out["server_reachable"] = True
            names = [
                m.get("name") for m in tags.get("models", []) if isinstance(m, dict)
            ]
            out["models"] = names
            # Exact match only — never silently fall back to another installed model.
            out["model_installed"] = self.model in names
        except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            out["error"] = str(exc)
            return out
        try:
            # version endpoint may not exist on all builds; keep best-effort
            ver = _http_json("GET", f"{base}/api/version", timeout=5.0)
            out["version"] = ver.get("version") or ver
        except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError):
            pass
        return out

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        prompt_template_hashes: list[str],
        input_artifact_hashes: list[str],
        schema_retries_so_far: int = 0,
    ) -> StructuredGenerationResult:
        started = _now_iso()
        t0 = datetime.now(UTC)
        call_id = str(uuid.uuid4())
        options = {
            "temperature": temperature,
            "seed": self.config.seed,
            "num_ctx": self.config.num_ctx,
        }
        payload = {
            "model": self.model,
            "stream": self.config.stream,
            "keep_alive": self.config.keep_alive,
            "format": json_schema,
            "options": options,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        request_hash = hash_mapping(payload)
        base = self.config.base_url.rstrip("/")
        raw_text = ""
        parsed: dict[str, Any] | None = None
        error_type: str | None = None
        error_message: str | None = None
        metrics: dict[str, int | float | str | None] = {}
        success = False
        schema_error: str | None = None
        try:
            resp = _http_json(
                "POST",
                f"{base}/api/chat",
                payload,
                timeout=self.config.request_timeout_seconds,
            )
            msg = resp.get("message") or {}
            raw_text = str(msg.get("content") or "")
            for key in (
                "total_duration",
                "load_duration",
                "prompt_eval_count",
                "prompt_eval_duration",
                "eval_count",
                "eval_duration",
            ):
                if key in resp:
                    metrics[key] = resp[key]
            try:
                parsed = json.loads(raw_text)
                success = True
            except json.JSONDecodeError as exc:
                error_type = "invalid_json"
                error_message = str(exc)
                schema_error = error_message
        except TimeoutError as exc:
            error_type = "timeout"
            error_message = str(exc)
        except HTTPError as exc:
            error_type = "http_error"
            error_message = f"{exc.code}: {exc.reason}"
            try:
                raw_text = exc.read().decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                raw_text = ""
        except (URLError, OSError) as exc:
            error_type = "transport_error"
            error_message = str(exc)

        duration = (datetime.now(UTC) - t0).total_seconds()
        record = LLMCallRecord(
            call_id=call_id,
            role=role,
            model=self.model,
            request_options={"options": options, "keep_alive": self.config.keep_alive},
            prompt_template_hashes=prompt_template_hashes,
            input_artifact_hashes=input_artifact_hashes,
            request_hash=request_hash,
            response_hash=sha256_text(raw_text),
            started_at=started,
            duration_seconds=duration,
            schema_retries=schema_retries_so_far,
            success=success,
            error_type=error_type,
            error_message=error_message,
            ollama_metrics=metrics,
        )
        return StructuredGenerationResult(
            raw_text=raw_text,
            parsed=parsed,
            call_record=record,
            schema_error=schema_error,
        )


class MockBackend:
    """Deterministic backend for tests — no network."""

    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[str] = []

    def health(self) -> dict[str, Any]:
        return {
            "server_reachable": True,
            "model_installed": True,
            "requested_model": "mock",
            "backend": "mock",
        }

    def set_response(self, role: str, payload: dict[str, Any]) -> None:
        self.responses[role] = payload

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        prompt_template_hashes: list[str],
        input_artifact_hashes: list[str],
        schema_retries_so_far: int = 0,
    ) -> StructuredGenerationResult:
        _ = system_prompt, user_prompt, json_schema, temperature
        self.calls.append(role)
        started = _now_iso()
        payload = self.responses.get(role)
        if payload is None:
            raw = ""
            parsed = None
            err = "missing_mock_response"
            success = False
        elif isinstance(payload.get("_raw"), str):
            raw = str(payload["_raw"])
            try:
                parsed = json.loads(raw)
                success = True
                err = None
            except json.JSONDecodeError as exc:
                parsed = None
                success = False
                err = str(exc)
        else:
            # Support sequenced responses per role
            seq = payload.get("_sequence")
            if isinstance(seq, list) and seq:
                idx = sum(1 for c in self.calls if c == role) - 1
                item = seq[min(idx, len(seq) - 1)]
                if isinstance(item, str):
                    raw = item
                    try:
                        parsed = json.loads(raw)
                        success = True
                        err = None
                    except json.JSONDecodeError as exc:
                        parsed = None
                        success = False
                        err = str(exc)
                else:
                    parsed = dict(item)
                    raw = json.dumps(parsed, sort_keys=True)
                    success = True
                    err = None
            else:
                parsed = {k: v for k, v in payload.items() if not str(k).startswith("_")}
                raw = json.dumps(parsed, sort_keys=True)
                success = True
                err = None

        record = LLMCallRecord(
            call_id=str(uuid.uuid4()),
            role=role,
            model="mock",
            request_options={"temperature": temperature},
            prompt_template_hashes=prompt_template_hashes,
            input_artifact_hashes=input_artifact_hashes,
            request_hash=hash_mapping(
                {"role": role, "system": system_prompt, "user": user_prompt}
            ),
            response_hash=sha256_text(raw),
            started_at=started,
            duration_seconds=0.0,
            schema_retries=schema_retries_so_far,
            success=success,
            error_type=None if success else "invalid_json",
            error_message=err,
            ollama_metrics={},
        )
        return StructuredGenerationResult(
            raw_text=raw,
            parsed=parsed,
            call_record=record,
            schema_error=err,
        )


class ReplayBackend:
    """Replay a stored raw_response.txt for deterministic regression."""

    def __init__(self, replay_dir: Path) -> None:
        self.replay_dir = Path(replay_dir)

    def health(self) -> dict[str, Any]:
        return {
            "server_reachable": True,
            "model_installed": True,
            "backend": "replay",
            "replay_dir": str(self.replay_dir),
        }

    def generate_structured(
        self,
        *,
        role: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        temperature: float,
        prompt_template_hashes: list[str],
        input_artifact_hashes: list[str],
        schema_retries_so_far: int = 0,
    ) -> StructuredGenerationResult:
        _ = system_prompt, user_prompt, json_schema, temperature
        path = self.replay_dir / role / "raw_response.txt"
        raw = path.read_text(encoding="utf-8") if path.is_file() else ""
        parsed: dict[str, Any] | None
        err: str | None
        try:
            parsed = json.loads(raw)
            success = True
            err = None
        except json.JSONDecodeError as exc:
            parsed = None
            success = False
            err = str(exc)
        record = LLMCallRecord(
            call_id=str(uuid.uuid4()),
            role=role,
            model="replay",
            request_options={},
            prompt_template_hashes=prompt_template_hashes,
            input_artifact_hashes=input_artifact_hashes,
            request_hash=hash_mapping({"role": role}),
            response_hash=sha256_text(raw),
            started_at=_now_iso(),
            duration_seconds=0.0,
            schema_retries=schema_retries_so_far,
            success=success,
            error_type=None if success else "invalid_json",
            error_message=err,
            ollama_metrics={},
        )
        return StructuredGenerationResult(
            raw_text=raw, parsed=parsed, call_record=record, schema_error=err
        )


def check_ollama(config: OllamaConfig, *, model: str | None = None) -> dict[str, Any]:
    """Health + optional structured smoke test. Does not start the service."""
    backend = OllamaBackend(config, model_override=model)
    report = backend.health()
    report["num_ctx"] = config.num_ctx
    report["seed"] = config.seed
    report["silent_fallback"] = False
    report["exact_model_required"] = True
    if not report.get("server_reachable"):
        report["smoke_test"] = {"ok": False, "reason": "server_unreachable"}
        return report
    if not report.get("model_installed"):
        report["smoke_test"] = {
            "ok": False,
            "reason": "model_not_installed",
            "setup_command": f"ollama pull {backend.model}",
        }
        return report
    t0 = datetime.now(UTC)
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}, "echo": {"type": "string"}},
        "required": ["ok", "echo"],
    }
    result = backend.generate_structured(
        role="smoke",
        system_prompt="Return only JSON matching the schema.",
        user_prompt='Reply with {"ok": true, "echo": "evocharge-m6"}.',
        json_schema=schema,
        temperature=0.0,
        prompt_template_hashes=[],
        input_artifact_hashes=[],
    )
    metrics = dict(result.call_record.ollama_metrics or {})
    eval_count = float(metrics.get("eval_count") or 0)
    eval_duration_ns = float(metrics.get("eval_duration") or 0)
    tokens_per_second = None
    if eval_count > 0 and eval_duration_ns > 0:
        tokens_per_second = eval_count / (eval_duration_ns / 1e9)
    # Heuristic: very low tok/s with long load may indicate heavy CPU offload / memory pressure.
    hardware_warning = None
    if tokens_per_second is not None and tokens_per_second < 1.0:
        hardware_warning = "very_low_tokens_per_second_possible_cpu_offload"
    load_duration_ns = float(metrics.get("load_duration") or 0)
    if load_duration_ns > 120e9:
        hardware_warning = hardware_warning or "long_model_load_duration"
    smoke_ok = bool(result.parsed and result.parsed.get("ok") is True)
    if result.call_record.error_type in {"timeout", "transport_error", "http_error"}:
        smoke_ok = False
    report["smoke_test"] = {
        "ok": smoke_ok,
        "duration_seconds": (datetime.now(UTC) - t0).total_seconds(),
        "response_hash": result.call_record.response_hash,
        "error": result.call_record.error_message,
        "error_type": result.call_record.error_type,
        "parsed": result.parsed,
        "num_ctx_requested": config.num_ctx,
        "ollama_metrics": metrics,
        "tokens_per_second": tokens_per_second,
        "hardware_warning": hardware_warning,
        "context_loaded": bool(metrics.get("prompt_eval_count") or metrics.get("eval_count")),
    }
    return report
