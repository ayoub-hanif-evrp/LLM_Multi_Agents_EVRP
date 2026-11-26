"""Manifest-based partition validation for Schneider research experiments."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = ROOT / "results" / "manifests" / "split.json"
EXPOSURE_REGISTRY = ROOT / "results" / "cipher" / "research" / "exposure_registry.json"


@lru_cache(maxsize=4)
def load_split_manifest(path: str | None = None) -> dict[str, object]:
    manifest_path = Path(path) if path else DEFAULT_MANIFEST
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError("split manifest must be a JSON object")
    return payload


def _id_set(payload: dict[str, object], key: str) -> set[str]:
    raw = payload.get(key) or []
    if not isinstance(raw, list):
        raise TypeError(f"{key} must be a list")
    return {str(x) for x in raw}


def partition_of_instance_id(instance_id: str, *, manifest_path: str | None = None) -> str:
    """Return discovery|confirmation|heldout from the committed Schneider split."""
    payload = load_split_manifest(manifest_path)
    iid = str(instance_id)
    if iid in _id_set(payload, "discovery_ids"):
        return "discovery"
    if iid in _id_set(payload, "confirmation_ids"):
        return "confirmation"
    if iid in _id_set(payload, "heldout_ids"):
        return "heldout"
    raise ValueError(f"instance {iid!r} missing from Schneider split manifest")


def assert_allowed_for_development(
    instance_ids: list[str] | tuple[str, ...],
    *,
    manifest_path: str | None = None,
    allow_exposed_confirmation: bool = False,
) -> None:
    """Block confirmation/heldout unless explicitly allow-listed as historically exposed."""
    exposed = set()
    if allow_exposed_confirmation and EXPOSURE_REGISTRY.exists():
        registry = json.loads(EXPOSURE_REGISTRY.read_text(encoding="utf-8"))
        exposed = {str(item["instance_id"]) for item in registry.get("exposures") or []}
    blocked = []
    for iid in instance_ids:
        part = partition_of_instance_id(iid, manifest_path=manifest_path)
        if part == "discovery":
            continue
        if allow_exposed_confirmation and iid in exposed and part == "confirmation":
            continue
        blocked.append((iid, part))
    if blocked:
        detail = ", ".join(f"{i}={p}" for i, p in blocked)
        raise PermissionError(
            "development experiments may not use confirmation/heldout instances: " + detail
        )


def write_default_exposure_registry() -> Path:
    """Document known historical partition exposures (do not relabel as untouched)."""
    payload = {
        "contract": "cipher_exposure_registry_v1",
        "note": (
            "Instances listed here were used in development experiments despite belonging to "
            "confirmation/heldout in the Schneider manifest. They must not be treated as "
            "untouched confirmation evidence."
        ),
        "exposures": [
            {
                "instance_id": "rc105C5",
                "manifest_partition": "confirmation",
                "family": "RC1",
                "exposed_in": "baseline_ablation_b0b4.json",
                "commit": "a675888",
                "reason": "B0-B4 ablation incorrectly treated RC1 as development",
            },
            {
                "instance_id": "RC2",
                "manifest_partition": "heldout",
                "family": "RC2",
                "exposed_in": "docs/BENCHMARK_CONTRACT.md / fidelity HELDOUT_FAMILY",
                "commit": "pre-cipher",
                "reason": "RC2 is permanently heldout; document that it must never enter discovery",
            },
        ],
    }
    EXPOSURE_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    EXPOSURE_REGISTRY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return EXPOSURE_REGISTRY
