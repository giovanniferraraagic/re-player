"""The generated test runs as untrusted code, so it must not inherit secrets.

The file executed by `npx playwright test` is written by a model whose prompt
contains text taken from the page under test. Whatever it prints is captured
into `harness_error` and from there into the run report and the terminal, so a
provider key in its environment is a key one `console.log` away from an
artifact on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from replayer.config import WorkflowConfig
from replayer.state import RunState


@pytest.fixture
def captured_env(monkeypatch, tmp_path: Path) -> dict:
    """Run `run_playwright` against a fake subprocess and keep the env it used."""
    seen: dict = {}

    class _Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def _fake_run(command, **kwargs):
        seen.update(kwargs.get("env") or {})
        return _Completed()

    monkeypatch.setattr("replayer.runner.subprocess.run", _fake_run)
    monkeypatch.setattr("replayer.runner._npx", lambda: "npx")

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "super-secret")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("OPENAI_API_KEY", "also-secret")
    monkeypatch.setenv("UNRELATED_SETTING", "keep-me")

    from replayer.runner import run_playwright

    config = WorkflowConfig(url="https://example.test/", session="env")
    config.artifacts_dir = str(tmp_path / "artifacts")
    state = RunState(url="https://example.test/", session="env")
    state.test_path = "e2e/generated/x.spec.ts"

    run_playwright(state, config)
    return seen


def test_provider_credentials_are_not_passed_to_the_generated_test(
    captured_env: dict,
) -> None:
    leaked = [key for key in captured_env if key.startswith(("AZURE_OPENAI", "OPENAI"))]
    assert leaked == [], f"model credentials reached the test process: {leaked}"
    assert "super-secret" not in captured_env.values()


def test_the_rest_of_the_environment_still_reaches_the_test(
    captured_env: dict,
) -> None:
    """Scrubbing must not break PATH-dependent tooling or the harness's own vars."""
    assert captured_env["UNRELATED_SETTING"] == "keep-me"
    assert captured_env["REPLAYER_TARGET_URL"] == "https://example.test/"
    assert captured_env["REPLAYER_RUN_GENERATED"] == "1"
    assert captured_env["REPLAYER_TEST_DIR"].endswith("e2e")
