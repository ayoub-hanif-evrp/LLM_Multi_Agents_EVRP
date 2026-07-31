"""Hashing and reproducibility helpers."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_mapping(payload: dict[str, Any]) -> str:
    return sha256_text(canonical_json(payload))


def git_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None
    return None


def git_available(project_root: Path) -> bool:
    return (Path(project_root) / ".git").exists()


def git_dirty(project_root: Path) -> bool | None:
    if not git_available(project_root):
        return None
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if result.returncode != 0:
            return None
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def git_diff_hash(project_root: Path) -> str | None:
    if not git_available(project_root):
        return None
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=project_root,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        return sha256_bytes(result.stdout or b"")
    except (OSError, subprocess.SubprocessError):
        return None


def source_tree_hash(
    project_root: Path,
    *,
    roots: tuple[str, ...] = ("src", "configs", "data/contracts"),
) -> str:
    """Content hash of tracked source tree paths (works without Git)."""
    project_root = Path(project_root)
    digest = hashlib.sha256()
    files: list[Path] = []
    for root_name in roots:
        root = project_root / root_name
        if not root.exists():
            continue
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(
                part in {".venv", "__pycache__", ".mypy_cache", ".ruff_cache"}
                for part in path.parts
            ):
                continue
            files.append(path)
    for path in sorted(files, key=lambda p: p.relative_to(project_root).as_posix()):
        rel = path.relative_to(project_root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def source_state(project_root: Path) -> Any:
    from evocharge.agents.schemas import SourceState

    project_root = Path(project_root)
    available = git_available(project_root)
    return SourceState(
        git_available=available,
        commit=git_commit(project_root) if available else None,
        dirty=git_dirty(project_root) if available else None,
        diff_hash=git_diff_hash(project_root) if available else None,
        source_tree_hash=source_tree_hash(project_root),
    )


def lockfile_hash(project_root: Path) -> str | None:
    lock = project_root / "uv.lock"
    if lock.is_file():
        return sha256_file(lock)
    return None
