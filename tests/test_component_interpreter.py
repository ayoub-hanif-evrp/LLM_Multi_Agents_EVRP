"""Scoring components are bound by a bounded interpreter, never exec'd in-process."""
from __future__ import annotations

from evrptw_autolab.components.interpret import UnsafeComponent, compile_component
from evrptw_autolab.components.loader import load_component


def test_interpreter_evaluates_arithmetic() -> None:
    source = (
        "def insertion_score(delta_distance, due_time, ready_time, demand, capacity_slack):\n"
        "    return delta_distance + (0.0 if capacity_slack >= demand else 10.0)\n"
    )
    fn = compile_component("insertion_score", source)
    assert fn(1.0, 0.0, 0.0, 2.0, 5.0) == 1.0
    assert fn(1.0, 0.0, 0.0, 5.0, 2.0) == 11.0


def test_interpreter_rejects_imports_loops_and_nonfinite() -> None:
    imported = "import os\ndef insertion_score(a, b, c, d, e):\n    return a\n"
    loop = "def insertion_score(a, b, c, d, e):\n    while True:\n        a = a + 1\n    return a\n"
    div = "def insertion_score(a, b, c, d, e):\n    return a / 0.0\n"
    for source in (imported, loop):
        try:
            compile_component("insertion_score", source)
        except UnsafeComponent:
            continue
        raise AssertionError("unsafe component was compiled")
    fn = compile_component("insertion_score", div)
    try:
        fn(1.0, 0.0, 0.0, 0.0, 0.0)
    except UnsafeComponent:
        pass
    else:
        raise AssertionError("division by zero returned a value")
    loaded = load_component("insertion_score", imported)
    assert loaded.ok is False
    assert loaded.callable is None
