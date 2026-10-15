"""VoltForge CLI: validate data, list models, audit datasets."""
from __future__ import annotations

import json
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
components_app = typer.Typer(no_args_is_help=True, help="Component synthesis smoke (Track 2).")
app.add_typer(models_app, name="models")
app.add_typer(datasets_app, name="datasets")
app.add_typer(components_app, name="components")
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


@components_app.command("smoke")
def components_smoke(
    fake: bool = typer.Option(True, "--fake/--ollama", help="Use FakeBackend (default) or local Ollama"),
    profile: str = typer.Option("qwen3_coder_30b", "--profile", help="Ollama profile id when --ollama"),
    seed: int = typer.Option(0, "--seed"),
) -> None:
    """Cheap end-to-end component synthesis on Schneider micro_g2 (no long campaign)."""
    from evrptw_autolab.components.interfaces import DEFAULT_SOURCES
    from evrptw_autolab.components.run import synthesize_components
    from evrptw_autolab.llm.registry import FakeBackend, availability, make_backend, resolve_profile
    from evrptw_autolab.problem.datasets.schneider_v2 import load_schneider_v2
    from evrptw_autolab.problem.micro import micro_g2_needs_charge

    spec = load_schneider_v2(micro_g2_needs_charge().metadata["source_path"])
    if fake:
        backend = FakeBackend(
            {
                "architect": json.dumps(
                    {
                        "summary": "smoke",
                        "components": ["insertion_score", "station_score", "removal_priority"],
                        "risks": [],
                        "success_criteria": ["feasible"],
                        "variant_notes": "micro",
                    }
                ),
                "routing": json.dumps(
                    {
                        "component": "insertion_score",
                        "owner_role": "routing",
                        "code": DEFAULT_SOURCES["insertion_score"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "charging": json.dumps(
                    {
                        "component": "station_score",
                        "owner_role": "charging",
                        "code": DEFAULT_SOURCES["station_score"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "search": json.dumps(
                    {
                        "component": "removal_priority",
                        "owner_role": "search",
                        "code": DEFAULT_SOURCES["removal_priority"],
                        "rationale": "r",
                        "mechanism": "m",
                    }
                ),
                "critic": json.dumps(
                    {"verdict": "ACCEPT", "reason": "smoke", "next_component": "none"}
                ),
            }
        )
        model = "fake"
    else:
        from evrptw_autolab.llm.ollama import OllamaBackend

        ollama = OllamaBackend()
        prof = resolve_profile(profile)
        status = availability(prof, ollama)
        if status != "installed":
            typer.echo(f"SKIPPED: profile {profile} status={status}")
            raise typer.Exit(code=0)
        backend = make_backend(prof, ollama_host=ollama.host)
        model = prof.model
    out_dir = ROOT / "results" / "v2" / "runs" / f"component_smoke_seed{seed}"
    result = synthesize_components(
        spec, backend, model=model, seed=seed, time_limit_s=5.0, work_dir=out_dir
    )
    typer.echo(json.dumps({k: result[k] for k in (
        "feasible", "vehicles", "distance", "llm_calls", "critic_verdict", "wall_s", "bundle_dir"
    )}, indent=2))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
