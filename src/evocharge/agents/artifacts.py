"""Immutable agent-run artifact storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evocharge.reproducibility import hash_mapping, sha256_file, sha256_text


def write_json(path: Path, payload: dict[str, Any] | list[Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return sha256_text(text)


def write_text(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return sha256_text(text)


class AgentRunStore:
    def __init__(self, root: Path, run_id: str) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self.run_dir = self.root / run_id
        if self.run_dir.exists():
            raise FileExistsError(
                f"Agent run already exists (no overwrite): {self.run_dir}"
            )
        self.run_dir.mkdir(parents=True, exist_ok=False)
        (self.run_dir / "input").mkdir()
        (self.run_dir / "analyst").mkdir()
        (self.run_dir / "scientist").mkdir()
        self.transitions: list[dict[str, Any]] = []

    def record_transition(self, state: str, detail: dict[str, Any] | None = None) -> None:
        from datetime import UTC, datetime

        entry = {
            "state": state,
            "at": datetime.now(UTC).isoformat(),
            "detail": detail or {},
        }
        self.transitions.append(entry)
        write_json(self.run_dir / "transitions.json", self.transitions)

    def write_input(self, name: str, payload: dict[str, Any]) -> str:
        return write_json(self.run_dir / "input" / name, payload)

    def write_role_json(self, role: str, name: str, payload: dict[str, Any]) -> str:
        return write_json(self.run_dir / role / name, payload)

    def write_role_text(self, role: str, name: str, text: str) -> str:
        return write_text(self.run_dir / role / name, text)

    def write_summary(self, payload: dict[str, Any]) -> str:
        payload = {
            **payload,
            "artifact_hashes": self.hash_tree(),
        }
        return write_json(self.run_dir / "summary.json", payload)

    def hash_tree(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in sorted(self.run_dir.rglob("*")):
            if path.is_file() and path.name != "summary.json":
                rel = path.relative_to(self.run_dir).as_posix()
                out[rel] = sha256_file(path)
        out["tree_hash"] = hash_mapping(out)
        return out
