"""Freeze improved solvers without overwriting published paper solvers."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
EVOLUTION_ROOT = REPO_ROOT / "results" / "paper" / "evolution" / "candidates"
IMMUTABLE_DIR = REPO_ROOT / "results" / "paper" / "solvers"


def assert_not_immutable(dest: Path) -> None:
    resolved = dest.resolve()
    frozen = IMMUTABLE_DIR.resolve()
    if resolved == frozen or frozen in resolved.parents:
        raise RuntimeError(f"refusing to overwrite published solvers: {dest}")


def freeze_dir_for(
    *,
    source_hash: str,
    seed_base: int | None = None,
    campaign_id: str = "",
    continuation: bool = False,
) -> Path:
    """Unique directory under results/paper/evolution/candidates."""
    if seed_base is not None:
        name = f"seed{seed_base}_{source_hash}"
    elif campaign_id:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in campaign_id)
        name = f"{safe}_{source_hash}"
    else:
        name = f"improved_{source_hash}"
    if continuation:
        name = f"continued_{name}"
    dest = EVOLUTION_ROOT / name
    assert_not_immutable(dest)
    return dest
