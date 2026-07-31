"""Prompt template loading and hashing."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from evocharge.reproducibility import sha256_text


def prompts_root() -> Path:
    # Prefer package directory next to this module's package parent
    pkg = Path(__file__).resolve().parents[1] / "prompts"
    if pkg.is_dir():
        return pkg
    return Path("src/evocharge/prompts")


def load_prompt(name: str) -> str:
    path = prompts_root() / name
    if path.is_file():
        return path.read_text(encoding="utf-8")
    # Fallback via importlib for installed wheels
    try:
        ref = resources.files("evocharge.prompts").joinpath(name)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError) as exc:
        raise FileNotFoundError(f"Prompt template not found: {name}") from exc


def prompt_hash(name: str) -> str:
    return sha256_text(load_prompt(name))


def render_task(template: str, **kwargs: object) -> str:
    text = template
    for key, value in kwargs.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text
