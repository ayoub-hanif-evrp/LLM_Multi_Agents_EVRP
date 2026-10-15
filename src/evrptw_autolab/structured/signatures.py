"""Documented stubs and assembler for structured EVRPTW solvers.

The framework defines ONLY these signatures. Algorithm bodies are written by the LLM.
A finished solver.py must run with zero LLM calls.
"""
from __future__ import annotations

from typing import Any

DEFAULT_IMPORTS = """\
import random
from evrptw_autolab.problem.physics import (
    distance,
    travel_time,
    energy_required,
    full_recharge,
    propagate_route,
)
from evrptw_autolab.problem.types import CandidateSolution
"""

CONSTRUCT_STUB = '''\
def construct(instance, rng):
    """Build an initial set of routes.

    Args:
        instance: EVRPTWInstance (string node ids; see problem contract).
        rng: random.Random seeded by the caller.

    Returns:
        list[list[str]]: routes, each starting and ending at instance.depot_id.
    """
    raise NotImplementedError("construct")
'''

REPAIR_STUB = '''\
def repair(instance, routes, rng):
    """Repair infeasible routes (capacity / windows / battery / visits).

    Args:
        instance: EVRPTWInstance.
        routes: list[list[str]] from construct (or a prior iterate).
        rng: random.Random.

    Returns:
        list[list[str]]: repaired routes.
    """
    raise NotImplementedError("repair")
'''

IMPROVE_STUB = '''\
def improve(instance, routes, rng):
    """Locally improve feasible (or near-feasible) routes.

    Args:
        instance: EVRPTWInstance.
        routes: list[list[str]].
        rng: random.Random.

    Returns:
        list[list[str]]: improved routes.
    """
    raise NotImplementedError("improve")
'''

SOLVE_STUB = '''\
def solve(instance, seed: int, time_limit_s: float):
    """Entry point. Must make zero LLM calls.

    Args:
        instance: EVRPTWInstance.
        seed: int RNG seed.
        time_limit_s: float wall-clock budget for search inside solve.

    Returns:
        CandidateSolution or dict with key "routes" (list[list[str]]).
    """
    raise NotImplementedError("solve")
'''

REQUIRED_FUNCTIONS = ("construct", "repair", "improve", "solve")


def construct(instance: Any, rng: Any) -> list[list[str]]:
    """Stub signature only — LLM supplies the body in generated solvers."""
    raise NotImplementedError("construct")


def repair(instance: Any, routes: list[list[str]], rng: Any) -> list[list[str]]:
    """Stub signature only — LLM supplies the body in generated solvers."""
    raise NotImplementedError("repair")


def improve(instance: Any, routes: list[list[str]], rng: Any) -> list[list[str]]:
    """Stub signature only — LLM supplies the body in generated solvers."""
    raise NotImplementedError("improve")


def solve(instance: Any, seed: int, time_limit_s: float) -> Any:
    """Stub signature only — LLM supplies the body in generated solvers."""
    raise NotImplementedError("solve")


def _normalize_block(src: str) -> str:
    text = (src or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text if text.endswith("\n") else text + "\n"


def assemble_solver_source(
    imports: str | None,
    construct_src: str,
    repair_src: str,
    improve_src: str,
    solve_src: str,
) -> str:
    """Build a complete solver.py from imports + four function bodies."""
    header = _normalize_block(imports if imports is not None else DEFAULT_IMPORTS)
    parts = [
        header.rstrip() + "\n\n",
        _normalize_block(construct_src),
        "\n",
        _normalize_block(repair_src),
        "\n",
        _normalize_block(improve_src),
        "\n",
        _normalize_block(solve_src),
    ]
    text = "".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    return text


def stub_solver_source(imports: str | None = None) -> str:
    """Assemble the documented stubs into a compile-checkable module."""
    return assemble_solver_source(
        imports,
        CONSTRUCT_STUB,
        REPAIR_STUB,
        IMPROVE_STUB,
        SOLVE_STUB,
    )
