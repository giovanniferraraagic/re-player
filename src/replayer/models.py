"""The single choke point for every language-model call in the harness.

Nothing else in the codebase may talk to a model. That constraint is what makes
"these four executors cost zero tokens" a checkable claim rather than a promise:
every invocation is recorded here together with the step that made it, so a test
can assert that no code-only step ever appears in the record.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
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
    "generate": {
        "test_source": (
            "import { test, expect } from '@playwright/test';\n\n"
            "test('stubbed journey', async ({ page }) => {\n"
            "  await page.goto('./');\n\n"
            "  await test.step('Open the application', async () => {\n"
            "    await expect(page).toHaveURL(/.*/);\n"
            "  });\n\n"
            "  await test.step('Add a todo', async () => {\n"
            "    await expect(page).toHaveURL(/.*/);\n"
            "  });\n"
            "});\n"
        )
    },
}


class AzureOpenAIChatClient:
    """Azure OpenAI backing for the LLM steps.

    Deliberately thin: the harness only needs "prompt in, text and usage out".
    Keeping the surface this small is what lets any provider be swapped in
    without touching the workflow.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
    ) -> None:
        import os

        self._endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self._api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self._api_version = (
            api_version or os.environ.get("AZURE_OPENAI_API_VERSION") or "2024-10-21"
        )
        if not self._endpoint or not self._api_key:
            raise RuntimeError(
                "Azure OpenAI is not configured: set AZURE_OPENAI_ENDPOINT and "
                "AZURE_OPENAI_API_KEY (a .env file at the repository root works)"
            )
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            from openai import AsyncAzureOpenAI

            self._client = AsyncAzureOpenAI(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
            )
        return self._client

    async def complete(
        self, *, step: str, model: str, provider: str, prompt: str
    ) -> ModelResponse:
        client = self._ensure_client()
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a meticulous QA engineer. Reply with a single "
                        "JSON object and nothing else."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        usage = response.usage
        return ModelResponse(
            text=response.choices[0].message.content or "",
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


class RecordingModelClient:
    """Wraps another client and appends every exchange to a JSONL file."""

    def __init__(self, inner: ModelClient, path: str) -> None:
        self._inner = inner
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text("", encoding="utf-8")

    async def complete(
        self, *, step: str, model: str, provider: str, prompt: str
    ) -> ModelResponse:
        response = await self._inner.complete(
            step=step, model=model, provider=provider, prompt=prompt
        )
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "step": step,
                        "text": response.text,
                        "input_tokens": response.input_tokens,
                        "output_tokens": response.output_tokens,
                    }
                )
                + "\n"
            )
        return response


class ReplayModelClient:
    """Replays a recorded transcript instead of calling a provider.

    Replay is per step and in order, so a run replayed from a recording takes
    exactly the same decisions as the original. This is what makes
    "reproducible" a checkable property rather than a slogan: the graph fixes
    the order of steps, and the recording fixes what the model said inside them.
    """

    def __init__(self, path: str) -> None:
        self._queues: dict[str, list[ModelResponse]] = {}
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            self._queues.setdefault(entry["step"], []).append(
                ModelResponse(
                    text=entry["text"],
                    input_tokens=entry.get("input_tokens", 0),
                    output_tokens=entry.get("output_tokens", 0),
                )
            )
        self._cursors: dict[str, int] = {}

    async def complete(
        self, *, step: str, model: str, provider: str, prompt: str
    ) -> ModelResponse:
        queue = self._queues.get(step, [])
        index = self._cursors.get(step, 0)
        if index >= len(queue):
            raise RuntimeError(
                f"recording exhausted for step {step!r}: the replayed run asked "
                f"for call {index + 1} but only {len(queue)} were recorded"
            )
        self._cursors[step] = index + 1
        return queue[index]


def client_for(config: WorkflowConfig) -> ModelClient:
    """Pick the client for this run, building it at most once.

    The cache matters: ``client_for`` is consulted on every model call, and a
    recording client rebuilt each time would truncate its own transcript,
    leaving a recording that only ever held the final exchange.
    """
    if config.client is not None:
        return config.client  # type: ignore[return-value]

    if config.replay_path:
        client: ModelClient = ReplayModelClient(config.replay_path)
    else:
        if config.stub_llm or config.dry_run:
            base: ModelClient = StubModelClient()
        else:
            providers = {binding.provider for binding in config.models.values()}
            if providers <= {"azure"}:
                base = AzureOpenAIChatClient()
            else:
                raise NotImplementedError(
                    f"No client wired for provider(s) {sorted(providers)}; "
                    "set REPLAYER_PROVIDER=azure or REPLAYER_STUB_LLM=1"
                )
        client = (
            RecordingModelClient(base, config.record_path)
            if config.record_path
            else base
        )

    config.client = client
    return client


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
