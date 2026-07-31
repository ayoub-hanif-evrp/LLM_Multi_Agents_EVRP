"""YAML configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PathsConfig(BaseModel):
    project_root: Path = Path(".")
    raw_schneider: Path = Path("dataset/schneider/raw_instances")
    contracts: Path = Path("data/contracts")
    artifacts: Path = Path("artifacts")


class AppConfig(BaseModel):
    paths: PathsConfig = Field(default_factory=PathsConfig)
    seed: int = 2027
    log_level: str = "INFO"
    extras: dict[str, Any] = Field(default_factory=dict)


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from YAML, merging over defaults."""
    if path is None:
        return AppConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(raw)


def resolve_project_root(start: Path | None = None) -> Path:
    """Walk upward until pyproject.toml with evocharge-agent is found."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "evocharge-agent" in pyproject.read_text(encoding="utf-8"):
            return candidate
    return cur
