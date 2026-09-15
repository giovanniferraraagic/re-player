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
_LOCATOR_PREFIX_RE = re.compile(r"locator\.\w+\s*:", re.IGNORECASE)
_LOCATOR_MARKERS = (
    "strict mode violation",
    "waiting for locator",
    "failed to resolve locator",
)
_ALLOWED_CHILD_ENV_VARS = {
    "CI",
    "COMSPEC",
    "HOME",
    "LANG",
    "LC_ALL",
    "OS",
    "PATH",
    "PATHEXT",
    "PWD",
    "SHELL",
    "SYSTEMROOT",
    "TEMP",
    "TEMPDIR",
    "TERM",
    "TMP",
    "TMPDIR",
    "USER",
    "USERPROFILE",
    "UNRELATED_SETTING",
    "PLAYWRIGHT_BROWSERS_PATH",
    "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD",
    "NODE_ENV",
}


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
    if _LOCATOR_PREFIX_RE.search(text) or any(marker in lowered for marker in _LOCATOR_MARKERS):
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


def _child_environment_for_generated_test(state: RunState, report_path: Path) -> dict[str, str]:
    """Build a restricted environment for the untrusted generated test.

    We keep only the minimum system values needed for Node/Playwright to run,
    plus every `REPLAYER_*` variable and any values explicitly opted into via
    `REPLAYER_ALLOW_ENV`. This prevents model-authored code from inheriting CI
    credentials or provider keys by accident.
    """
    passthrough = {
        key.strip()
        for key in os.environ.get("REPLAYER_ALLOW_ENV", "").split(",")
        if key.strip()
    }
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if key.startswith("REPLAYER_") or key in _ALLOWED_CHILD_ENV_VARS or key in passthrough:
            env[key] = value
    env["REPLAYER_TARGET_URL"] = state.url
    env["REPLAYER_JSON_REPORT"] = str(report_path.resolve())
    env["REPLAYER_RUN_GENERATED"] = "1"
    return env


def run_playwright(state: RunState, config: WorkflowConfig) -> bool:
    """Run the generated test and record the outcome on the state."""
    if not state.test_path:
        raise RuntimeError("No generated test to run")

    report_path = report_path_for(config)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if report_path.exists():
        report_path.unlink()

    env = _child_environment_for_generated_test(state, report_path)
    env["REPLAYER_TEST_DIR"] = str(Path(config.generated_tests_dir).resolve().parent)

    try:
        completed = subprocess.run(
            [_npx(), "playwright", "test", state.test_path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        completed = exc
        completed.returncode = 124
        completed.stdout = (getattr(exc, "stdout", "") or "")
        completed.stderr = (getattr(exc, "stderr", "") or "")

    if report_path.exists():
        try:
            state.test_report = json.loads(report_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            state.test_report = {
                "stats": {},
                "harness_error": (
                    f"playwright wrote an invalid JSON report: {exc}. "
                    f"stdout: {getattr(completed, 'stdout', '')[-800:]} "
                    f"stderr: {getattr(completed, 'stderr', '')[-800:]}"
                ),
            }

    stats = state.test_report.get("stats", {})
    state.test_passed = (
        getattr(completed, "returncode", 1) == 0
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
                f"playwright exited {getattr(completed, 'returncode', 1)} without writing a "
                f"report. stdout: {getattr(completed, 'stdout', '')[-800:]} "
                f"stderr: {getattr(completed, 'stderr', '')[-800:]}"
            ),
        }
    return bool(state.test_passed)
