"""FakeBackend research campaign plumbing (not a scientific claim)."""
from __future__ import annotations

from pathlib import Path

from evrptw_autolab.experiments.campaign import (
    CampaignConfig,
    _select_panel_items,
    run_research_campaign,
)


def test_fake_campaign_runs_all_arms(tmp_path: Path) -> None:
    payload = run_research_campaign(
        CampaignConfig(
            seed=0,
            fake=True,
            max_instances=1,
            time_limit_s=1.5,
            alns_iterations=10,
            evolution_generations=1,
            max_llm_calls=20,
            out_dir=tmp_path / "camp",
        )
    )
    arms = {row["arm"] for row in payload["rows"]}
    assert arms >= {"classical", "single_agent", "five_agent", "five_agent_evolution"}
    assert (tmp_path / "camp" / "campaign.json").exists()
    assert payload["aggregate"]["classical"]["n"] == 1


def test_live_ollama_campaign_is_blocked(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(RuntimeError, match="Live Qwen is blocked"):
        run_research_campaign(CampaignConfig(fake=False, out_dir=tmp_path / "live"))


def test_panel_cap_spans_families() -> None:
    items = _select_panel_items(CampaignConfig(max_instances=5, fake=True))
    families = {i.family for i in items}
    assert len(items) == 5
    assert len(families) >= 4
