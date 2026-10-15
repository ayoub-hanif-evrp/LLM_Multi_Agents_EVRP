"""Shared subprocess boundary for untrusted generated Python.

This is an ordinary process isolation layer with timeouts and static scanning —
not a hardened security sandbox. Prefer WSL2/Docker for stronger isolation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evrptw_autolab.sandbox.static_scan import scan_source

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PACKAGE_SRC = ROOT / "src"

# Driver used for structured Level-A function unit tests (no Schneider files).
_UNIT_DRIVER = r'''
import json
import random
import sys
import traceback
from pathlib import Path

sys.path.insert(0, {package_src!r})
sys.path.insert(0, {solver_dir!r})

from evrptw_autolab.problem.micro import micro_g1_one_customer
from solver import construct, repair, improve, solve

out = {{
    "ok": False,
    "syntax_ok": True,
    "missing": [],
    "construct_ok": False,
    "repair_ok": False,
    "improve_ok": False,
    "solve_ok": False,
    "detail": "",
}}
try:
    instance = micro_g1_one_customer()
    rng = random.Random(0)
    routes = construct(instance, rng)
    out["construct_ok"] = isinstance(routes, list)
    if not out["construct_ok"]:
        out["detail"] = "construct did not return list"
        print(json.dumps(out))
        raise SystemExit(0)
    repaired = repair(instance, routes, rng)
    out["repair_ok"] = isinstance(repaired, list)
    if not out["repair_ok"]:
        out["detail"] = "repair did not return list"
        print(json.dumps(out))
        raise SystemExit(0)
    improved = improve(instance, repaired, rng)
    out["improve_ok"] = isinstance(improved, list)
    if not out["improve_ok"]:
        out["detail"] = "improve did not return list"
        print(json.dumps(out))
        raise SystemExit(0)
    sol = solve(instance, 0, 1.0)
    if hasattr(sol, "routes"):
        out["solve_ok"] = True
    elif isinstance(sol, dict) and "routes" in sol:
        out["solve_ok"] = True
    else:
        out["detail"] = "solve return shape"
        print(json.dumps(out))
        raise SystemExit(0)
    out["ok"] = all([out["construct_ok"], out["repair_ok"], out["improve_ok"], out["solve_ok"]])
except Exception as error:
    out["detail"] = f"{{type(error).__name__}}: {{error}}"
    out["traceback"] = traceback.format_exc()[-2000:]
print(json.dumps(out))
'''


@dataclass
class SafeExecResult:
    ok: bool
    timed_out: bool = False
    crashed: bool = False
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    runtime_s: float = 0.0
    error: str = ""
    scan_errors: list[str] = field(default_factory=list)


def _kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    """Best-effort Windows/POSIX process-tree cleanup after timeout."""
    if proc.poll() is not None:
        return
    pid = proc.pid
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
                timeout=10,
            )
        else:
            import signal

            os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def run_python_source(
    source: str,
    *,
    wall_clock_s: float = 5.0,
    package_src: Path | None = None,
    max_output_bytes: int = 200_000,
    filename: str = "solver.py",
    driver_source: str | None = None,
) -> SafeExecResult:
    """Write ``source`` to an isolated temp dir and execute a driver in a subprocess.

    Does **not** ``exec`` untrusted code in the parent process.
    """
    scan_errors = scan_source(source)
    if scan_errors:
        return SafeExecResult(
            ok=False,
            crashed=True,
            error="; ".join(scan_errors[:8]),
            scan_errors=scan_errors,
        )

    src = str((package_src or DEFAULT_PACKAGE_SRC).resolve())
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="voltforge_safe_") as tmp:
        work = Path(tmp)
        solver_path = work / filename
        solver_path.write_text(source, encoding="utf-8")
        driver = work / "driver.py"
        body = driver_source or _UNIT_DRIVER.format(
            package_src=src,
            solver_dir=str(work.resolve()),
        )
        driver.write_text(body, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": src, "PYTHONUNBUFFERED": "1"}
        env.pop("OLLAMA_HOST", None)
        # Deny accidental LLM use inside generated code paths.
        env["VOLTFORGE_DENY_LLM"] = "1"

        popen_kwargs: dict[str, Any] = {
            "cwd": str(work),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "env": env,
        }
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen([sys.executable, str(driver)], **popen_kwargs)
        try:
            stdout, stderr = proc.communicate(timeout=float(wall_clock_s))
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            try:
                stdout, stderr = proc.communicate(timeout=2.0)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
            return SafeExecResult(
                ok=False,
                timed_out=True,
                crashed=True,
                returncode=proc.returncode,
                stdout=(stdout or "")[:max_output_bytes],
                stderr=(stderr or "")[:max_output_bytes],
                runtime_s=time.monotonic() - started,
                error="timeout",
            )

        runtime = time.monotonic() - started
        stdout = (stdout or "")[:max_output_bytes]
        stderr = (stderr or "")[:max_output_bytes]
        if proc.returncode != 0:
            return SafeExecResult(
                ok=False,
                crashed=True,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                runtime_s=runtime,
                error=(stderr or stdout or "subprocess_crash")[-2000:],
            )
        payload: dict[str, Any] = {}
        try:
            line = stdout.strip().splitlines()[-1] if stdout.strip() else ""
            payload = json.loads(line) if line else {}
        except (json.JSONDecodeError, IndexError) as error:
            return SafeExecResult(
                ok=False,
                crashed=True,
                returncode=proc.returncode,
                stdout=stdout,
                stderr=stderr,
                runtime_s=runtime,
                error=f"bad_payload: {error}",
            )
        return SafeExecResult(
            ok=bool(payload.get("ok")),
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            payload=payload,
            runtime_s=runtime,
        )


def run_hanging_probe(wall_clock_s: float = 1.0) -> SafeExecResult:
    """Test helper: deliberate infinite loop at import time under timeout."""
    source = "while True:\n    pass\n"
    # Minimal driver: importing solver executes the hang.
    driver = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path('.').resolve()))\n"
        "import solver  # noqa: F401\n"
        "print('{\"ok\": true}')\n"
    )
    return run_python_source(
        source,
        wall_clock_s=wall_clock_s,
        driver_source=driver,
        filename="solver.py",
    )
