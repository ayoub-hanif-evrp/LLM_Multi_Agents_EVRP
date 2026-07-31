"""Development instance registry (Schneider Solomon E-VRPTW)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def development_instance_paths(project_root: Path | None = None) -> list[Path]:
    """Collect up to 18 Schneider instances (prefer small Cus5)."""
    root = project_root or resolve_project_root()
    base = root / "dataset" / "schneider" / "raw_instances"
    paths: list[Path] = []
    if base.is_dir():
        for path in sorted(base.glob("*C5.txt")) + sorted(base.glob("*C10.txt")) + sorted(
            base.glob("*_21.txt")
        ):
            paths.append(path)
    return paths[:18]


def regression_cus100_paths(project_root: Path | None = None) -> list[Path]:
    root = project_root or resolve_project_root()
    from evocharge.candidates.integration import ANCHORED_RELATIVE

    base = root / "dataset" / "schneider" / "raw_instances"
    return [base / name for name in ANCHORED_RELATIVE if (base / name).is_file()]


def label_instance_path(path: Path) -> dict[str, Any]:
    name = path.name
    family = (
        "RC"
        if name.lower().startswith("rc")
        else ("R" if name.lower().startswith("r") else ("C" if name.lower().startswith("c") else "?"))
    )
    if "C5" in name:
        size = "Cus_5"
    elif "C10" in name:
        size = "Cus_10"
    elif "C15" in name:
        size = "Cus_15"
    elif "_21" in name:
        size = "Cus_100"
    else:
        size = "unknown"
    return {
        "path": str(path),
        "name": name,
        "size": size,
        "family": family,
        "horizon": "schneider",
        "set_label": "schneider_smoke" if size == "Cus_5" else "development",
        "not_benchmark_claim": True,
    }


def development_manifest(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or resolve_project_root()
    dev = [label_instance_path(p) for p in development_instance_paths(root)]
    reg = [label_instance_path(p) for p in regression_cus100_paths(root)]
    return {
        "n_development": len(dev),
        "n_regression_smoke": len(reg),
        "development": dev,
        "regression_smoke": reg,
        "note": "Schneider Solomon instances under dataset/schneider/raw_instances.",
        "not_benchmark_claim": True,
    }
