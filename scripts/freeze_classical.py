"""Remeasure the development panel with the current classical solver.

Writes a new run directory. Does not replace the historical 27278a1 artifacts.
"""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.baselines.classical_pilot import run_classical_pilot

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    out = ROOT / "results" / "v2" / "baselines" / "classical_frozen_c2de5a0"
    result = run_classical_pilot(seeds=[7, 11, 22], out_dir=out, root=ROOT)
    print({"n": result["n"], "seeds": result["seeds"], "paths": result["paths"]}, flush=True)


if __name__ == "__main__":
    main()
