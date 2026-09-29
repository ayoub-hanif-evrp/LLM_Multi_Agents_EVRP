"""Unit test: OllamaBackend accepts seed in options (no network)."""
from __future__ import annotations

import json

from evrptw_autolab.llm.ollama import OllamaBackend, derived_call_seed


def test_ollama_backend_stores_seed() -> None:
    b = OllamaBackend(seed=33)
    assert b.seed == 33
    b2 = OllamaBackend()
    assert b2.seed is None


def test_ollama_options_include_seed(monkeypatch) -> None:
    captured: dict = {}

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {"message": {"content": '{"ok": true}'}, "prompt_eval_count": 1, "eval_count": 1}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    b = OllamaBackend(seed=44)
    b.complete(prompt="hi", role="routing", temperature=0.2, model="x", json_mode=True)
    assert captured["body"]["options"]["seed"] == 44
    assert "temperature" in captured["body"]["options"]


def test_diversified_calls_get_distinct_logged_seeds(monkeypatch) -> None:
    captured: list[int] = []

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(
                {"message": {"content": "code"}, "prompt_eval_count": 2, "eval_count": 3}
            ).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        body = json.loads(request.data.decode("utf-8"))
        captured.append(int(body["options"]["seed"]))
        return FakeResp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    backend = OllamaBackend(seed=11)
    backend.diversify_calls = True
    backend.complete(prompt="a", role="architect", temperature=0.2, model="x", json_mode=False)
    backend.complete(prompt="b", role="search", temperature=0.2, model="x", json_mode=False)
    assert captured == [
        derived_call_seed(11, 1, "architect"),
        derived_call_seed(11, 2, "search"),
    ]
    assert captured[0] != captured[1]
    assert backend.pending_usages[-1].seed == captured[-1]
    assert backend.pending_usages[-1].base_seed == 11
    assert backend.pending_usages[-1].call_index == 2
