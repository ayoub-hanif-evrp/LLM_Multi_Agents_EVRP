"""Usage records and centralized budget collection for every LLM call."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


class BudgetExhausted(RuntimeError):
    """Raised when a run has reached its call, token, or wall-clock ceiling."""


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
    seed: int | None = None
    base_seed: int | None = None
    call_index: int | None = None
    repair: bool = False
    model_tag: str | None = None
    reasoning_effort: str | None = None
    thinking_chars: int = 0
    content_empty: bool = False
    ollama_version: str | None = None
    num_ctx: int | None = None
    candidate_id: str | None = None
    generation: int | None = None
    http_attempt: int = 1
    failed: bool = False

    @property
    def total_tokens(self) -> int:
        return int(self.prompt_tokens or 0) + int(self.completion_tokens or 0)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_tokens"] = self.total_tokens
        return data


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


@dataclass
class UsageCollector:
    """Central budget + provenance tracker for logical agent calls and HTTP attempts."""

    max_calls: int | None = None
    max_tokens: int | None = None
    max_wall_s: float | None = None
    records: list[LLMUsage] = field(default_factory=list)
    logical_calls: int = 0
    http_attempts: int = 0
    total_tokens: int = 0
    wall_s: float = 0.0
    started_monotonic: float = field(default_factory=time.monotonic)
    overshoot_tokens: int = 0
    stopped: bool = False
    stop_reason: str = ""

    def restore(self, *, logical_calls: int = 0, total_tokens: int = 0, wall_s: float = 0.0) -> None:
        """Resume prior budget consumption from a checkpoint (do not reset to zero)."""
        self.logical_calls = int(logical_calls)
        self.total_tokens = int(total_tokens)
        self.wall_s = float(wall_s)
        self.started_monotonic = time.monotonic() - self.wall_s

    def check_budget(self) -> None:
        if self.stopped:
            raise BudgetExhausted(self.stop_reason or "budget already exhausted")
        elapsed = time.monotonic() - self.started_monotonic
        self.wall_s = elapsed
        if self.max_calls is not None and self.logical_calls >= self.max_calls:
            self.stopped = True
            self.stop_reason = f"max_calls={self.max_calls}"
            raise BudgetExhausted(self.stop_reason)
        if self.max_tokens is not None and self.total_tokens >= self.max_tokens:
            self.stopped = True
            self.stop_reason = f"max_tokens={self.max_tokens} used={self.total_tokens}"
            raise BudgetExhausted(self.stop_reason)
        if self.max_wall_s is not None and elapsed >= self.max_wall_s:
            self.stopped = True
            self.stop_reason = f"max_wall_s={self.max_wall_s}"
            raise BudgetExhausted(self.stop_reason)

    def _ingest(self, usage: LLMUsage) -> None:
        self.records.append(usage)
        self.http_attempts += 1
        self.total_tokens += usage.total_tokens
        self.wall_s = time.monotonic() - self.started_monotonic
        if self.max_tokens is not None and self.total_tokens > self.max_tokens:
            self.overshoot_tokens = self.total_tokens - self.max_tokens
            self.stopped = True
            self.stop_reason = (
                f"token_budget_overshoot used={self.total_tokens} max={self.max_tokens} "
                f"overshoot={self.overshoot_tokens}"
            )

    def complete(
        self,
        backend: Any,
        *,
        prompt: str,
        role: str,
        temperature: float,
        model: str,
        json_mode: bool = True,
        candidate_id: str | None = None,
        generation: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Run one logical agent call; record every underlying HTTP generation/retry."""
        self.check_budget()
        # Clear backend pending list if present so we only see this call's attempts.
        if hasattr(backend, "pending_usages"):
            backend.pending_usages = []
        error: Exception | None = None
        text = ""
        try:
            text = backend.complete(
                prompt=prompt,
                role=role,
                temperature=temperature,
                model=model,
                json_mode=json_mode,
                **kwargs,
            )
        except Exception as exc:  # noqa: BLE001 — must keep usage already incurred
            error = exc

        pending = list(getattr(backend, "pending_usages", None) or [])
        if pending:
            for idx, usage in enumerate(pending, start=1):
                usage.candidate_id = candidate_id
                usage.generation = generation
                usage.http_attempt = idx
                if error is not None and idx == len(pending):
                    usage.failed = True
                self._ingest(usage)
        else:
            # Backends without pending_usages: synthesize from last_usage / last_tokens.
            last = getattr(backend, "last_usage", None)
            if last is not None:
                last.candidate_id = candidate_id
                last.generation = generation
                last.failed = error is not None
                self._ingest(last)
            else:
                tokens = int(getattr(backend, "last_tokens", 0) or 0)
                synthetic = LLMUsage(
                    model_id=model,
                    provider=str(getattr(backend, "provider", "unknown")),
                    role=role,
                    latency_s=0.0,
                    prompt_tokens=0,
                    completion_tokens=tokens,
                    candidate_id=candidate_id,
                    generation=generation,
                    failed=error is not None,
                )
                self._ingest(synthetic)

        self.logical_calls += 1
        if error is not None:
            raise error
        # Overshoot on this call is recorded; future calls are blocked in check_budget().
        return text

    def as_dict(self) -> dict[str, Any]:
        return {
            "logical_calls": self.logical_calls,
            "http_attempts": self.http_attempts,
            "total_tokens": self.total_tokens,
            "wall_s": self.wall_s,
            "overshoot_tokens": self.overshoot_tokens,
            "stopped": self.stopped,
            "stop_reason": self.stop_reason,
            "max_calls": self.max_calls,
            "max_tokens": self.max_tokens,
            "max_wall_s": self.max_wall_s,
            "records": [r.as_dict() for r in self.records],
        }
