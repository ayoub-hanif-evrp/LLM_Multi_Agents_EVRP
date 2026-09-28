"""Safe freeze paths for SLM-Evo artifacts (never overwrite OPT_V1)."""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS_SLM_EVO = REPO_ROOT / "results" / "md" / "artifacts" / "slm_evo"
OPT_V1_DIR = ARTIFACTS_SLM_EVO / "OPT_V1"
OPT_V1_NAME = "OPT_V1"


def assert_not_opt_v1(dest: Path) -> None:
    resolved = dest.resolve()
    opt_v1 = OPT_V1_DIR.resolve()
    if resolved == opt_v1 or opt_v1 in resolved.parents or resolved.name == OPT_V1_NAME:
        raise RuntimeError(f"refusing to write immutable OPT_V1 path: {dest}")


def freeze_dir_for(
    *,
    source_hash: str,
    seed_base: int | None = None,
    campaign_id: str = "",
    continuation: bool = False,
) -> Path:
    """Build a unique freeze directory under artifacts/slm_evo (never OPT_V1)."""
    if continuation or (campaign_id.startswith("cont") or campaign_id.startswith("evo_cont")):
        name = f"OPT_BEST_CONT_{source_hash}"
    elif seed_base is not None:
        name = f"OPT_SEED{seed_base}_{source_hash}"
    elif campaign_id:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in campaign_id)
        name = f"OPT_{safe}_{source_hash}"
    else:
        name = f"VEHICLE_WIN_{source_hash}"
    if name == OPT_V1_NAME or name.startswith("OPT_V1"):
        raise RuntimeError(f"illegal freeze name: {name}")
    dest = ARTIFACTS_SLM_EVO / name
    assert_not_opt_v1(dest)
    return dest
