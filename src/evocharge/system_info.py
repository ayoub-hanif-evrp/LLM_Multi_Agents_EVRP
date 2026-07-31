"""Startup diagnostics for reproducibility (no model inference)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import psutil

from evocharge import __version__
from evocharge.reproducibility import git_commit, lockfile_hash, source_state


def _ollama_version() -> str | None:
    """Probe Ollama CLI version without loading or invoking a model."""
    exe = shutil.which("ollama")
    if exe is None:
        return None
    try:
        result = subprocess.run(
            [exe, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        text = (result.stdout or result.stderr or "").strip()
        return text or None
    except (OSError, subprocess.SubprocessError):
        return None


def _gpu_info() -> dict[str, Any]:
    info: dict[str, Any] = {"name": None, "vram_mb": None, "source": None}
    if shutil.which("nvidia-smi") is None:
        return info
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                info["name"] = parts[0]
                try:
                    info["vram_mb"] = float(parts[1])
                except ValueError:
                    info["vram_mb"] = parts[1]
                info["source"] = "nvidia-smi"
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def collect_system_info(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    vm = psutil.virtual_memory()
    return {
        "evocharge_version": __version__,
        "python_version": sys.version,
        "python_executable": sys.executable,
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "cpu": {
            "physical": psutil.cpu_count(logical=False),
            "logical": psutil.cpu_count(logical=True),
        },
        "ram": {
            "total_bytes": int(vm.total),
            "available_bytes": int(vm.available),
        },
        "gpu": _gpu_info(),
        "ollama": {
            "available": shutil.which("ollama") is not None,
            "version": _ollama_version(),
            "note": (
                "CLI version probe only; agent inference uses "
                "evocharge agent check-ollama / run-m6."
            ),
        },
        "git_commit": git_commit(root),
        "source_state": source_state(root).model_dump(),
        "dependency_lock_hash": lockfile_hash(root),
        "cwd": str(Path.cwd()),
        "project_root": str(root),
        "env_pythonpath": os.environ.get("PYTHONPATH"),
    }
