"""Exploration step - decides which user journey is worth testing.

Task 4 wires the step through the model choke point using canned responses;
Task 5 replaces the prompt and adds real browser-driven exploration.
"""

from __future__ import annotations

import json

from replayer.config import WorkflowConfig
from replayer.models import invoke_model
from replayer.state import FlowCandidate, RunState

PROMPT_TEMPLATE = """You are exploring a web application to decide what is worth testing.

URL: {url}

Visible elements:
{elements}

Reply with JSON: {{"flows": [{{"title": str, "rationale": str, "steps": [str]}}]}}
"""


def _describe_elements(state: RunState, limit: int = 40) -> str:
    if not state.snapshots:
        return "(no snapshot captured)"
    lines: list[str] = []
    for node in state.snapshots[-1][:limit]:
        name = f' "{node.name}"' if node.name else ""
        lines.append(f"- {node.role}{name} [{node.ref}]")
    return "\n".join(lines)


def parse_flows(text: str) -> list[FlowCandidate]:
    """Read flow candidates out of a model response, ignoring unknown fields."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    raw_flows = payload.get("flows") if isinstance(payload, dict) else None
    if not isinstance(raw_flows, list):
        return []

    flows: list[FlowCandidate] = []
    for item in raw_flows:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        steps = item.get("steps")
        flows.append(
            FlowCandidate(
                title=title.strip(),
                rationale=str(item.get("rationale", "")),
                steps=[str(s) for s in steps] if isinstance(steps, list) else [],
            )
        )
    return flows


async def run_explore(state: RunState, config: WorkflowConfig) -> None:
    """Populate ``state.flows`` with candidate user journeys."""
    prompt = PROMPT_TEMPLATE.format(url=state.url, elements=_describe_elements(state))
    response = await invoke_model(
        step="explore", config=config, prompt=prompt, state=state
    )
    state.flows = parse_flows(response.text)
