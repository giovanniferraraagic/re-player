"""Test execution. Pure code - never calls a model."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from replayer.config import WorkflowConfig
from replayer.state import RunState

#: Failure classes. Only ``LOCATOR`` may be handed back to a model for repair.
LOCATOR = "locator"
ASSERTION = "assertion"
HARNESS = "harness"
UNKNOWN = "unknown"

_ASSERTION_RE = re.compile(r"\bexpect(?:\.\w+)?\s*\(")
_LOCATOR_MARKERS = (
    "strict mode violation",
    "waiting for locator",
    "failed to resolve locator",
)


@dataclass(frozen=True)
class TestFailure:
    """One failure from a Playwright run, classified for the retry policy."""

    message: str
    kind: str

    @property
    def repairable(self) -> bool:
        return self.kind == LOCATOR


def classify_failure(message: str) -> str:
    """Classify a Playwright failure message.

    ``expect(...)`` is tested first and deliberately outranks the locator
    markers. An assertion that timed out waiting for an element still encodes an
    expected state, and repairing it is precisely how a real application defect
    becomes a green test. Unrecognised messages escalate for the same reason:
    of the two ways to be wrong here, only guessing "repairable" fails silently.
    """
    text = message.strip()
    if not text:
        return UNKNOWN
    if _ASSERTION_RE.search(text):
        return ASSERTION
    lowered = text.lower()
    if any(marker in lowered for marker in _LOCATOR_MARKERS):
        return LOCATOR
    return UNKNOWN


def classify_failures(report: dict) -> list[TestFailure]:
    """Every failure in a Playwright JSON report, with its class.

    ``skipped`` is excluded alongside ``passed``: a test that never ran is not a
    failure, and surfacing it as one would put noise in front of the human who
    has to triage the escalations.
    """
    failures: list[TestFailure] = []
    harness_error = report.get("harness_error")
    if harness_error:
        failures.append(TestFailure(str(harness_error), HARNESS))
    for suite in report.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    if result.get("status") in {"passed", "skipped"}:
                        continue
                    error = result.get("error") or {}
                    message = error.get("message") or result.get("status", "failed")
                    text = str(message).strip()[:800]
                    failures.append(TestFailure(text, classify_failure(text)))
    return failures


def _npx() -> str:
    npx = shutil.which("npx")
    if npx is None:
        raise RuntimeError("npx was not found on PATH; Node.js is required")
    return npx


def report_path_for(config: WorkflowConfig) -> Path:
    """Where this run's Playwright JSON report is written."""
    return Path(config.artifacts_dir) / "playwright-report.json"


def failure_messages(report: dict) -> list[str]:
    """Pull human-readable failure reasons out of a Playwright JSON report."""
    return [failure.message for failure in classify_failures(report)]


def run_playwright(state: RunState, config: WorkflowConfig) -> bool:
    """Run the generated test and record the outcome on the state."""
    if not state.test_path:
        raise RuntimeError("No generated test to run")

    report_path = report_path_for(config)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        report_path.unlink()

    env = dict(os.environ)
    env["REPLAYER_TARGET_URL"] = state.url
    # Tell Playwright exactly where to write, then read back that same path.
    env["REPLAYER_JSON_REPORT"] = str(report_path.resolve())
    # Generated tests are excluded from the default suite; opt back in here.
    env["REPLAYER_RUN_GENERATED"] = "1"

    completed = subprocess.run(
        [_npx(), "playwright", "test", state.test_path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
        env=env,
    )

    if report_path.exists():
        state.test_report = json.loads(report_path.read_text(encoding="utf-8"))

    stats = state.test_report.get("stats", {})
    state.test_passed = (
        completed.returncode == 0
        and stats.get("unexpected", 1) == 0
        and stats.get("expected", 0) > 0
    )
    if not state.test_passed and not state.test_report:
        # No report at all means Playwright never ran the file. Surface that
        # instead of reporting an "unknown reason", which sent an earlier
        # investigation chasing model quality when the cause was configuration.
        state.test_report = {
            "stats": {},
            "harness_error": (
                f"playwright exited {completed.returncode} without writing a "
                f"report. stdout: {completed.stdout[-800:]} "
                f"stderr: {completed.stderr[-800:]}"
            ),
        }
    return bool(state.test_passed)
