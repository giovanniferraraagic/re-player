"""The single choke point for every language-model call in the harness.

Nothing else in the codebase may talk to a model. That constraint is what makes
"these four executors cost zero tokens" a checkable claim rather than a promise:
every invocation is recorded here together with the step that made it, so a test
can assert that no code-only step ever appears in the record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from replayer.config import CODE_ONLY_STEPS, WorkflowConfig
from replayer.state import RunState


class ModelCallFromCodeStepError(RuntimeError):
    """Raised when a code-only executor tries to invoke a model."""


@dataclass(frozen=True)
class ModelResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ModelInvocation:
    step: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int


class ModelClient(Protocol):
    async def complete(
        self, *, step: str, model: str, provider: str, prompt: str
    ) -> ModelResponse: ...


@dataclass
class InvocationRecorder:
    """In-memory ledger of every model call made during a run."""

    invocations: list[ModelInvocation] = field(default_factory=list)

    def record(self, invocation: ModelInvocation) -> None:
        self.invocations.append(invocation)

    def steps(self) -> set[str]:
        return {invocation.step for invocation in self.invocations}

    def clear(self) -> None:
        self.invocations.clear()


#: Process-wide recorder. Tests read it; production code only appends to it.
RECORDER = InvocationRecorder()


class StubModelClient:
    """Deterministic stand-in used when no real provider is configured.

    It returns canned, well-formed answers so the pipeline can be exercised
    end to end, and reports non-zero token usage so cost attribution is
    exercised too.
    """

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self._responses = responses or {}

    async def complete(
        self, *, step: str, model: str, provider: str, prompt: str
    ) -> ModelResponse:
        payload = self._responses.get(step, DEFAULT_STUB_RESPONSES.get(step, {}))
        text = json.dumps(payload)
        return ModelResponse(
            text=text,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
        )


DEFAULT_STUB_RESPONSES: dict[str, Any] = {
    "explore": {
        "flows": [
            {
                "title": "Add a todo",
                "rationale": "The primary journey of a todo application.",
                "steps": [
                    "Open the application",
                    "Enter a todo title and press Enter",
                    "Confirm the todo appears in the list",
                ],
            }
        ]
    },
    "plan": {
        "title": "Add a todo",
        "description": "Adding a single todo to an empty list.",
        "steps": [
            {
                "action": "Open the application",
                "expected": "The new-todo field is visible",
            },
            {
                "action": "Enter 'Buy groceries' and press Enter",
                "expected": "'Buy groceries' appears in the todo list",
            },
        ],
    },
    "generate": {"test_source": ""},
}


def client_for(config: WorkflowConfig) -> ModelClient:
    """Pick the client for this run. Stub unless a real provider is wired up."""
    if config.stub_llm or config.dry_run:
        return StubModelClient()
    raise NotImplementedError(
        "No real model provider is configured yet; set REPLAYER_STUB_LLM=1 "
        "or wire a provider in replayer.models.client_for"
    )


async def invoke_model(
    *,
    step: str,
    config: WorkflowConfig,
    prompt: str,
    state: RunState | None = None,
    client: ModelClient | None = None,
) -> ModelResponse:
    """Call a model on behalf of ``step`` and record what it cost."""
    if step in CODE_ONLY_STEPS:
        raise ModelCallFromCodeStepError(
            f"{step!r} is declared code-only and must never invoke a model"
        )

    binding = config.model_for(step)
    model = binding.model if binding else "unknown"
    provider = binding.provider if binding else "unknown"

    active = client or client_for(config)
    response = await active.complete(
        step=step, model=model, provider=provider, prompt=prompt
    )

    RECORDER.record(
        ModelInvocation(
            step=step,
            model=model,
            provider=provider,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
    )
    if state is not None:
        state.record_usage(
            step,
            model=model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )
    return response
