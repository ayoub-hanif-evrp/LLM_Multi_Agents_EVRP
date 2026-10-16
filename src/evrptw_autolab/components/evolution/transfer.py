"""Capability-aware cross-variant component transfer experiments."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evrptw_autolab.components.evolution.archive import BundleCandidate, source_hash
from evrptw_autolab.components.evolution.fitness import PanelEvaluation, panel_is_better
from evrptw_autolab.components.interfaces import (
    DEFAULT_SOURCES,
    REQUIRED_CAPS,
    ComponentKind,
    signature_for,
)
from evrptw_autolab.problem.v2.types import ProblemSpecV2


@dataclass(frozen=True, slots=True)
class TransferRecord:
    kind: str
    source_family: str
    target_family: str
    compatible: bool
    source_candidate_id: str
    before_instances_feasible: int
    after_instances_feasible: int
    improved: bool
    worsened: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source_family": self.source_family,
            "target_family": self.target_family,
            "compatible": self.compatible,
            "source_candidate_id": self.source_candidate_id,
            "before_instances_feasible": self.before_instances_feasible,
            "after_instances_feasible": self.after_instances_feasible,
            "improved": self.improved,
            "worsened": self.worsened,
            "negative_transfer": self.worsened and not self.improved,
            "positive_transfer": self.improved and not self.worsened,
            "note": self.note,
        }


def component_compatible(kind: ComponentKind | str, target_spec: ProblemSpecV2) -> bool:
    """True if the component's required capabilities hold on the target variant."""
    if kind not in REQUIRED_CAPS:
        return False
    return signature_for(kind).compatible_with(target_spec.capabilities)  # type: ignore[arg-type]


def retrieve_transferable_components(
    archive: list[BundleCandidate],
    *,
    target_families: set[str],
    target_specs: list[ProblemSpecV2],
) -> list[tuple[BundleCandidate, str, str]]:
    """Return (donor, kind, source_family) for LLM components from other families."""
    out: list[tuple[BundleCandidate, str, str]] = []
    for donor in archive:
        source_families = set(donor.metadata.get("source_families") or [])
        if not source_families:
            # Infer from panel rows if present.
            for row in (donor.panel or {}).get("per_instance") or []:
                source_families.add(str(row.get("family") or ""))
        if source_families & target_families and not (source_families - target_families):
            # Donor only saw the target families — not a cross-variant donor.
            continue
        foreign = source_families - target_families
        if not foreign:
            continue
        for kind, meta in (donor.lineage or {}).items():
            if not meta.get("llm_generated"):
                continue
            # Compatible with at least one target spec.
            if any(component_compatible(kind, spec) for spec in target_specs):
                out.append((donor, str(kind), sorted(foreign)[0]))
    return out


def apply_transfer(
    base_sources: dict[str, str],
    donor: BundleCandidate,
    kind: str,
) -> dict[str, str]:
    """Copy one component source from donor into a base bundle."""
    child = dict(base_sources)
    code = donor.sources.get(kind)
    if code:
        child[kind] = code
    return child


def evaluate_transfer_effect(
    *,
    kind: str,
    source_family: str,
    target_family: str,
    donor: BundleCandidate,
    before: PanelEvaluation,
    after: PanelEvaluation,
    compatible: bool,
) -> TransferRecord:
    improved = panel_is_better(after, before)
    worsened = panel_is_better(before, after)
    return TransferRecord(
        kind=kind,
        source_family=source_family,
        target_family=target_family,
        compatible=compatible,
        source_candidate_id=donor.candidate_id,
        before_instances_feasible=before.instances_feasible,
        after_instances_feasible=after.instances_feasible,
        improved=improved,
        worsened=worsened,
        note=(
            "incompatible_skipped"
            if not compatible
            else ("positive" if improved and not worsened else ("negative" if worsened else "neutral"))
        ),
    )


def write_transfer_report(path: Path, records: list[TransferRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n": len(records),
        "positive": sum(1 for r in records if r.improved and not r.worsened),
        "negative": sum(1 for r in records if r.worsened and not r.improved),
        "neutral": sum(1 for r in records if not r.improved and not r.worsened),
        "incompatible": sum(1 for r in records if not r.compatible),
        "records": [r.as_dict() for r in records],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def default_bundle_sources() -> dict[str, str]:
    return {k: DEFAULT_SOURCES[k] for k in DEFAULT_SOURCES}


def transfer_fingerprint(sources: dict[str, str]) -> str:
    return source_hash(json.dumps(sources, sort_keys=True))
