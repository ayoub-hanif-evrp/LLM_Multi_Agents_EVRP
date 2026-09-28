"""Structured outputs for the five fixed logical roles."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

FIXED_ROLES = ("architect", "routing", "charging", "search", "critic")

_CHANGE = ("CREATE", "REPLACE_FILE", "PATCH", "DELETE_FILE", "ARCHITECTURE")
_TARGET = ("BOOTSTRAP", "ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE", "TEST_ONLY")
_DECISION = ("RETAIN", "REVISE", "REVERT", "ABANDON")
_NEXT = ("ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE", "NONE")
_VERDICT = ("PASS", "RETURN")
_FAULT = ("VISIT", "DEPOT", "CAPACITY", "WINDOW", "BATTERY", "CHARGE_POLICY", "CRASH", "PARSE", "OK", "")


def _first_enum(value: Any, options: tuple[str, ...], *, aliases: dict[str, str] | None = None) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    upper = text.upper().replace(" ", "")
    table = {opt: opt for opt in options}
    if aliases:
        table.update({key.upper(): val for key, val in aliases.items()})
    if upper in table:
        return table[upper]
    for opt in options:
        if opt in upper or opt in text.upper():
            return opt
    return value


def _as_str_list(value: Any) -> Any:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.replace("|", ",").split(",") if part.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if isinstance(item, str):
                if item.strip():
                    out.append(item.strip())
            elif isinstance(item, dict):
                out.append(str(item)[:400])
            elif item is not None:
                out.append(str(item)[:400])
        return out
    return value


def _as_str(value: Any) -> Any:
    return "" if value is None else value


class ArchitectPlan(BaseModel):
    hypothesis: str
    target: Literal["BOOTSTRAP", "ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE", "TEST_ONLY"]
    evidence: list[str] = Field(default_factory=list)
    agents_to_activate: list[str] = Field(default_factory=list)
    files_or_components: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    constraint_ledger: list[str] = Field(default_factory=list)
    budget: dict[str, object] = Field(default_factory=dict)

    @field_validator("target", mode="before")
    @classmethod
    def _target(cls, value: Any) -> Any:
        return _first_enum(
            value,
            _TARGET,
            aliases={
                "HYBRID": "SEARCH",
                "GA": "SEARCH",
                "ALNS": "SEARCH",
                "VNS": "SEARCH",
                "TABU": "SEARCH",
                # Fault-family labels sometimes emitted as target — map to owning role.
                "CHARGE_POLICY": "CHARGING",
                "BATTERY": "CHARGING",
                "WINDOW": "CHARGING",
                "VISIT": "ROUTING",
                "DEPOT": "ROUTING",
                "CAPACITY": "ROUTING",
                "CRASH": "SEARCH",
                "PARSE": "SEARCH",
            },
        )

    @field_validator("evidence", "agents_to_activate", "files_or_components", "success_criteria", "constraint_ledger", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> Any:
        return _as_str_list(value)

    @field_validator("budget", mode="before")
    @classmethod
    def _budget(cls, value: Any) -> Any:
        return value if isinstance(value, dict) else {}


class CodeFile(BaseModel):
    path: str
    operation: Literal["replace", "create", "delete"] = "replace"
    content: str = ""

    @field_validator("operation", mode="before")
    @classmethod
    def _op(cls, value: Any) -> Any:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if "delete" in lowered:
                return "delete"
            if "create" in lowered:
                return "create"
            if "replace" in lowered or "patch" in lowered or "modify" in lowered or "update" in lowered:
                return "replace"
        return value

    @field_validator("content", "path", mode="before")
    @classmethod
    def _content(cls, value: Any) -> Any:
        return "" if value is None else value


class CodeProposal(BaseModel):
    proposal_id: str = ""
    role: str = ""
    parent_solver_id: str = ""
    hypothesis: str = ""
    change_type: Literal["CREATE", "REPLACE_FILE", "PATCH", "DELETE_FILE", "ARCHITECTURE"] = "REPLACE_FILE"
    files: list[CodeFile] = Field(default_factory=list)
    expected_effect: dict[str, str] = Field(default_factory=dict)
    requested_tests: list[str] = Field(default_factory=list)

    @field_validator("parent_solver_id", "proposal_id", "role", "hypothesis", mode="before")
    @classmethod
    def _strings(cls, value: Any) -> Any:
        return _as_str(value)

    @field_validator("change_type", mode="before")
    @classmethod
    def _change(cls, value: Any) -> Any:
        return _first_enum(
            value,
            _CHANGE,
            aliases={"CREATE_FILE": "CREATE", "REPLACE": "REPLACE_FILE", "DELETE": "DELETE_FILE"},
        )

    @field_validator("requested_tests", mode="before")
    @classmethod
    def _tests(cls, value: Any) -> Any:
        return _as_str_list(value)

    @field_validator("expected_effect", mode="before")
    @classmethod
    def _effect(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return {}
        return {str(key): str(val) for key, val in value.items()}

    @field_validator("files", mode="before")
    @classmethod
    def _files(cls, value: Any) -> Any:
        return value if isinstance(value, list) else []


class CriticDecision(BaseModel):
    decision: Literal["RETAIN", "REVISE", "REVERT", "ABANDON"]
    primary_cause: str
    evidence: list[str]
    credited_components: list[str] = Field(default_factory=list)
    blamed_components: list[str] = Field(default_factory=list)
    next_target: Literal["ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE", "NONE"]
    lesson: str

    @field_validator("decision", mode="before")
    @classmethod
    def _decision(cls, value: Any) -> Any:
        return _first_enum(value, _DECISION)

    @field_validator("next_target", mode="before")
    @classmethod
    def _next(cls, value: Any) -> Any:
        return _first_enum(value, _NEXT)

    @field_validator("evidence", "credited_components", "blamed_components", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> Any:
        return _as_str_list(value)

    @field_validator("primary_cause", "lesson", mode="before")
    @classmethod
    def _text(cls, value: Any) -> Any:
        return _as_str(value)


class HandshakeVerdict(BaseModel):
    """Between-role interface gate. Distinct from the post-run RETAIN/REVERT critic."""

    verdict: Literal["PASS", "RETURN"]
    owner: Literal["ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE"] = "SEARCH"
    first_fault_family: str = ""
    instruction: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _verdict(cls, value: Any) -> Any:
        return _first_enum(value, _VERDICT)

    @field_validator("owner", mode="before")
    @classmethod
    def _owner(cls, value: Any) -> Any:
        mapped = _first_enum(value, _NEXT)
        if mapped == "NONE" or mapped not in {"ROUTING", "CHARGING", "SEARCH", "ARCHITECTURE"}:
            return "SEARCH"
        return mapped

    @field_validator("first_fault_family", "instruction", mode="before")
    @classmethod
    def _text_fields(cls, value: Any) -> Any:
        return _as_str(value)
