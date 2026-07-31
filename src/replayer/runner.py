"""Test execution. Pure code - never calls a model."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from replayer.config import WorkflowConfig
from replayer.state import RunState


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
    messages: list[str] = []
    for suite in report.get("suites", []):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    if result.get("status") == "passed":
                        continue
                    error = result.get("error") or {}
                    message = error.get("message") or result.get("status", "failed")
                    messages.append(str(message).strip()[:800])
    return messages


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
    return bool(state.test_passed)
