"""VoltForge CLI: validate data and list local models."""
from __future__ import annotations

from pathlib import Path

import typer

from evrptw_autolab.evaluation.fidelity import load_all, split_instances, write_split_manifest
from evrptw_autolab.llm.ollama import OllamaBackend
from evrptw_autolab.llm.registry import SKIPPED_NOT_INSTALLED, availability, list_profiles
from evrptw_autolab.problem.hashes import write_instance_hashes
from evrptw_autolab.problem.schneider import SCHNEIDER_ROOT, discover_instances

app = typer.Typer(no_args_is_help=True, add_completion=False)
models_app = typer.Typer(no_args_is_help=True, help="Inspect configured LLM model profiles.")
app.add_typer(models_app, name="models")
ROOT = Path(__file__).resolve().parents[2]


@app.command("validate-data")
def validate_data() -> None:
    paths = discover_instances(ROOT / SCHNEIDER_ROOT)
    instances = load_all(ROOT / SCHNEIDER_ROOT)
    split = split_instances(instances)
    manifest = write_split_manifest(ROOT / "results" / "manifests" / "split.json", split)
    hashes = write_instance_hashes(ROOT / "results" / "manifests" / "instance_hashes.json")
    typer.echo(
        f"OK {len(paths)} Schneider instances; discovery={len(split['discovery'])} "
        f"confirmation={len(split['confirmation'])} heldout={len(split['heldout'])} "
        f"manifest={manifest} hashes={hashes}"
    )


@models_app.command("list")
def models_list() -> None:
    ollama = OllamaBackend()
    for profile in list_profiles():
        status = availability(profile, ollama)
        flag = "SKIPPED_NOT_INSTALLED" if status == SKIPPED_NOT_INSTALLED else status
        typer.echo(f"{profile.id:20s} {profile.model:24s} {flag}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
