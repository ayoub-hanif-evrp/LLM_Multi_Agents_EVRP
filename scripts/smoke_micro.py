"""Engineering smoke test: Qwen 14B on synthetic micro G0-G3 only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evrptw_autolab.llm.ollama import OllamaBackend  # noqa: E402
from evrptw_autolab.llm.registry import availability, resolve_profile  # noqa: E402
from evrptw_autolab.synthesis.from_scratch import STAGES, copy_run_provenance, run_from_scratch  # noqa: E402


def main() -> None:
    profile = resolve_profile("qwen25_coder_14b")
    backend = OllamaBackend(
        timeout_s=float(profile.timeout_s or 300.0),
        num_ctx=profile.num_ctx,
        keep_alive="20m",
        seed=11,
    )
    if availability(profile, backend) != "installed":
        raise SystemExit(f"missing model: {profile.model}")
    workspace = ROOT / "workspace" / "smoke_micro" / "qwen25_coder_14b" / "seed11"
    report = run_from_scratch(
        mode="five_agent",
        model=profile.model,
        backend=backend,
        workspace=workspace,
        temperatures=profile.temperatures,
        max_llm_calls=40,
        stages=STAGES[:4],
    )
    dest = ROOT / "results" / "smoke_micro" / "qwen25_coder_14b_seed11.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2), encoding="utf-8")
    copy_run_provenance(workspace, ROOT / "results" / "smoke_micro" / "raw", report)
    print(json.dumps({k: report[k] for k in (
        "executable", "routing", "charging", "multi_customer",
        "deepest_gate", "failure_category", "failure_reason", "llm_calls", "tokens",
    )}, indent=2))


if __name__ == "__main__":
    main()
