"""Git / protocol / config provenance stamps for synthesis result JSON."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROTOCOL_FILES: tuple[str, ...] = (
    "prompts",
    "configs/experiments.yaml",
    "configs/models.yaml",
    "src/evrptw_autolab/synthesis/from_scratch.py",
    "src/evrptw_autolab/evolution/patch_apply.py",
    "src/evrptw_autolab/sandbox/limits.py",
)

CONFIG_FILES = (
    "configs/experiments.yaml",
    "configs/models.yaml",
)


def git_commit(repo_root: Path) -> str:
    """Return the current HEAD commit hash, or empty string if unavailable."""
    root = Path(repo_root)
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _hash_path(path: Path, hasher: Any) -> None:
    if path.is_file():
        hasher.update(path.as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
        return
    if not path.is_dir():
        return
    for child in sorted(path.rglob("*")):
        if child.is_file():
            rel = child.relative_to(path).as_posix()
            hasher.update(rel.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(child.read_bytes())
            hasher.update(b"\0")


def _hash_named_paths(repo_root: Path, names: tuple[str, ...]) -> str:
    root = Path(repo_root)
    hasher = hashlib.sha256()
    for name in names:
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\0")
        _hash_path(root / name, hasher)
    return hasher.hexdigest()


def protocol_hash(repo_root: Path) -> str:
    """Hash frozen protocol files (prompts, configs, synthesis/patch/limits)."""
    return _hash_named_paths(repo_root, PROTOCOL_FILES)


def config_hash(repo_root: Path) -> str:
    """Hash experiments.yaml + models.yaml."""
    return _hash_named_paths(repo_root, CONFIG_FILES)


def stamp_report(report: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """Add git_commit, protocol_hash, config_hash, and ISO-UTC timestamp."""
    out = dict(report)
    out["git_commit"] = git_commit(repo_root)
    out["protocol_hash"] = protocol_hash(repo_root)
    out["config_hash"] = config_hash(repo_root)
    out["timestamp"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def should_reuse_result(path: Path | str, repo_root: Path) -> bool:
    """True only if the result file exists and matches current git + protocol hashes."""
    target = Path(path)
    if not target.is_file():
        return False
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    if not isinstance(data, dict):
        return False
    current_commit = git_commit(repo_root)
    current_protocol = protocol_hash(repo_root)
    if not current_commit or not current_protocol:
        return False
    return (
        str(data.get("git_commit") or "") == current_commit
        and str(data.get("protocol_hash") or "") == current_protocol
    )


def refuse_stale_or_missing(path: Path | str, repo_root: Path) -> bool:
    """Inverse of should_reuse_result — runners should delete/rerun when True."""
    return not should_reuse_result(path, repo_root)
