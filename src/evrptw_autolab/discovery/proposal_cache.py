"""Versioned disk cache for identical discovery LLM proposal requests."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

# Bump when prompt contracts, schema, or cache payload shape change.
PROPOSAL_CACHE_VERSION = "2026-11-12.v1"
# Policy-language / feature contract digest baked into keys.
SCHEMA_DIGEST = "operator-spec+hypothesis+critique.v1"


def default_cache_dir() -> Path | None:
    """Return the configured cache directory, or None when caching is disabled."""
    raw = os.environ.get("CIPHER_PROPOSAL_CACHE")
    if raw is None:
        # Opt-in default under the repo results tree when explicitly enabled via empty path marker.
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"0", "false", "off", "none"}:
        return None
    if text.lower() in {"1", "true", "on"}:
        return Path("results") / "cipher" / "cache" / "proposals"
    return Path(text)


def cache_key(
    *,
    model: str,
    role: str,
    prompt: str,
    schema_digest: str = SCHEMA_DIGEST,
    cache_version: str = PROPOSAL_CACHE_VERSION,
) -> str:
    blob = "\n".join(
        [
            cache_version,
            schema_digest,
            str(model),
            str(role),
            hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _entry_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.json"


def lookup(cache_dir: Path | None, key: str) -> str | None:
    if cache_dir is None:
        return None
    path = _entry_path(cache_dir, key)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("cache_version") != PROPOSAL_CACHE_VERSION:
        return None
    text = payload.get("text")
    return str(text) if isinstance(text, str) else None


def store(cache_dir: Path | None, key: str, text: str, *, meta: dict[str, Any] | None = None) -> None:
    if cache_dir is None:
        return
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_version": PROPOSAL_CACHE_VERSION,
        "schema_digest": SCHEMA_DIGEST,
        "text": text,
        "meta": meta or {},
    }
    path = _entry_path(cache_dir, key)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
