"""Exploration step - drives the browser and decides what is worth testing.

The model is given a deliberately small view of the page and asked for one
action at a time. Two properties matter and are enforced here rather than
hoped for:

* the interaction budget is a hard ceiling, not a suggestion to the model;
* an action is only executed if its element reference actually exists in the
  snapshot the model was shown, so a hallucinated reference can never reach
  the browser.
"""

from __future__ import annotations

import json

from replayer.config import WorkflowConfig
from replayer.driver import PlaywrightCliDriver
from replayer.models import invoke_model
from replayer.state import ExploreAction, FlowCandidate, RunState, SnapshotNode

ACTIONABLE_KINDS = {"click", "fill", "check", "press"}

PROMPT_TEMPLATE = """You are a QA engineer exploring a web application to decide what to test.

URL: {url}
Interactions used: {used} of {budget}

Elements currently on the page:
{elements}

Actions already taken:
{history}

Choose ONE next interaction, or stop if you have seen enough.

Reply with a single JSON object:
{{"action": {{"kind": "click|fill|check|press|none",
              "ref": "<element ref such as e8, or null>",
              "text": "<text to type, or null>"}},
  "done": true|false,
  "flows": [{{"title": "...", "rationale": "...", "steps": ["..."]}}]}}

Put your candidate user journeys in "flows" whenever you set "done" to true.
Only use a "ref" that appears in the element list above.
"""


def describe_elements(snapshot: list[SnapshotNode], limit: int = 40) -> str:
    if not snapshot:
        return "(no elements captured)"
    lines: list[str] = []
    for node in snapshot[:limit]:
        if node.ref is None:
            continue
        name = f' "{node.name}"' if node.name else ""
        lines.append(f"- [{node.ref}] {node.role}{name}")
    return "\n".join(lines) or "(no referenceable elements)"


def _describe_history(state: RunState) -> str:
    if not state.explore_actions:
        return "(none yet)"
    executed = [
        f"- {action.kind} {action.ref or ''} {action.text or ''}".rstrip()
        for action in state.explore_actions
        if action.executed
    ]
    return "\n".join(executed) if executed else "(none executed)"


def parse_flows(payload: object) -> list[FlowCandidate]:
    """Read flow candidates, ignoring anything the model invents beyond them."""
    if not isinstance(payload, list):
        return []
    flows: list[FlowCandidate] = []
    for item in payload:
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
                steps=[str(step) for step in steps] if isinstance(steps, list) else [],
            )
        )
    return flows


def _parse_turn(text: str) -> tuple[dict, bool, list[FlowCandidate]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}, True, []
    if not isinstance(payload, dict):
        return {}, True, []
    action = payload.get("action")
    return (
        action if isinstance(action, dict) else {},
        bool(payload.get("done", False)),
        parse_flows(payload.get("flows")),
    )


def _apply(driver: PlaywrightCliDriver, action: ExploreAction, state: RunState) -> None:
    """Execute a validated action and capture what the browser reported."""
    if action.kind == "click":
        result = driver.click(action.ref)
    elif action.kind == "fill":
        result = driver.fill(action.ref, action.text or "", submit=True)
    elif action.kind == "check":
        result = driver.check(action.ref)
    elif action.kind == "press":
        result = driver.press(action.text or "Enter")
    else:
        return
    state.observed_code.extend(result.code_lines)
    action.executed = True


def _fallback_flow() -> list[FlowCandidate]:
    """Never leave the pipeline with nothing to plan against."""
    return [
        FlowCandidate(
            title="Primary interaction",
            rationale="Model returned no usable flow; falling back to a generic one.",
            steps=["Open the application", "Perform the main action"],
        )
    ]


async def run_explore(state: RunState, config: WorkflowConfig) -> None:
    """Explore the application and populate ``state.flows``."""
    if config.dry_run:
        await _explore_without_browser(state, config)
        return

    with PlaywrightCliDriver(config.session) as driver:
        driver.open(state.url)
        snapshot = driver.snapshot()
        state.snapshots.append(snapshot)

        flows: list[FlowCandidate] = []
        while state.explore_turns < config.max_explore_steps:
            state.explore_turns += 1
            prompt = PROMPT_TEMPLATE.format(
                url=state.url,
                used=state.explore_turns - 1,
                budget=config.max_explore_steps,
                elements=describe_elements(snapshot),
                history=_describe_history(state),
            )
            response = await invoke_model(
                step="explore", config=config, prompt=prompt, state=state
            )
            raw_action, done, turn_flows = _parse_turn(response.text)
            if turn_flows:
                flows = turn_flows

            kind = str(raw_action.get("kind", "none")).lower()
            raw_ref = raw_action.get("ref")
            ref = str(raw_ref) if isinstance(raw_ref, str) and raw_ref.strip() else None
            raw_text = raw_action.get("text")
            text = str(raw_text) if isinstance(raw_text, str) else None

            if kind in ACTIONABLE_KINDS:
                available = {node.ref for node in snapshot if node.ref}
                action = ExploreAction(
                    kind=kind,
                    ref=ref,
                    text=text,
                    ref_was_in_snapshot=(ref in available) if ref else kind == "press",
                )
                if action.ref_was_in_snapshot:
                    _apply(driver, action, state)
                    snapshot = driver.snapshot()
                    state.snapshots.append(snapshot)
                else:
                    action.rejection = (
                        f"ref {ref!r} was not in the snapshot shown to the model"
                    )
                state.explore_actions.append(action)

            if done:
                break

        state.flows = flows

    if not state.flows:
        state.flows = _fallback_flow()


async def _explore_without_browser(state: RunState, config: WorkflowConfig) -> None:
    """Single model turn with no browser, used by hermetic tests."""
    state.explore_turns = 1
    snapshot = state.snapshots[-1] if state.snapshots else []
    prompt = PROMPT_TEMPLATE.format(
        url=state.url,
        used=0,
        budget=config.max_explore_steps,
        elements=describe_elements(snapshot),
        history="(none yet)",
    )
    response = await invoke_model(
        step="explore", config=config, prompt=prompt, state=state
    )
    _, _, flows = _parse_turn(response.text)
    state.flows = flows or _fallback_flow()
