"""Schneider Solomon E-VRPTW instance parser (primary dataset)."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from evocharge.data.evrptwd_parser import parse_evrptwd_solomon_text
from evocharge.domain.instance import Instance

# c101_21.txt (full, 21 stations) or c101C5.txt / rc105C5.txt (customer-count variants)
_SCHNEIDER_NAME_RE = re.compile(
    r"^(?P<family>rc|c|r)(?P<num>\d+)"
    r"(?:_(?P<nstations>\d+)|[Cc](?P<ncust>\d+))?\.txt$",
    re.IGNORECASE,
)


class SchneiderDataNotAvailableError(FileNotFoundError):
    """Raised when a Schneider instance path does not exist."""


def parse_schneider_filename_metadata(path: Path | str) -> dict[str, Any]:
    name = Path(path).name
    match = _SCHNEIDER_NAME_RE.search(name)
    if not match:
        return {"filename": name, "dataset": "Schneider_E-VRPTW"}
    family = match.group("family").upper()
    num = match.group("num")
    nstations = match.group("nstations")
    ncust = match.group("ncust")
    if ncust is not None:
        scale = f"Cus_{int(ncust)}"
        variant = "customer_subset"
    elif nstations is not None:
        scale = "Cus_100" if int(nstations) >= 21 else f"stations_{nstations}"
        variant = "full_station_set"
    else:
        scale = "unknown"
        variant = "base"
    return {
        "filename": name,
        "dataset": "Schneider_E-VRPTW",
        "file_instance_id": f"{family.lower()}{num}",
        "instance_type": family,
        "solomon_id": num,
        "n_stations_tag": int(nstations) if nstations else None,
        "n_customers_tag": int(ncust) if ncust else None,
        "scale": scale,
        "variant": variant,
        "family_key": family,
        "tw_regime": "schneider",
    }


def _decode_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_schneider_text(text: str, source_path: Path | str | None = None) -> Instance:
    """Parse Schneider Solomon-format EVRPTW text into an Instance."""
    inst = parse_evrptwd_solomon_text(
        text,
        source_path=source_path,
        dataset_name="Schneider_E-VRPTW",
    )
    file_meta = parse_schneider_filename_metadata(source_path) if source_path else {}
    meta = {**dict(inst.metadata), **file_meta}
    instance_id = str(
        file_meta.get("file_instance_id")
        or (Path(source_path).stem if source_path else inst.instance_id)
    )
    if file_meta.get("instance_type"):
        meta["instance_type"] = file_meta["instance_type"]
        meta["family_key"] = file_meta.get("family_key") or file_meta["instance_type"]
    return replace(
        inst,
        instance_id=instance_id,
        dataset_name="Schneider_E-VRPTW",
        metadata=meta,
    )


def parse_schneider_file(path: Path | str) -> Instance:
    path = Path(path)
    if not path.is_file():
        raise SchneiderDataNotAvailableError(
            f"Schneider E-VRPTW instance not found: {path}. "
            "Expected files under dataset/schneider/raw_instances/."
        )
    return parse_schneider_text(_decode_text(path), source_path=path)


def parse_instance_file(path: Path | str) -> Instance:
    """Primary instance loader (Schneider Solomon EVRPTW)."""
    return parse_schneider_file(path)
