"""Static safety scan of untrusted generated solver source."""
from __future__ import annotations

import ast
from pathlib import Path

FORBIDDEN_MODULES = {
    "subprocess",
    "socket",
    "requests",
    "http",
    "http.client",
    "httpx",
    "urllib",
    "urllib.request",
    "ctypes",
    "multiprocessing",
    "pickle",
    "importlib",
    "pip",
}
FORBIDDEN_NAMES = {
    "system",
    "popen",
    "spawn",
    "execl",
    "execv",
    "walk",
    "rmtree",
    "remove",
    "unlink",
    "getenv",
    "environ",
}
FORBIDDEN_IMPORT_PREFIXES = ("evrptw_autolab.evaluation", "evrptw_autolab.experiments")
HELD_OUT_MARKERS = ("rc201", "rc202", "rc203", "rc204", "rc205", "rc206", "rc207", "rc208")


def scan_source(source: str) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return [f"syntax_error: {error}"]
    lowered = source.lower()
    for marker in HELD_OUT_MARKERS:
        if marker in lowered:
            errors.append(f"possible_heldout_hardcode:{marker}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FORBIDDEN_MODULES or alias.name.split(".")[0] in FORBIDDEN_MODULES:
                    errors.append(f"forbidden_import:{alias.name}")
                if alias.name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                    errors.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module in FORBIDDEN_MODULES or module.split(".")[0] in FORBIDDEN_MODULES:
                errors.append(f"forbidden_import:{module}")
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                errors.append(f"forbidden_import:{module}")
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "os" and node.attr in FORBIDDEN_NAMES:
                errors.append(f"forbidden_call:os.{node.attr}")
            if node.value.id == "shutil" and node.attr in {"rmtree", "move"}:
                errors.append(f"forbidden_call:shutil.{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            errors.append(f"forbidden_call:{node.func.id}")
    return errors


def scan_directory(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*.py")):
        errors.extend(f"{path.name}:{item}" for item in scan_source(path.read_text(encoding="utf-8")))
    return errors
