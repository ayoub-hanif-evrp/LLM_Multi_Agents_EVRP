"""Manifest helpers for dataset inventories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evocharge.reproducibility import hash_mapping, sha256_file


def write_manifest(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hash_mapping(payload)
    out = {**payload, "manifest_hash": digest}
    path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return digest


def archive_checksum_record(archive_path: Path) -> dict[str, Any]:
    return {
        "path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "sha256": sha256_file(archive_path),
    }
