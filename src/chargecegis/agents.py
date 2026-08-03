"""Five strictly separated LLM roles with deterministic output validation."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import yaml
from pydantic import BaseModel, Field

from .policy_dsl import Policy, parse_policy, policy_hash

ROOT = Path(__file__).resolve().parents[2]
MODELS_CONFIG_PATH = ROOT / "configs" / "models.yaml"
PROMPTS = ROOT / "prompts"

MODEL = "qwen2.5-coder:3b"
TEMPERATURES = {"analyst": .10, "scientist": .45, "synthesizer": .20, "counterexample": .40, "critic": .10}
OLLAMA_BASE_URL = "http://127.0.0.1:11434"


class AnalystReport(BaseModel):
    dominant_failure: str
    supporting_metrics: list[str]
    alternative_explanations: list[str]
    uncertainty: float = Field(ge=0, le=1)
    missing_evidence: list[str]


class ScientistHypothesis(BaseModel):
    hypothesis: str
    target_mechanism: str
    required_features: list[str]
    expected_behavior: str
    no_action_conditions: list[str]
    invariants: list[str]
    falsification_condition: str


class Challenge(BaseModel):
    type: str
    target_failure: str
    state_requirements: list[str]
    expected_invariant: str


class CounterexamplePlan(BaseModel):
    challenges: list[Challenge]


class CriticReport(BaseModel):
    decision: str
    evidence: list[str]
    failure_class: str
    revision_instruction: str
    claim_limit: str


class Backend(Protocol):
    def __call__(self, *, prompt: str, role: str, model: str, temperature: float) -> str | dict[str, Any]: ...


class MockBackend:
    """Fixture backend: map role names to JSON-compatible fixture responses."""
    def __init__(self, fixtures: dict[str, Any]) -> None: self.fixtures = fixtures
    def __call__(self, **kwargs: Any) -> Any: return self.fixtures[kwargs["role"]]


def load_model_config(path: Path | None = None) -> dict[str, Any]:
    """Load configs/models.yaml (repo-root relative), used by OllamaBackend."""
    with (path or MODELS_CONFIG_PATH).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class OllamaBackend:
    """Sequential, single-model Ollama backend: one JSON-repair retry, failures always raise."""

    def __init__(self, config: dict[str, Any] | None = None, base_url: str = OLLAMA_BASE_URL,
                 timeout: float = 120.0) -> None:
        config = config if config is not None else load_model_config()
        ollama_config = config.get("ollama", {})
        self.model: str = ollama_config.get("model", MODEL)
        self.temperatures: dict[str, float] = config.get("temperatures", TEMPERATURES)
        self.num_ctx: int = ollama_config.get("num_ctx", 4096)
        self.keep_alive: str = ollama_config.get("keep_alive", "5m")
        self.base_url = base_url
        self.timeout = timeout
        self.last_model: str | None = None
        self.last_latency_seconds: float = 0.0
        self.last_digest: str | None = None

    def _request(self, prompt: str, temperature: float) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise ValueError(f"Ollama HTTP {error.code}") from error
        except urllib.error.URLError as error:
            raise ValueError(f"Ollama connection failed: {error}") from error
        self.last_latency_seconds = time.monotonic() - started
        self.last_model = body.get("model", self.model)
        self.last_digest = body.get("digest")
        content = str(body.get("message", {}).get("content", ""))
        if not content:
            raise ValueError("empty content from Ollama response")
        json.loads(content)  # raises json.JSONDecodeError on malformed output
        return content

    def __call__(self, *, prompt: str, role: str, model: str, temperature: float) -> str:
        # Sequential-only: one request in flight at a time, no threading/async fan-out.
        effective_temperature = self.temperatures.get(role, temperature)
        try:
            return self._request(prompt, effective_temperature)
        except (ValueError, json.JSONDecodeError, KeyError, TimeoutError):
            repair_prompt = (
                f"{prompt}\n\nYour previous response was not valid JSON. "
                "Reply with ONLY a single valid JSON object, no prose, no markdown fences."
            )
            try:
                return self._request(repair_prompt, effective_temperature)
            except (ValueError, json.JSONDecodeError, KeyError, TimeoutError) as second_error:
                # A failed generation must stay failed: never return unparsed/partial content.
                raise RuntimeError(
                    f"Ollama backend failed for role={role!r} model={self.model!r} "
                    f"after one repair retry: {second_error}"
                ) from second_error


def _prompt(name: str, payload: Any) -> str:
    return PROMPTS.joinpath(f"{name}.md").read_text(encoding="utf-8") + "\n\nINPUT:\n" + json.dumps(payload)


def _invoke(backend: Backend, role: str, payload: Any) -> Any:
    raw = backend(prompt=_prompt(role, payload), role=role, model=MODEL, temperature=TEMPERATURES[role])
    return json.loads(raw) if isinstance(raw, str) else raw


def run_analyst(backend: Backend, diagnostics: dict[str, Any]) -> AnalystReport:
    return AnalystReport.model_validate(_invoke(backend, "analyst", diagnostics))


def run_scientist(backend: Backend, analyst: AnalystReport, archive: list[dict[str, Any]]) -> ScientistHypothesis:
    return ScientistHypothesis.model_validate(_invoke(backend, "scientist", {"analyst": analyst.model_dump(), "archive": archive}))


def run_synthesizer(backend: Backend, scientist: ScientistHypothesis, revision_context: dict[str, Any] | None = None) -> Policy:
    # Invalid LLM output remains invalid; callers receive the validation exception.
    if revision_context is not None:
        payload = {
            "mode": "revision",
            "original_hypothesis": scientist.model_dump(),
            "original_policy": revision_context["original_policy"],
            "verification_failures": revision_context["verification_failures"],
            "executed_counterexamples": revision_context["executed_counterexamples"],
            "development_behavior": revision_context["development_behavior"],
            "critic_failure_class": revision_context["critic_failure_class"],
            "revision_instruction": revision_context["revision_instruction"],
            "invariants": revision_context.get("invariants", scientist.invariants),
        }
    else:
        payload = scientist.model_dump()
    return parse_policy(_invoke(backend, "synthesizer", payload))


def run_counterexample_agent(backend: Backend, policy: Policy, scientist: ScientistHypothesis) -> CounterexamplePlan:
    return CounterexamplePlan.model_validate(_invoke(backend, "counterexample", {"policy": policy, "hypothesis": scientist.model_dump()}))


def run_critic(backend: Backend, evidence: dict[str, Any]) -> CriticReport:
    report = CriticReport.model_validate(_invoke(backend, "critic", evidence))
    if report.decision not in {"REJECT", "RETAIN", "REVISE_ONCE"}:
        raise ValueError("critic decision must be REJECT, RETAIN, or REVISE_ONCE")
    return report


def discovery_loop(backend: Backend, diagnostics: dict[str, Any], archive: list[dict[str, Any]],
                   deterministic_evaluate: Callable[[Policy, CounterexamplePlan], dict[str, Any]]) -> dict[str, Any]:
    """Run initial synthesis and, only when requested, exactly one focused, evidence-grounded revision."""
    analyst = run_analyst(backend, diagnostics)
    scientist = run_scientist(backend, analyst, archive)
    policy = run_synthesizer(backend, scientist)
    challenges = run_counterexample_agent(backend, policy, scientist)
    evidence = deterministic_evaluate(policy, challenges)
    critic = run_critic(backend, evidence)
    revised = False
    lineage: dict[str, Any] | None = None
    if critic.decision == "REVISE_ONCE":
        revised = True
        parent_policy_id = policy_hash(policy)
        revision_context = {
            "original_policy": policy,
            "verification_failures": evidence.get("failures", evidence) if isinstance(evidence, dict) else evidence,
            "executed_counterexamples": [c.model_dump() for c in challenges.challenges],
            "development_behavior": evidence,
            "critic_failure_class": critic.failure_class,
            "revision_instruction": critic.revision_instruction,
            "invariants": scientist.invariants,
        }
        policy = run_synthesizer(backend, scientist, revision_context=revision_context)
        lineage = {
            "parent_policy_id": parent_policy_id,
            "revision_reason": critic.failure_class,
            "counterexample_ids": [c.type for c in challenges.challenges],
            "critic_instruction": critic.revision_instruction,
        }
        # Re-verify exactly once: fresh counterexamples, fresh evaluation, fresh critic pass.
        challenges = run_counterexample_agent(backend, policy, scientist)
        evidence = deterministic_evaluate(policy, challenges)
        critic = run_critic(backend, evidence)
    result = {"policy": policy, "analyst": analyst, "scientist": scientist, "challenges": challenges,
              "evidence": evidence, "critic": critic, "revised_once": revised}
    if lineage is not None:
        result["lineage"] = lineage
    return result
