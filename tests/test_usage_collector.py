"""Centralized LLM usage / budget accounting tests."""
from __future__ import annotations

import pytest

from evrptw_autolab.llm.registry import FakeBackend
from evrptw_autolab.llm.usage import BudgetExhausted, UsageCollector


def test_token_sequence_sums_to_450() -> None:
    backend = FakeBackend(
        {"routing": '{"code": "ok"}'},
        token_sequence=[100, 150, 200],
    )
    collector = UsageCollector()
    for _ in range(3):
        collector.complete(
            backend, prompt="x", role="routing", temperature=0.0, model="fake-model", json_mode=True
        )
    assert collector.logical_calls == 3
    assert collector.http_attempts == 3
    assert collector.total_tokens == 450


def test_failed_generation_retry_counts_both_attempts() -> None:
    backend = FakeBackend(
        {"routing": '{"code": "ok"}'},
        token_sequence=[40, 60],
        fail_first_n=1,
    )
    collector = UsageCollector()
    collector.complete(
        backend, prompt="x", role="routing", temperature=0.0, model="fake-model", json_mode=True
    )
    assert collector.logical_calls == 1
    assert collector.http_attempts == 2
    assert collector.total_tokens == 100
    assert any(r.repair for r in collector.records)
    assert any(r.failed for r in collector.records)


def test_resume_does_not_reset_budget() -> None:
    backend = FakeBackend({"routing": '{"ok": true}'}, token_sequence=[50, 50, 50])
    collector = UsageCollector(max_tokens=120)
    collector.restore(logical_calls=2, total_tokens=100, wall_s=1.0)
    collector.complete(
        backend, prompt="x", role="routing", temperature=0.0, model="fake-model", json_mode=True
    )
    assert collector.total_tokens == 150
    assert collector.overshoot_tokens == 30
    with pytest.raises(BudgetExhausted):
        collector.complete(
            backend, prompt="x", role="routing", temperature=0.0, model="fake-model", json_mode=True
        )


def test_unavailable_model_is_not_substituted() -> None:
    from evrptw_autolab.llm.registry import SKIPPED_NOT_INSTALLED, ModelProfile, availability

    missing = ModelProfile(
        id="missing_local_model",
        provider="ollama",
        model="this-model-does-not-exist-xyz:999b",
        enabled=True,
    )
    status = availability(missing)
    assert status in {SKIPPED_NOT_INSTALLED, "SKIPPED_OLLAMA_UNAVAILABLE"}
    # Profile model string is preserved (no silent remap to an installed model).
    assert missing.model == "this-model-does-not-exist-xyz:999b"
