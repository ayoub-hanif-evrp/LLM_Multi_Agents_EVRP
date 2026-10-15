"""Bounded memory of past repair attempts for structured synthesis."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Effect = Literal["improved", "unchanged", "regressed"]

MAX_RECORDS = 20


@dataclass
class FailureRecord:
    code_hash: str
    function_changed: str
    failure_family: str
    failed_instance: str
    diagnostic: str
    attempted_repair: str
    effect: Effect


@dataclass
class FailureMemory:
    """Store up to MAX_RECORDS failure/repair outcomes."""

    records: list[FailureRecord] = field(default_factory=list)
    max_records: int = MAX_RECORDS

    def add(self, record: FailureRecord) -> None:
        self.records.append(record)
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records :]

    def relevant(self, current_error: str, k: int = 3) -> list[FailureRecord]:
        """Return up to k records most related to current_error."""
        if k <= 0 or not self.records:
            return []
        needle = (current_error or "").lower()
        tokens = {tok for tok in _tokenize(needle) if len(tok) > 2}

        def score(rec: FailureRecord) -> tuple[int, int]:
            blob = " ".join(
                [
                    rec.failure_family,
                    rec.failed_instance,
                    rec.diagnostic,
                    rec.attempted_repair,
                    rec.function_changed,
                ]
            ).lower()
            overlap = sum(1 for tok in tokens if tok in blob)
            family_hit = 1 if rec.failure_family and rec.failure_family.lower() in needle else 0
            return (overlap + 2 * family_hit, -self.records.index(rec))

        ranked = sorted(self.records, key=score, reverse=True)
        # Prefer non-zero overlap; if none, return newest k.
        if tokens and score(ranked[0])[0] == 0:
            return list(reversed(self.records[-k:]))
        return ranked[:k]

    def as_dicts(self) -> list[dict[str, Any]]:
        return [asdict(r) for r in self.records]


def _tokenize(text: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for ch in text:
        if ch.isalnum() or ch in {"_", "-"}:
            current.append(ch.lower())
        else:
            if current:
                out.append("".join(current))
                current = []
    if current:
        out.append("".join(current))
    return out
