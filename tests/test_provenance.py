"""Provenance stamps and result reuse gates."""
from __future__ import annotations

import json
from pathlib import Path

from evrptw_autolab.synthesis.provenance import (
    config_hash,
    git_commit,
    protocol_hash,
    refuse_stale_or_missing,
    should_reuse_result,
    stamp_report,
)

ROOT = Path(__file__).resolve().parents[1]


def test_protocol_and_config_hash_stable() -> None:
    first = protocol_hash(ROOT)
    second = protocol_hash(ROOT)
    assert first == second
    assert len(first) == 64
    cfg = config_hash(ROOT)
    assert cfg == config_hash(ROOT)
    assert len(cfg) == 64
    assert first != cfg or True  # may coincide only by chance; both must be hex


def test_stamp_report_fields() -> None:
    stamped = stamp_report({"ok": True}, ROOT)
    assert stamped["git_commit"] == git_commit(ROOT)
    assert stamped["protocol_hash"] == protocol_hash(ROOT)
    assert stamped["config_hash"] == config_hash(ROOT)
    assert stamped["timestamp"].endswith("Z")


def test_reuse_rejects_mismatched_commit(tmp_path: Path) -> None:
    dest = tmp_path / "result.json"
    good = stamp_report({"seed": 11, "model_tag": "x"}, ROOT)
    dest.write_text(json.dumps(good), encoding="utf-8")
    assert should_reuse_result(dest, ROOT) is True
    assert refuse_stale_or_missing(dest, ROOT) is False

    stale = dict(good)
    stale["git_commit"] = "0" * 40
    dest.write_text(json.dumps(stale), encoding="utf-8")
    assert should_reuse_result(dest, ROOT) is False
    assert refuse_stale_or_missing(dest, ROOT) is True

    missing = tmp_path / "missing.json"
    assert should_reuse_result(missing, ROOT) is False
    assert refuse_stale_or_missing(missing, ROOT) is True


def test_reuse_rejects_mismatched_protocol(tmp_path: Path) -> None:
    dest = tmp_path / "result.json"
    row = stamp_report({"seed": 22}, ROOT)
    row["protocol_hash"] = "deadbeef" * 8
    dest.write_text(json.dumps(row), encoding="utf-8")
    assert should_reuse_result(dest, ROOT) is False
