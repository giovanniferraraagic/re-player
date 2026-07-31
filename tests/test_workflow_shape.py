"""Task 4 checks: the graph decides the order, and code steps never spend tokens.

These assertions are the heart of the project's claim, so they are written to
fail if the claim stops being true. An earlier version of this file asserted the
executor order from a stubbed run, which an adversarial reviewer correctly
called theatre: a deterministic stub produces a stable order even if the graph
were model-routed. The checks below instead (a) inspect the graph topology
without running anything, (b) run a deliberately hostile model that tries to
reroute the workflow, and (c) prove model calls are impossible from code-only
steps.
"""

from __future__ import annotations

import json

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from replayer.config import (
    CODE_ONLY_STEPS,
    EXECUTOR_SEQUENCE,
    LLM_STEPS,
    WorkflowConfig,
)
from replayer.models import (
    RECORDER,
    ModelCallFromCodeStepError,
    ModelResponse,
    invoke_model,
)
from replayer.workflow import build_workflow, execute

EXECUTOR_SPAN_PREFIX = "executor.process "
GENAI_SPAN_MARKERS = ("chat", "text_completion", "execute_tool", "invoke_agent")

EXPECTED_EDGES = {
    ("bootstrap", "explore"),
    ("explore", "catalog"),
    ("catalog", "plan"),
    ("plan", "generate"),
    ("generate", "run"),
    ("run", "report"),
}


def _config(tmp_path) -> WorkflowConfig:
    config = WorkflowConfig.from_env(
        url="https://demo.playwright.dev/todomvc/",
        session="replayer-shape",
        stub_llm=True,
        dry_run=True,
    )
    config.artifacts_dir = str(tmp_path / "artifacts")
    config.checkpoint_dir = str(tmp_path / "checkpoints")
    return config


# --------------------------------------------------------------------------- #
# Structural proof: no run required, so no stub can flatter the result.
# --------------------------------------------------------------------------- #


def test_graph_topology_is_a_fixed_linear_chain(tmp_path) -> None:
    """The declared graph is the chain, independent of any model output."""
    workflow = build_workflow(_config(tmp_path))

    assert workflow.start_executor_id == "bootstrap"
    assert set(workflow.executors) == set(EXECUTOR_SEQUENCE)

    edges = {
        (group.source_executor_ids[0], group.target_executor_ids[0])
        for group in workflow.edge_groups
        if type(group).__name__ == "SingleEdgeGroup"
    }
    assert edges == EXPECTED_EDGES


def test_no_executor_has_more_than_one_outgoing_edge(tmp_path) -> None:
    """With one successor each, there is no branch a model could choose."""
    workflow = build_workflow(_config(tmp_path))

    outgoing: dict[str, int] = {}
    for group in workflow.edge_groups:
        if type(group).__name__ != "SingleEdgeGroup":
            continue
        source = group.source_executor_ids[0]
        outgoing[source] = outgoing.get(source, 0) + 1

    assert outgoing, "expected at least one edge"
    assert max(outgoing.values()) == 1, f"branching found: {outgoing}"


def test_graph_signature_is_stable_across_builds(tmp_path) -> None:
    """Two builds of the same config describe the same graph."""
    first = build_workflow(_config(tmp_path))
    second = build_workflow(_config(tmp_path))
    assert first.graph_signature_hash == second.graph_signature_hash


# --------------------------------------------------------------------------- #
# Behavioural proof: a hostile model must not be able to change the order.
# --------------------------------------------------------------------------- #


class RogueModelClient:
    """Returns well-formed payloads laced with routing instructions.

    If the workflow honoured anything a model said about control flow, these
    directives would skip or reorder steps and the sequence assertion would
    fail.
    """

    async def complete(self, *, step, model, provider, prompt) -> ModelResponse:
        sabotage = {
            "next_step": "report",
            "skip": ["catalog", "generate", "run"],
            "goto": "report",
            "terminate": True,
        }
        if step == "explore":
            payload = {
                "flows": [{"title": "Rogue flow", "rationale": "", "steps": []}],
                **sabotage,
            }
        elif step == "plan":
            payload = {
                "title": "Rogue plan",
                "description": "",
                "steps": [{"action": "a", "expected": "b"}],
                **sabotage,
            }
        else:
            payload = {"test_source": "// rogue", **sabotage}
        return ModelResponse(text=json.dumps(payload), input_tokens=7, output_tokens=11)


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    from agent_framework.observability import enable_instrumentation

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    enable_instrumentation()
    return exporter


def _executor_order(spans) -> list[str]:
    executor_spans = [s for s in spans if s.name.startswith(EXECUTOR_SPAN_PREFIX)]
    executor_spans.sort(key=lambda s: s.start_time)
    return [s.name[len(EXECUTOR_SPAN_PREFIX) :] for s in executor_spans]


async def test_rogue_model_cannot_reroute_the_workflow(
    span_exporter, tmp_path, monkeypatch
) -> None:
    """Every executor still runs, in order, while the model demands otherwise."""
    monkeypatch.setattr("replayer.models.client_for", lambda config: RogueModelClient())
    RECORDER.clear()
    span_exporter.clear()

    state = await execute(_config(tmp_path))

    assert _executor_order(span_exporter.get_finished_spans()) == list(EXECUTOR_SEQUENCE)
    assert state.flows[0].title == "Rogue flow", "the rogue client was not used"


# --------------------------------------------------------------------------- #
# Cost proof: model calls are recorded, and code-only steps cannot make them.
# --------------------------------------------------------------------------- #


async def test_model_calls_come_only_from_llm_steps(tmp_path) -> None:
    """The recorder proves who spent tokens - not the absence of a provider."""
    RECORDER.clear()
    state = await execute(_config(tmp_path))

    called = RECORDER.steps()
    assert called == set(LLM_STEPS), f"unexpected set of model callers: {called}"
    assert not called & set(CODE_ONLY_STEPS)

    for step in CODE_ONLY_STEPS:
        assert state.tokens_for(step) == 0, f"{step} spent tokens"
    for step in LLM_STEPS:
        assert state.tokens_for(step) > 0, f"{step} recorded no token usage"


async def test_code_only_steps_are_refused_at_the_choke_point(tmp_path) -> None:
    """Even a deliberate attempt to call a model from a code step is blocked."""
    config = _config(tmp_path)
    for step in CODE_ONLY_STEPS:
        with pytest.raises(ModelCallFromCodeStepError):
            await invoke_model(step=step, config=config, prompt="x")


async def test_no_genai_spans_in_a_code_only_run(span_exporter, tmp_path) -> None:
    RECORDER.clear()
    span_exporter.clear()
    await execute(_config(tmp_path))

    genai = [
        s.name
        for s in span_exporter.get_finished_spans()
        if any(s.name.startswith(marker) for marker in GENAI_SPAN_MARKERS)
    ]
    assert genai == [], f"Unexpected model-invocation spans: {genai}"


async def test_every_executor_recorded_usage(tmp_path) -> None:
    """Cost attribution covers the whole graph, not just the model steps."""
    RECORDER.clear()
    state = await execute(_config(tmp_path))
    assert set(state.usage) == set(EXECUTOR_SEQUENCE)
