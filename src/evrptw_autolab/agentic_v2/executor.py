"""Run an agent-generated solver on a JSON instance. The parent evaluates afterward."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from evrptw_autolab.sandbox.static_scan import scan_source

_DRIVER = """
import json
import sys
from pathlib import Path

sys.path.insert(0, {solver_dir!r})
import solver

instance = json.loads(Path({instance_path!r}).read_text(encoding="utf-8"))
result = solver.solve(instance)
if not isinstance(result, dict):
    raise TypeError("solve must return a JSON object")
Path({output_path!r}).write_text(json.dumps(result), encoding="utf-8")
"""


def _blocked(source: str) -> list[str]:
    errors = scan_source(source)
    lowered = source.lower()
    for marker in ("solve_classical", "evrptw_autolab.backbone", "import alns"):
        if marker in lowered:
            errors.append(f"classical_solver_forbidden:{marker}")
    if "def solve" not in source:
        errors.append("missing_solve")
    return errors


def execute_generated_solver(source: str, instance: dict[str, Any], *, time_limit_s: float = 20.0) -> dict[str, Any]:
    """Execute generated code in a subprocess. The returned object is untrusted JSON."""
    errors = _blocked(source)
    if errors:
        return {"ok": False, "errors": errors, "routes": None, "runtime_s": 0.0}
    with tempfile.TemporaryDirectory(prefix="voltforge-agentic-") as directory:
        root = Path(directory)
        (root / "solver.py").write_text(source, encoding="utf-8")
        instance_path = root / "instance.json"
        output_path = root / "output.json"
        instance_path.write_text(json.dumps(instance), encoding="utf-8")
        driver = root / "driver.py"
        driver.write_text(
            _DRIVER.format(
                solver_dir=str(root),
                instance_path=str(instance_path),
                output_path=str(output_path),
            ),
            encoding="utf-8",
        )
        started = time.monotonic()
        try:
            completed = subprocess.run(
                [sys.executable, str(driver)],
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=time_limit_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "errors": ["timeout"], "routes": None, "runtime_s": time_limit_s}
        runtime = time.monotonic() - started
        if completed.returncode != 0 or not output_path.exists():
            detail = (completed.stderr or completed.stdout or "no output")[-500:]
            return {"ok": False, "errors": [detail], "routes": None, "runtime_s": runtime}
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            return {"ok": False, "errors": [f"invalid_json:{error}"], "routes": None, "runtime_s": runtime}
    return {"ok": True, "errors": [], "routes": payload, "runtime_s": runtime}
