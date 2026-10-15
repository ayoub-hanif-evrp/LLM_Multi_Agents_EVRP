"""Filesystem registry and audit for the five EVRP benchmark families."""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from evrptw_autolab.problem.v2.types import ProblemSpecV2

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
        instance_glob="**/Instances/*.xml",
        notes="Multiple recharging technologies; Solutions/ excluded from instance audit.",
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
        notes="Heterogeneous ICEV/PHEV/BEV fleet; never collapse to homogeneous EV.",
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
    loaded_count: int = 0
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
    return sorted(p for p in paths if p.name.lower() not in skip_names)


def _loader_for(family_id: str) -> Callable[[Path], ProblemSpecV2] | None:
    if family_id == "schneider":
        from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2

        return load_schneider_v2
    if family_id == "montoya":
        from evrptw_autolab.problem.datasets.montoya import load_montoya

        return load_montoya
    if family_id == "bezzi":
        from evrptw_autolab.problem.datasets.bezzi import load_bezzi

        return load_bezzi
    if family_id == "goeke":
        from evrptw_autolab.problem.datasets.goeke import load_goeke

        return load_goeke
    if family_id == "hiermann":
        from evrptw_autolab.problem.datasets.hiermann import load_hiermann

        return load_hiermann
    return None


def _validate_with_loader(
    audit: DatasetAudit,
    paths: list[Path],
    loader: Callable[[Path], ProblemSpecV2],
    *,
    expected_family: str,
) -> None:
    loaded = 0
    errors: list[str] = []
    for path in paths:
        try:
            spec = loader(path)
            if spec.family != expected_family:
                raise ValueError(f"family mismatch {spec.family!r}")
            if not spec.nodes or not spec.depot_ids:
                raise ValueError("empty nodes/depots")
            loaded += 1
        except Exception as error:  # noqa: BLE001
            errors.append(f"{path.name}: {error}")
    audit.loaded_count = loaded
    audit.parse_status = "validated" if loaded == len(paths) and loaded > 0 else "failed"
    audit.parse_note = f"parser loaded {loaded}/{len(paths)} instances as ProblemSpecV2"
    if errors:
        audit.warnings.extend(errors[:15])


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
    # Schneider: enforce frozen 92-instance discover contract for validation set.
    if spec.family_id == "schneider":
        from evrptw_autolab.problem.schneider import discover_instances

        try:
            instances = list(discover_instances(folder / "raw_instances"))
        except Exception as error:  # noqa: BLE001
            audit.parse_status = "failed"
            audit.parse_note = f"Schneider discover failed: {error}"
            return audit

    audit.instance_file_count = len(instances)
    records: list[FileRecord] = []
    for path in instances:
        try:
            rel = str(path.relative_to(folder)).replace("\\", "/")
        except ValueError:
            rel = path.name
        records.append(
            FileRecord(
                relative_path=rel,
                sha256=_sha256_file(path),
                size_bytes=path.stat().st_size,
                extension=path.suffix.lower() or "(none)",
            )
        )
    audit.instance_files = records

    if audit.instance_file_count == 0:
        audit.parse_status = "failed"
        audit.parse_note = "no instance files matched glob"
        audit.warnings.append("zero instance matches")
        return audit

    loader = _loader_for(spec.family_id)
    if loader is None:
        audit.parse_status = "unsupported"
        audit.parse_note = f"no parser registered for {spec.family_id}"
        return audit

    try:
        _validate_with_loader(audit, instances, loader, expected_family=spec.family_id)
    except Exception as error:  # noqa: BLE001
        audit.parse_status = "failed"
        audit.parse_note = f"audit error: {error}"
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
                "loaded": a.loaded_count,
                "parse_status": a.parse_status,
            }
            for a in audits
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
