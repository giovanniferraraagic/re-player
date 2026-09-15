"""The generator may repair locators, but must never repair assertions.

`AGENTS.md` constraint 4 and the tier table in `docs/research/README.md` both say
a failed assertion or a server error escalates rather than being repaired.
Retrying those would push the model toward an expectation that accommodates a
real defect, which is how an application bug silently becomes a green test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from replayer.config import WorkflowConfig
from replayer.models import RECORDER
from replayer.runner import (
    ASSERTION,
    HARNESS,
    LOCATOR,
    UNKNOWN,
    classify_failure,
    classify_failures,
)
from replayer.state import RunState, SpecStep
from replayer.steps.generate import MAX_ATTEMPTS, run_generate

# --------------------------------------------------------------------------- #
# Classification.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "message",
    [
        "Error: expect(received).toHaveText(expected)\nExpected: 'a'\nReceived: 'b'",
        "expect(locator).toBeVisible() failed",
        "expect.soft(page).toHaveURL(expected)",
    ],
)
def test_assertion_failures_are_classified_as_assertions(message: str) -> None:
    assert classify_failure(message) == ASSERTION


@pytest.mark.parametrize(
    "message",
    [
        "locator.click: Error: strict mode violation: resolved to 2 elements",
        "locator.click: Timeout 30000ms exceeded.\n=========== waiting for getByRole('button')",
        "Timeout 30000ms exceeded.\n=========== waiting for locator('button')",
        "Failed to resolve locator against the page",
    ],
)
def test_locator_failures_are_classified_as_locator(message: str) -> None:
    assert classify_failure(message) == LOCATOR


def test_an_assertion_that_timed_out_on_a_locator_still_escalates() -> None:
    """The fail-safe direction: expect() outranks the locator markers.

    A timeout inside expect() still encodes an expected state, so treating it as
    a repairable locator problem is the one mistake here that fails silently.
    """
    message = (
        "Error: expect(locator).toBeVisible() failed\n"
        "Timeout 5000ms exceeded.\n=========== waiting for locator('.todo')"
    )
    assert classify_failure(message) == ASSERTION


@pytest.mark.parametrize("message", ["", "   ", "something entirely unfamiliar"])
def test_unrecognised_failures_escalate(message: str) -> None:
    assert classify_failure(message) == UNKNOWN


def test_only_locator_failures_are_repairable() -> None:
    report = {
        "suites": [
            {
                "specs": [
                    {
                        "tests": [
                            {
                                "results": [
                                    {
                                        "status": "failed",
                                        "error": {"message": "strict mode violation"},
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    failures = classify_failures(report)
    assert [failure.kind for failure in failures] == [LOCATOR]
    assert all(failure.repairable for failure in failures)


def test_a_harness_error_is_a_failure_that_escalates() -> None:
    failures = classify_failures({"harness_error": "playwright exited 1"})
    assert [failure.kind for failure in failures] == [HARNESS]
    assert not failures[0].repairable


def test_an_empty_failure_list_escalates_unknown() -> None:
    report = {"stats": {"unexpected": 1}, "suites": [{"specs": [{"tests": [{"results": [{"status": "skipped"}]}]}]}]}
    failures = classify_failures(report)
    assert failures == []


def test_passed_results_are_not_failures() -> None:
    report = {
        "suites": [{"specs": [{"tests": [{"results": [{"status": "passed"}]}]}]}]
    }
    assert classify_failures(report) == []


def test_skipped_results_are_not_failures() -> None:
    """A test that never ran is not a failure, and must not become an escalation."""
    report = {
        "suites": [{"specs": [{"tests": [{"results": [{"status": "skipped"}]}]}]}]
    }
    assert classify_failures(report) == []


# --------------------------------------------------------------------------- #
# The generator's retry policy.
# --------------------------------------------------------------------------- #


def _state() -> RunState:
    """A state whose spec matches the two steps of the stubbed generator reply."""
    state = RunState(url="https://example.test/", session="triage")
    state.spec_title = "Add a todo"
    state.spec_steps = [
        SpecStep(index=1, action="Open the application", expected="The field shows"),
        SpecStep(index=2, action="Add a todo", expected="It appears in the list"),
    ]
    return state


def _config(tmp_path: Path) -> WorkflowConfig:
    config = WorkflowConfig.from_env(
        url="https://example.test/", session="triage", stub_llm=True, dry_run=False
    )
    config.artifacts_dir = str(tmp_path / "artifacts")
    config.generated_tests_dir = str(tmp_path / "generated")
    return config


def _failing_run(message: str):
    """A stand-in for run_playwright that always fails with ``message``."""

    def _run(state: RunState, config: WorkflowConfig) -> bool:
        state.test_passed = False
        state.test_report = {
            "suites": [
                {
                    "specs": [
                        {
                            "tests": [
                                {
                                    "results": [
                                        {
                                            "status": "failed",
                                            "error": {"message": message},
                                        }
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return False

    return _run


async def test_an_assertion_failure_stops_the_loop_and_escalates(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "replayer.runner.run_playwright",
        _failing_run("Error: expect(locator).toHaveText(expected)"),
    )
    RECORDER.clear()
    state = _state()

    await run_generate(state, _config(tmp_path))

    assert state.escalations, "an assertion failure must be escalated"
    assert state.escalations[0].startswith(ASSERTION)
    assert state.generation_error
    assert len(RECORDER.invocations) == 1, (
        "the generator must not ask the model to repair a failed assertion"
    )


async def test_a_harness_error_stops_the_loop_and_escalates(
    tmp_path: Path, monkeypatch
) -> None:
    def _run(state: RunState, config: WorkflowConfig) -> bool:
        state.test_passed = False
        state.test_report = {"stats": {}, "harness_error": "playwright exited 1"}
        return False

    monkeypatch.setattr("replayer.runner.run_playwright", _run)
    RECORDER.clear()
    state = _state()

    await run_generate(state, _config(tmp_path))

    assert state.escalations
    assert state.escalations[0].startswith(HARNESS)
    assert len(RECORDER.invocations) == 1


async def test_no_per_test_failures_escalates_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    def _run(state: RunState, config: WorkflowConfig) -> bool:
        state.test_passed = False
        state.test_report = {"stats": {"skipped": 2}}
        return False

    monkeypatch.setattr("replayer.runner.run_playwright", _run)
    state = _state()

    await run_generate(state, _config(tmp_path))

    assert state.escalations
    assert state.escalations[0].startswith(UNKNOWN)
    assert state.generation_error


async def test_a_locator_failure_is_still_repaired(
    tmp_path: Path, monkeypatch
) -> None:
    """Locator repair is explicitly allowed, so the loop must still retry."""
    monkeypatch.setattr(
        "replayer.runner.run_playwright",
        _failing_run("locator.click: Error: strict mode violation"),
    )
    RECORDER.clear()
    state = _state()

    await run_generate(state, _config(tmp_path))

    assert not state.escalations, "a locator failure must not escalate"
    assert state.generation_error, "exhausting the attempts is still a failure"
    assert len(RECORDER.invocations) == MAX_ATTEMPTS


async def test_exhaustion_leaves_an_unambiguous_verdict(
    tmp_path: Path, monkeypatch
) -> None:
    """The artifact left on disk may never have been executed.

    So the state must not carry a report describing some earlier attempt's
    source, and `run` must not be left to re-execute a known-bad test.
    """
    monkeypatch.setattr(
        "replayer.runner.run_playwright",
        _failing_run("locator.click: Error: strict mode violation"),
    )
    state = _state()

    await run_generate(state, _config(tmp_path))

    assert state.test_passed is False, "the verdict must be explicit, not None"
    assert state.test_report == {}, "a stale report describes the wrong file"


async def test_generation_failure_does_not_raise(tmp_path: Path, monkeypatch) -> None:
    """The workflow must reach `report`; a raise would skip it entirely."""
    monkeypatch.setattr(
        "replayer.runner.run_playwright",
        _failing_run("Error: expect(page).toHaveURL(expected)"),
    )
    state = _state()

    await run_generate(state, _config(tmp_path))

    assert state.test_source, "the last attempt is kept so it can be inspected"
    assert Path(state.test_path).exists()
