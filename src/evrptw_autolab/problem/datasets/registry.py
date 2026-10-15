"""Filesystem registry and audit for the five EVRP benchmark families.

Milestone 2 vertical slice: enumerate, hash, classify format. Full mathematical
parsers land in subsequent milestones; unsupported parse status is explicit.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

ParseStatus = Literal["validated", "inventory_only", "unsupported", "failed"]

ROOT = Path(__file__).resolve().parents[4]
DATASET_ROOT = ROOT / "dataset"


@dataclass(frozen=True)
class DatasetSpec:
    family_id: str
    folder_name: str
    publication: str
    expected_format: str
    instance_glob: str
    notes: str = ""


DATASET_SPECS: tuple[DatasetSpec, ...] = (
    DatasetSpec(
        family_id="schneider",
        folder_name="schneider",
        publication="Schneider et al. 2014 EVRPTW",
        expected_format="solomon_txt",
        instance_glob="raw_instances/*.txt",
        notes="Legacy VoltForge Experiment A/B contract; full recharge homogeneous EV.",
    ),
    DatasetSpec(
        family_id="montoya",
        folder_name="montoya-et-al-2017",
        publication="Montoya et al. 2017 E-VRP-NL",
        expected_format="xml_nonlinear_charge",
        instance_glob="*.xml",
        notes="Piecewise-linear nonlinear charging; do not replace with constant-rate.",
    ),
    DatasetSpec(
        family_id="bezzi",
        folder_name="Bezzi & Ceselli EVRP-MRT",
        publication="Bezzi & Ceselli EVRP-MRT",
        expected_format="xml_multitech",
        instance_glob="**/*.xml",
        notes="Multiple recharging technologies; XML+PNG pairs.",
    ),
    DatasetSpec(
        family_id="goeke",
        folder_name="goeke-2018",
        publication="Goeke PDPTW-EV",
        expected_format="solomon_pd_txt",
        instance_glob="*.txt",
        notes="Pickup/delivery pairing via PartnerID; types cp/cd.",
    ),
    DatasetSpec(
        family_id="hiermann",
        folder_name="hiermann-et-al-2017-set-1",
        publication="Hiermann et al. 2016/2017 H2E-FTW set 1",
        expected_format="solomon_het_txt",
        instance_glob="*.txt",
        notes="Heterogeneous fleet attributes; per-station rechargingrate column.",
    ),
)


@dataclass
class FileRecord:
    relative_path: str
    sha256: str
    size_bytes: int
    extension: str


@dataclass
class DatasetAudit:
    family_id: str
    folder_name: str
    folder_exists: bool
    publication: str
    expected_format: str
    raw_file_count: int = 0
    instance_file_count: int = 0
    parse_status: ParseStatus = "inventory_only"
    parse_note: str = ""
    warnings: list[str] = field(default_factory=list)
    instance_files: list[FileRecord] = field(default_factory=list)
    extension_counts: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _match_instances(folder: Path, pattern: str) -> list[Path]:
    """Match instance candidates; skip obvious non-instance text files."""
    skip_names = {"readme.txt", "manifest.txt", "license.txt"}
    paths = [p for p in folder.glob(pattern) if p.is_file()]
    return sorted(
        p for p in paths if p.name.lower() not in skip_names
    )


def audit_dataset(spec: DatasetSpec, *, dataset_root: Path | None = None) -> DatasetAudit:
    root = dataset_root or DATASET_ROOT
    folder = root / spec.folder_name
    audit = DatasetAudit(
        family_id=spec.family_id,
        folder_name=spec.folder_name,
        folder_exists=folder.is_dir(),
        publication=spec.publication,
        expected_format=spec.expected_format,
    )
    if not folder.is_dir():
        audit.parse_status = "failed"
        audit.parse_note = f"missing folder: {folder}"
        return audit

    all_files = [p for p in folder.rglob("*") if p.is_file()]
    audit.raw_file_count = len(all_files)
    ext_counts: dict[str, int] = {}
    for path in all_files:
        ext = path.suffix.lower() or "(none)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    audit.extension_counts = dict(sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0])))

    instances = _match_instances(folder, spec.instance_glob)
    audit.instance_file_count = len(instances)
    # Hash only instance candidates (bounded cost); still O(n) over instance set.
    records: list[FileRecord] = []
    for path in instances:
        rel = str(path.relative_to(folder)).replace("\\", "/")
        records.append(
            FileRecord(
                relative_path=rel,
                sha256=_sha256_file(path),
                size_bytes=path.stat().st_size,
                extension=path.suffix.lower() or "(none)",
            )
        )
    audit.instance_files = records

    # Milestone-2 slice: Schneider can reuse legacy loader for a validated count.
    if spec.family_id == "schneider":
        try:
            from evrptw_autolab.problem.schneider import discover_instances, load_instance

            raw_root = folder / "raw_instances"
            # discover_instances enforces the frozen 92-instance contract.
            paths = discover_instances(raw_root)
            loaded = 0
            errors: list[str] = []
            for path in paths:
                try:
                    load_instance(path)
                    loaded += 1
                except Exception as error:  # noqa: BLE001
                    errors.append(f"{path.name}: {error}")
            audit.parse_status = "validated" if loaded == len(paths) and loaded > 0 else "failed"
            audit.parse_note = f"legacy Schneider loader: {loaded}/{len(paths)} loaded"
            if errors:
                audit.warnings.extend(errors[:10])
            extra = sorted(
                p.name for p in raw_root.glob("*.txt") if p.name.lower() != "readme.txt"
            )
            if len(extra) != len(paths):
                audit.warnings.append(
                    f"raw_instances txt count={len(extra)} vs discover contract={len(paths)}"
                )
        except Exception as error:  # noqa: BLE001
            audit.parse_status = "failed"
            audit.parse_note = f"Schneider audit error: {error}"
    else:
        audit.parse_status = "inventory_only"
        audit.parse_note = (
            "files enumerated and hashed; mathematical parser not yet implemented "
            f"for {spec.family_id} (Milestone 2 continuation)"
        )
        if audit.instance_file_count == 0:
            audit.parse_status = "failed"
            audit.parse_note = "no instance files matched glob"
            audit.warnings.append("zero instance matches")
    return audit


def audit_all(*, dataset_root: Path | None = None) -> list[DatasetAudit]:
    return [audit_dataset(spec, dataset_root=dataset_root) for spec in DATASET_SPECS]


def write_audit_manifest(
    audits: list[DatasetAudit],
    path: Path,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "protocol": "voltforge-v2-dataset-audit",
        "dataset_root": str(DATASET_ROOT),
        "families": [a.as_dict() for a in audits],
        "summary": {
            a.family_id: {
                "raw_files": a.raw_file_count,
                "instance_files": a.instance_file_count,
                "parse_status": a.parse_status,
            }
            for a in audits
        },
    }
    # Drop per-file hashes from the short console summary file variant? Keep full.
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
