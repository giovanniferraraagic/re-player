"""The generated test is executed once, and a failed run still reports.

Two claims that were previously untrue:

* `generate` verifies its output by running it and `run` ran it again, so every
  successful workflow paid for two full Playwright executions and the second
  result silently overwrote the first.
* generation failure raised, which skipped `run` *and* `report`, so the run that
  most needed a report produced none.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from replayer.config import WorkflowConfig
from replayer.driver import CommandResult
from replayer.state import RunState, SnapshotNode
from replayer.workflow import execute

SNAPSHOT = [
    SnapshotNode(role="textbox", name="What needs to be done?", ref="e3", depth=1),
    SnapshotNode(role="heading", name="todos", ref="e2", depth=1),
]


class _FakeDriver:
    """A browser stand-in: the point of these tests is the graph, not the page."""

    def __init__(self, session_name: str) -> None:
        self.session_name = session_name

    def __enter__(self) -> "_FakeDriver":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def open(self, url: str) -> CommandResult:
        return CommandResult("", 0, [], None, url, "Fake", None)

    def snapshot(self, depth: int | None = None) -> list[SnapshotNode]:
        return list(SNAPSHOT)


@pytest.fixture
def workflow_config(tmp_path: Path) -> WorkflowConfig:
    config = WorkflowConfig.from_env(
        url="https://example.test/",
        session="single-exec",
        stub_llm=True,
        dry_run=False,
    )
    config.artifacts_dir = str(tmp_path / "artifacts")
    config.checkpoint_dir = str(tmp_path / "checkpoints")
    config.generated_tests_dir = str(tmp_path / "generated")
    config.max_explore_steps = 1
    return config


@pytest.fixture(autouse=True)
def fake_browser(monkeypatch):
    monkeypatch.setattr("replayer.driver.PlaywrightCliDriver", _FakeDriver)
    monkeypatch.setattr("replayer.steps.explore.PlaywrightCliDriver", _FakeDriver)


def _counting_run(calls: list[str], passed: bool):
    def _run(state: RunState, config: WorkflowConfig) -> bool:
        calls.append(state.test_path or "?")
        state.test_passed = passed
        state.test_report = (
            {"stats": {"expected": 1, "unexpected": 0}}
            if passed
            else {
                "suites": [
                    {
                        "specs": [
                            {
                                "tests": [
                                    {
                                        "results": [
                                            {
                                                "status": "failed",
                                                "error": {
                                                    "message": "expect(x).toBe(y)"
                                                },
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
        return passed

    return _run


async def test_a_passing_test_is_executed_exactly_once(
    workflow_config: WorkflowConfig, monkeypatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("replayer.runner.run_playwright", _counting_run(calls, True))

    state = await execute(workflow_config)

    assert state.test_passed is True
    assert len(calls) == 1, f"the test was executed {len(calls)} times, expected once"


async def test_the_workflow_still_reports_when_generation_escalates(
    workflow_config: WorkflowConfig, monkeypatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr("replayer.runner.run_playwright", _counting_run(calls, False))

    state = await execute(workflow_config)

    # The escalating failure is not retried, and `run` does not re-execute it.
    assert len(calls) == 1
    assert state.escalations
    assert state.generation_error
    assert state.test_passed is False

    assert state.report_path, "a failed run must still produce a report"
    payload = json.loads(Path(state.report_path).read_text(encoding="utf-8"))
    assert payload["test_passed"] is False
    assert payload["escalations"] == state.escalations
    assert payload["generation_error"]


async def test_every_executor_still_runs_when_generation_fails(
    workflow_config: WorkflowConfig, monkeypatch
) -> None:
    """A raise used to skip `run` and `report`; escalation must not."""
    from replayer.config import EXECUTOR_SEQUENCE

    monkeypatch.setattr("replayer.runner.run_playwright", _counting_run([], False))

    state = await execute(workflow_config)

    assert set(state.usage) == set(EXECUTOR_SEQUENCE)
