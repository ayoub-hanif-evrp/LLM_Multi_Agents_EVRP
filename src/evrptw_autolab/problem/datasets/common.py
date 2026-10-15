"""Shared helpers for dataset parsers."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_child(parent: Any, tag: str, default: str | None = None) -> str | None:
    node = parent.find(tag)
    if node is None or node.text is None:
        return default
    return str(node.text).strip()


def float_child(parent: Any, tag: str) -> float:
    raw = text_child(parent, tag)
    if raw is None:
        raise ValueError(f"missing required XML child <{tag}>")
    return float(raw)


def require_unique_ids(ids: list[str], *, label: str) -> None:
    if len(ids) != len(set(ids)):
        seen: set[str] = set()
        dupes: list[str] = []
        for item in ids:
            if item in seen:
                dupes.append(item)
            seen.add(item)
        raise ValueError(f"duplicate {label} ids: {sorted(set(dupes))}")
