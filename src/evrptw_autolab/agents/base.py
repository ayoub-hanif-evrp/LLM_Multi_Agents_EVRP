"""Shared agent invocation: one role, one prompt, one schema, one model profile."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from evrptw_autolab.llm.usage import BudgetExhausted, LLMUsage, UsageLog

ROOT = Path(__file__).resolve().parents[3]
TModel = TypeVar("TModel", bound=BaseModel)


def extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("agent output must be a JSON object")
    return payload


def extract_python_source(raw: str) -> str:
    """Pull Python out of a fence, a JSON files[].content field, or a raw dump."""
    text = (raw or "").strip()
    if not text:
        return ""
    if "```" in text:
        chunks: list[str] = []
        rest = text
        while "```" in rest:
            _, rest = rest.split("```", 1)
            if "\n" not in rest:
                break
            header, rest = rest.split("\n", 1)
            if "```" not in rest:
                chunks.append(rest)
                break
            body, rest = rest.split("```", 1)
            lang = header.strip().lower()
            if lang in {"", "python", "py"}:
                chunks.append(body)
        if chunks:
            text = max(chunks, key=len).strip()
    if text.startswith("{") and '"content"' in text:
        try:
            payload = extract_json(text)
            files = payload.get("files") or []
            if files and isinstance(files[0], dict):
                inner = str(files[0].get("content") or "")
                if inner.strip():
                    return inner.strip()
        except (ValueError, json.JSONDecodeError):
            pass
    return text


def is_python_stub(content: str, marker: str) -> bool:
    if marker not in (content or ""):
        return True
    body = "\n".join(
        line for line in content.splitlines() if line.strip() and not line.strip().startswith("#")
    )
    return len(body) < 80


def coerce_schema_payload(schema_name: str, data: dict[str, Any]) -> dict[str, Any]:
    if schema_name == "HandshakeVerdict":
        if "verdict" not in data and "decision" in data:
            decision = str(data.get("decision") or "").upper()
            data["verdict"] = "PASS" if decision == "RETAIN" else "RETURN"
        data.setdefault("verdict", "RETURN")
        owner = str(data.get("owner") or data.get("next_target") or "SEARCH")
        data["owner"] = owner
        data.setdefault(
            "instruction",
            str(data.get("lesson") or data.get("primary_cause") or data.get("instruction") or ""),
        )
        data.setdefault("first_fault_family", str(data.get("first_fault_family") or ""))
        return data
    if schema_name == "CodeProposal":
        data.setdefault("proposal_id", str(data.get("id") or "P000"))
        data.setdefault("role", str(data.get("agent") or ""))
        data.setdefault("hypothesis", str(data.get("rationale") or data.get("plan") or "patch"))
        data.setdefault("change_type", "REPLACE_FILE")
        data.setdefault("files", [])
        data.setdefault("parent_solver_id", str(data.get("parent_solver_id") or ""))
        return data
    if schema_name == "CriticDecision":
        data.setdefault("decision", "REVISE")
        data.setdefault(
            "primary_cause",
            str(data.get("primary_cause") or data.get("cause") or data.get("reason") or "unspecified"),
        )
        data.setdefault("evidence", [])
        data.setdefault("credited_components", [])
        data.setdefault("blamed_components", [])
        data.setdefault(
            "next_target",
            str(data.get("next_target") or data.get("owner") or data.get("target") or "SEARCH"),
        )
        data.setdefault(
            "lesson",
            str(data.get("lesson") or data.get("primary_cause") or data.get("instruction") or "Continue repair."),
        )
        return data
    if schema_name != "ArchitectPlan":
        return data
    if not str(data.get("hypothesis") or "").strip():
        for key in (
            "answer",
            "rationale",
            "text",
            "plan",
            "lesson",
            "description",
            "message",
            "next_step",
            "summary",
            "hypothesis_text",
        ):
            if str(data.get(key) or "").strip():
                data["hypothesis"] = str(data[key])[:800]
                break
        else:
            data["hypothesis"] = "Continue from elite solver evidence."
    # Semantic fields: never invent target / activation. Missing → validation fails.
    data.setdefault("constraint_ledger", [])
    data.setdefault("evidence", [])
    data.setdefault("files_or_components", [])
    data.setdefault("success_criteria", [])
    data.setdefault("budget", {})
    return data


class Agent(Generic[TModel]):
    role: str
    prompt_name: str
    schema: type[TModel]

    def __init__(
        self,
        backend: Any,
        *,
        model: str,
        temperature: float,
        usage_log: UsageLog | None = None,
    ) -> None:
        self.backend = backend
        self.model = model
        self.temperature = temperature
        self.usage_log = usage_log
        self.prompt = (ROOT / "prompts" / self.prompt_name).read_text(encoding="utf-8")
        self.max_calls: int | None = None
        self.token_ceiling: int | None = None

    def _spent(self) -> tuple[int, int]:
        if self.usage_log is None:
            return 0, 0
        rows = self.usage_log.all()
        tokens = 0
        for row in rows:
            tokens += int(row.get("prompt_tokens") or 0) + int(row.get("completion_tokens") or 0)
        return len(rows), tokens

    def _complete(self, prompt: str, *, json_mode: bool = True) -> str:
        calls, tokens = self._spent()
        if self.max_calls is not None and calls >= self.max_calls:
            raise BudgetExhausted("call ceiling")
        if self.token_ceiling is not None and tokens >= self.token_ceiling:
            raise BudgetExhausted("token ceiling")
        raw = self.backend.complete(
            prompt=prompt,
            role=self.role,
            temperature=self.temperature,
            model=self.model,
            json_mode=json_mode,
        )
        pending = getattr(self.backend, "pending_usages", None)
        if pending is None:
            recorded = [
                LLMUsage(
                    model_id=self.model,
                    provider=type(self.backend).__name__,
                    role=self.role,
                    latency_s=0.0,
                    model_tag=self.model,
                )
            ]
        else:
            recorded = list(pending)
            self.backend.pending_usages = []
        if self.usage_log is not None:
            for usage in recorded:
                usage.role = self.role
                if not usage.model_tag:
                    usage.model_tag = self.model
                self.usage_log.record(usage)
        return raw if isinstance(raw, str) else json.dumps(raw)

    def run(self, payload: dict[str, Any]) -> TModel:
        prompt = self.prompt + "\n\nINPUT:\n" + json.dumps(payload, default=str)
        raw = self._complete(prompt)
        try:
            data = coerce_schema_payload(self.schema.__name__, extract_json(raw))
            parsed = self.schema.model_validate(data)
        except (ValidationError, ValueError, json.JSONDecodeError) as first:
            repair = (
                "\n\nINVALID_ARCHITECT_PLAN. Reply with ONLY one valid JSON object. "
                "target must be exactly one of BOOTSTRAP, ROUTING, CHARGING, SEARCH, "
                "ARCHITECTURE, TEST_ONLY. Do not use fault families as target."
                if self.schema.__name__ == "ArchitectPlan"
                else "\n\nReply with ONLY one valid JSON object matching the schema."
            )
            raw = self._complete(prompt + repair)
            try:
                data = coerce_schema_payload(self.schema.__name__, extract_json(raw))
                parsed = self.schema.model_validate(data)
            except (ValidationError, ValueError, json.JSONDecodeError) as second:
                raise ValueError(f"{self.role} output invalid: {second}") from first
        return parsed

    def write_python(self, payload: dict[str, Any], *, filename: str, marker: str) -> str:
        """Ask for raw Python (not JSON). Used when a crash needs a surgical file rewrite."""
        instruction = str(payload.get("instruction") or "")
        body = {key: value for key, value in payload.items() if key != "instruction"}
        prompt = (
            self.prompt
            + "\n\nINPUT:\n"
            + json.dumps(body, default=str)
            + ("\n\n" + instruction if instruction else "")
            + f"\n\nReply with ONLY Python source for {filename}. It must contain `{marker.strip()}`. No JSON object."
        )
        raw = self._complete(prompt, json_mode=False)
        self.last_raw = raw if isinstance(raw, str) else str(raw)
        source = extract_python_source(raw)
        self.last_extracted = source
        return source
