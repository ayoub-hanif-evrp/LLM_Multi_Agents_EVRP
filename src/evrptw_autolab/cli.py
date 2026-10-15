"""VoltForge CLI: validate data, list models, audit datasets."""
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
datasets_app = typer.Typer(no_args_is_help=True, help="Dataset registry and audit.")
app.add_typer(models_app, name="models")
app.add_typer(datasets_app, name="datasets")
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


@models_app.command("smoke")
def models_smoke(
    model: str = typer.Option(..., "--model", help="Exact Ollama model tag, e.g. qwen3-coder:30b"),
) -> None:
    """Fast capability smoke: server up, model installed, /api/show details."""
    ollama = OllamaBackend()
    report = ollama.capability_smoke(model)
    typer.echo(report)


@datasets_app.command("audit")
def datasets_audit(
    write_manifest: bool = typer.Option(
        True, "--write-manifest/--no-write-manifest", help="Write results/v2/manifests/dataset_audit.json"
    ),
) -> None:
    """Enumerate and hash all five benchmark families; validate Schneider via legacy loader."""
    from evrptw_autolab.problem.datasets.registry import audit_all, write_audit_manifest

    audits = audit_all()
    for audit in audits:
        typer.echo(
            f"{audit.family_id:10s} exists={audit.folder_exists} "
            f"raw={audit.raw_file_count:4d} instances={audit.instance_file_count:4d} "
            f"status={audit.parse_status} - {audit.parse_note}"
        )
        for warning in audit.warnings[:3]:
            typer.echo(f"  warning: {warning}")
    if write_manifest:
        path = write_audit_manifest(audits, ROOT / "results" / "v2" / "manifests" / "dataset_audit.json")
        typer.echo(f"manifest={path}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
