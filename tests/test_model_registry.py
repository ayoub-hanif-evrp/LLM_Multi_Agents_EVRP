from evrptw_autolab.llm.registry import (
    SKIPPED_NOT_INSTALLED,
    FakeBackend,
    ModelProfile,
    availability,
    list_profiles,
    resolve_profile,
)


class _StubOllama:
    def __init__(self, *, up: bool, installed: set[str]) -> None:
        self._up = up
        self._installed = installed

    def available(self) -> bool:
        return self._up

    def installed_models(self) -> set[str]:
        return self._installed


def test_configured_comparison_models() -> None:
    profiles = list_profiles()
    assert len(profiles) >= 4
    ids = {p.id for p in profiles}
    assert "qwen25_coder_3b" in ids
    assert resolve_profile("qwen25_coder_7b").model == "qwen2.5-coder:7b"


def test_missing_model_is_skipped() -> None:
    profile = ModelProfile(id="missing", provider="ollama", model="not-a-real-model:9b")
    status = availability(profile, _StubOllama(up=True, installed={"qwen2.5-coder:3b"}))  # type: ignore[arg-type]
    assert status == SKIPPED_NOT_INSTALLED


def test_ollama_down() -> None:
    profile = ModelProfile(id="x", provider="ollama", model="qwen2.5-coder:3b")
    status = availability(profile, _StubOllama(up=False, installed=set()))  # type: ignore[arg-type]
    assert status == "SKIPPED_OLLAMA_UNAVAILABLE"


def test_fake_backend_sequence() -> None:
    backend = FakeBackend({"architect": ["{}", "{ }"]})
    assert backend.complete(prompt="p", role="architect", temperature=0.1, model="fake") == "{}"
    assert backend.calls == ["architect"]
