"""SHA256 of the frozen 92 Schneider instance files. Not a solver."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evrptw_autolab.problem.schneider import SCHNEIDER_ROOT, discover_instances

ROOT = Path(__file__).resolve().parents[3]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def instance_hashes(data_root: Path | None = None) -> dict[str, str]:
    root = Path(data_root) if data_root else ROOT / SCHNEIDER_ROOT
    return {path.stem: file_sha256(path) for path in discover_instances(root)}


def write_instance_hashes(path: Path, data_root: Path | None = None) -> Path:
    payload = {
        "contract": "schneider_92_full_recharge",
        "n": 92,
        "sha256": instance_hashes(data_root),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
