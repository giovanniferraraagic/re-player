"""Task 5 checks: exploration is grounded, bounded, and produces something usable.

This test spends real tokens against the configured provider, because the
Definition of Done is about behaviour with a real model - a stub could not tell
us whether a small model can explore usefully, which is the riskiest assumption
in the whole spec. The interaction budget is kept small to keep it cheap.
"""

from __future__ import annotations

import os

import pytest

from replayer.config import WorkflowConfig
from replayer.driver import PlaywrightCliDriver
from replayer.state import RunState
from replayer.steps.explore import describe_elements, parse_flows, run_explore

TARGET_URL = "https://demo.playwright.dev/todomvc/"
BUDGET = 4

requires_provider = pytest.mark.skipif(
    not os.environ.get("AZURE_OPENAI_API_KEY")
    and not os.environ.get("REPLAYER_ALLOW_LIVE_MODEL"),
    reason="no model provider configured",
)


@pytest.fixture(scope="module")
async def explored() -> RunState:
    from replayer.config import load_dotenv

    load_dotenv()
    config = WorkflowConfig.from_env(url=TARGET_URL, session="replayer-explore-test")
    config.max_explore_steps = BUDGET

    state = RunState(url=TARGET_URL, session=config.session)
    await run_explore(state, config)
    return state


# --------------------------------------------------------------------------- #
# Pure checks - no model, no browser.
# --------------------------------------------------------------------------- #


def test_parse_flows_ignores_malformed_entries() -> None:
    flows = parse_flows(
        [
            {"title": "Good flow", "rationale": "r", "steps": ["a"]},
            {"title": "   "},
            {"no_title": True},
            "not an object",
        ]
    )
    assert [flow.title for flow in flows] == ["Good flow"]


def test_describe_elements_omits_nodes_without_refs() -> None:
    from replayer.state import SnapshotNode

    described = describe_elements(
        [
            SnapshotNode(role="textbox", name="Search", ref="e1", depth=0),
            SnapshotNode(role="generic", name=None, ref=None, depth=1),
        ]
    )
    assert "[e1] textbox" in described
    assert "generic" not in described


# --------------------------------------------------------------------------- #
# Live checks - the Definition of Done.
# --------------------------------------------------------------------------- #


@requires_provider
async def test_explore_emits_at_least_one_flow(explored: RunState) -> None:
    assert explored.flows, "exploration produced no candidate flow"
    assert explored.flows[0].title.strip()


@requires_provider
async def test_interaction_budget_is_respected(explored: RunState) -> None:
    assert explored.explore_turns <= BUDGET, (
        f"used {explored.explore_turns} turns against a budget of {BUDGET}"
    )


@requires_provider
async def test_every_executed_action_used_a_ref_from_the_shown_snapshot(
    explored: RunState,
) -> None:
    """A hallucinated element reference must never reach the browser."""
    for action in explored.explore_actions:
        if action.executed:
            assert action.ref_was_in_snapshot, (
                f"executed {action.kind} on ref {action.ref!r}, "
                "which was not in the snapshot shown to the model"
            )


@requires_provider
async def test_exploration_captured_page_state(explored: RunState) -> None:
    assert explored.snapshots, "no snapshot captured during exploration"
    assert any(node.role == "textbox" for node in explored.snapshots[0])


@requires_provider
async def test_exploration_left_no_browser_session(explored: RunState) -> None:
    assert PlaywrightCliDriver.list_sessions() == []


@requires_provider
async def test_exploration_recorded_token_cost(explored: RunState) -> None:
    assert explored.tokens_for("explore") > 0
