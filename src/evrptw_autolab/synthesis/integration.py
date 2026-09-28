"""Apply specialist proposals into one solver directory. No hidden construction or charging logic."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.agents.schemas import CodeProposal
from evrptw_autolab.synthesis.patching import apply_proposal


def integrate_proposals(solver_dir: Path, proposals: list[CodeProposal]) -> list[Path]:
    written: list[Path] = []
    for proposal in proposals:
        written.extend(apply_proposal(solver_dir, proposal))
    return written
