"""Generation step - emits the TypeScript Playwright test.

Task 4 wires the step through the model choke point using canned responses;
Task 7 replaces the prompt and enforces catalog-only locators.
"""

from __future__ import annotations

import json

from replayer.config import WorkflowConfig
from replayer.models import invoke_model
from replayer.state import RunState

PROMPT_TEMPLATE = """Write a Playwright test in TypeScript for this specification.

Specification: {title}
Steps:
{steps}

You may ONLY use locators from this catalog:
{catalog}

Reply with JSON: {{"test_source": str}}
"""


def _render_steps(state: RunState) -> str:
    return "\n".join(
        f"{step.index}. {step.action} -> {step.expected}" for step in state.spec_steps
    )


def _render_catalog(state: RunState) -> str:
    return "\n".join(f"- {entry.expression}" for entry in state.catalog)


def parse_test_source(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    source = payload.get("test_source")
    return source if isinstance(source, str) else ""


async def run_generate(state: RunState, config: WorkflowConfig) -> None:
    """Populate ``state.test_source``."""
    prompt = PROMPT_TEMPLATE.format(
        title=state.spec_title,
        steps=_render_steps(state),
        catalog=_render_catalog(state),
    )
    response = await invoke_model(
        step="generate", config=config, prompt=prompt, state=state
    )
    state.test_source = parse_test_source(response.text)
