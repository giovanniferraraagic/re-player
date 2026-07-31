"""Planning step - turns a chosen flow into a readable spec.

Task 4 wires the step through the model choke point using canned responses;
Task 6 replaces the prompt and writes the spec artifact.
"""

from __future__ import annotations

import json

from replayer.config import WorkflowConfig
from replayer.models import invoke_model
from replayer.state import RunState, SpecStep

PROMPT_TEMPLATE = """Write a manual test specification for this user journey.

Application: {url}
Flow: {flow}

Reply with JSON: {{"title": str, "description": str,
"steps": [{{"action": str, "expected": str}}]}}
Every step needs a concrete action and an observable expected result.
"""


def parse_spec(text: str) -> tuple[str, str, list[SpecStep]]:
    """Read a spec out of a model response, ignoring unknown fields."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "", "", []
    if not isinstance(payload, dict):
        return "", "", []

    title = str(payload.get("title", "")).strip()
    description = str(payload.get("description", "")).strip()

    steps: list[SpecStep] = []
    raw_steps = payload.get("steps")
    if isinstance(raw_steps, list):
        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).strip()
            expected = str(item.get("expected", "")).strip()
            if not action or not expected:
                continue
            steps.append(
                SpecStep(index=len(steps) + 1, action=action, expected=expected)
            )
    return title, description, steps


async def run_plan(state: RunState, config: WorkflowConfig) -> None:
    """Populate the spec fields on ``state``."""
    flow = state.flows[0] if state.flows else None
    prompt = PROMPT_TEMPLATE.format(
        url=state.url,
        flow=flow.title if flow else "(no flow discovered)",
    )
    response = await invoke_model(step="plan", config=config, prompt=prompt, state=state)
    title, description, steps = parse_spec(response.text)
    state.spec_title = title or (flow.title if flow else "Untitled flow")
    state.spec_description = description
    state.spec_steps = steps
