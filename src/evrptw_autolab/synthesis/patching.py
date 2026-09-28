"""Apply whole-file agent proposals to a solver directory."""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from evrptw_autolab.agents.schemas import CodeProposal

ALLOWED_ROOTS = ("solver/",)


def apply_proposal(solver_dir: Path, proposal: CodeProposal) -> list[Path]:
    written: list[Path] = []
    solver_dir.mkdir(parents=True, exist_ok=True)
    for item in proposal.files:
        relative = item.path.replace("\\", "/").lstrip("/")
        if ".." in relative.split("/"):
            raise ValueError(f"illegal path: {item.path}")
        if not any(relative == "solver.py" or relative.startswith(root) for root in (*ALLOWED_ROOTS, "solver.py")):
            if not relative.endswith(".py"):
                raise ValueError(f"only Python solver files are allowed: {item.path}")
        target = solver_dir / Path(relative).name if "/" not in relative.strip("/") else solver_dir / relative
        if relative == "solver.py" or relative.endswith("/solver.py"):
            target = solver_dir / "solver.py"
        elif relative.startswith("solver/"):
            target = solver_dir / relative.split("/", 1)[1]
        else:
            target = solver_dir / Path(relative).name
        if item.operation == "delete":
            if target.exists():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        written.append(target)
    return written


def snapshot_files(solver_dir: Path, *, max_chars: int = 8000) -> dict[str, str]:
    files: dict[str, str] = {}
    if not solver_dir.exists():
        return files
    for path in sorted(solver_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n# ... truncated ..."
        files[path.relative_to(solver_dir).as_posix()] = text
    return files


def code_hash(solver_dir: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(solver_dir.rglob("*.py")):
        hasher.update(path.relative_to(solver_dir).as_posix().encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def next_free_solver_id(candidates_dir: Path, taken: set[str]) -> str:
    index = 0
    while index <= 999:
        solver_id = f"S{index:03d}"
        dest = candidates_dir / solver_id
        if solver_id not in taken and not dest.exists():
            return solver_id
        index += 1
    raise RuntimeError("no free solver id")


def copy_solver_tree(source: Path, dest: Path) -> Path:
    """Copy a solver tree. Never deletes a locked OneDrive folder; dest must be new."""
    if dest.exists():
        raise FileExistsError(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)
    return dest


def snapshot_solver(solver_dir: Path, dest: Path) -> Path:
    if dest.exists():
        try:
            shutil.rmtree(dest)
        except OSError:
            dest = dest.with_name(f"{dest.name}_r{next_free_solver_id(dest.parent, set())}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(solver_dir, dest)
    return dest


def rollback_to(parent_dir: Path, solver_dir: Path) -> Path:
    return snapshot_solver(parent_dir, solver_dir)
