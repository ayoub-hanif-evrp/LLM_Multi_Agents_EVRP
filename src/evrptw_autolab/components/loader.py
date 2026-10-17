"""Validate and load pure scoring components.

Validation runs in a subprocess. The parent binds the function through a
bounded arithmetic interpreter. Generated source is never ``exec``'d in the
controller.
"""
from __future__ import annotations

import ast
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evrptw_autolab.components.interfaces import SIGNATURES, ComponentKind
from evrptw_autolab.components.interpret import UnsafeComponent, compile_component
from evrptw_autolab.sandbox.safe_exec import run_python_source
from evrptw_autolab.sandbox.static_scan import scan_source

_SMOKE_DRIVER = r'''
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))
import component  # noqa: F401

kind = {kind!r}
fn = getattr(component, kind)
if kind == "insertion_score":
    val = fn(1.0, 100.0, 0.0, 5.0, 50.0)
elif kind == "station_score":
    val = fn(2.0, 10.0, 1.0)
elif kind == "removal_priority":
    val = fn(100.0, 0.5, 0.1)
else:
    raise SystemExit("unknown kind")
if not isinstance(val, (int, float)) or isinstance(val, bool):
    raise TypeError("score must be numeric")
if not math.isfinite(float(val)):
    raise ValueError("score not finite")
print(json.dumps({{"ok": True, "value": float(val)}}))
'''


@dataclass
class ComponentLoadResult:
    ok: bool
    kind: ComponentKind
    source: str
    error: str = ""
    callable: Callable[..., float] | None = None
    smoke_value: float | None = None


def _forbid_imports_and_calls(source: str) -> list[str]:
    errors = scan_source(source)
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"syntax_error: {error}"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append("imports_forbidden_in_component")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "__builtins__":
            errors.append("builtins_escape")
        if isinstance(node, ast.Name) and node.id in {"open", "exec", "eval", "compile", "__import__"}:
            errors.append(f"forbidden_name:{node.id}")
    return errors


def validate_component_source(kind: ComponentKind, source: str, *, wall_clock_s: float = 3.0) -> dict[str, Any]:
    """AST + static scan + subprocess smoke. Never exec in parent."""
    out: dict[str, Any] = {"ok": False, "kind": kind, "detail": "", "value": None}
    if f"def {kind}" not in source:
        out["detail"] = f"missing def {kind}"
        return out
    errors = _forbid_imports_and_calls(source)
    if errors:
        out["detail"] = "; ".join(errors[:6])
        return out
    # Write as component.py for the driver.
    driver = _SMOKE_DRIVER.format(kind=kind)
    # safe_exec writes solver.py by default — use filename component.py
    result = run_python_source(
        source,
        wall_clock_s=wall_clock_s,
        filename="component.py",
        driver_source=driver,
    )
    if result.timed_out:
        out["detail"] = "timeout"
        return out
    if result.scan_errors:
        out["detail"] = result.error
        return out
    if result.crashed and not result.payload:
        out["detail"] = result.error or "subprocess crash"
        return out
    payload = result.payload or {}
    if not payload.get("ok"):
        out["detail"] = str(payload.get("detail") or result.error or "smoke failed")
        return out
    out["ok"] = True
    out["value"] = payload.get("value")
    return out


def load_component(kind: ComponentKind, source: str) -> ComponentLoadResult:
    """Validate then bind through the arithmetic interpreter. Never exec in parent."""
    check = validate_component_source(kind, source)
    if not check.get("ok"):
        return ComponentLoadResult(False, kind, source, error=str(check.get("detail") or "invalid"))
    try:
        fn = compile_component(kind, source)
    except (UnsafeComponent, SyntaxError, TypeError, ValueError) as error:
        return ComponentLoadResult(False, kind, source, error=f"bind_failed: {error}")
    return ComponentLoadResult(
        True,
        kind,
        source,
        callable=fn,
        smoke_value=float(check["value"]) if check.get("value") is not None else None,
    )


@dataclass
class PolicyBundle:
    """Set of scoring hooks for the classical backbone."""

    insertion_score: Callable[..., float] | None = None
    station_score: Callable[..., float] | None = None
    removal_priority: Callable[..., float] | None = None
    sources: dict[str, str] = field(default_factory=dict)
    owners: dict[str, str] = field(default_factory=dict)
    call_counts: dict[str, int] = field(default_factory=dict)

    def set(self, kind: ComponentKind, fn: Callable[..., float], source: str, owner: str) -> None:
        setattr(self, kind, fn)
        self.sources[kind] = source
        self.owners[kind] = owner


def load_bundle(sources: dict[ComponentKind, str], owners: dict[ComponentKind, str] | None = None) -> tuple[PolicyBundle, list[str]]:
    bundle = PolicyBundle()
    errors: list[str] = []
    owners = owners or {}
    for kind, source in sources.items():
        loaded = load_component(kind, source)
        if not loaded.ok or loaded.callable is None:
            errors.append(f"{kind}: {loaded.error}")
            continue
        bundle.set(kind, loaded.callable, source, owners.get(kind, "unknown"))
    return bundle, errors


def write_bundle(bundle: PolicyBundle, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for kind, source in bundle.sources.items():
        (directory / f"{kind}.py").write_text(source, encoding="utf-8")
    meta = {"owners": bundle.owners, "kinds": list(bundle.sources)}
    path = directory / "bundle.json"
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return path


# Silence unused SIGNATURES import warning by referencing it.
_ = SIGNATURES
