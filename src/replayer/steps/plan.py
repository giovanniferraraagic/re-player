"""Planning step - turns a chosen flow into a spec a human can review.

The spec is the supervision interface: it has to be executable by a person who
never opens the generated code. Steps whose action or expected result is empty
are dropped rather than written out, because a step you cannot check is worse
than no step at all.
"""

from __future__ import annotations

import json

from replayer.config import WorkflowConfig
from replayer.models import invoke_model
from replayer.specfile import write_spec
from replayer.state import RunState, SpecStep

PROMPT_TEMPLATE = """Write a manual test specification for one user journey.

Application under test: {url}
Journey: {flow}
Known journey steps:
{flow_steps}

Elements available on the page:
{elements}

Rules:
- Between 2 and 6 steps.
- Every step needs one concrete action and one observable expected result.
- The expected result must be something a tester can see on screen.
- State any precondition or test data inside the action text.
- Do not mention code, selectors or automation.

Reply with a single JSON object:
{{"title": "...", "description": "...",
  "steps": [{{"action": "...", "expected": "..."}}]}}
"""


def _render_elements(state: RunState, limit: int = 30) -> str:
    if not state.snapshots:
        return "(none captured)"
    lines = []
    for node in state.snapshots[-1][:limit]:
        if node.name:
            lines.append(f'- {node.role} "{node.name}"')
    return "\n".join(lines) or "(none named)"


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
    """Populate the spec fields on ``state`` and write the spec artifact."""
    flow = state.flows[0] if state.flows else None
    prompt = PROMPT_TEMPLATE.format(
        url=state.url,
        flow=flow.title if flow else "(no flow discovered)",
        flow_steps="\n".join(f"- {s}" for s in flow.steps) if flow else "- (none)",
        elements=_render_elements(state),
    )
    response = await invoke_model(step="plan", config=config, prompt=prompt, state=state)
    title, description, steps = parse_spec(response.text)

    state.spec_title = title or (flow.title if flow else "Untitled flow")
    state.spec_description = description
    state.spec_steps = steps
    write_spec(state, config.artifacts_dir)
