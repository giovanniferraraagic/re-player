"""Shared pytest setup.

The .env file is loaded here, before any test module is imported, because skip
conditions are evaluated at collection time. Loading it later would leave the
live-model tests permanently skipped - and a skipped test that reads as green is
exactly the false confidence this project exists to avoid.

The live workflow is executed once per session and shared, so the tests that
need a real model do not each pay for their own run.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from replayer.config import WorkflowConfig, load_dotenv

load_dotenv()

TARGET_URL = "https://demo.playwright.dev/todomvc/"

requires_provider = pytest.mark.skipif(
    not os.environ.get("AZURE_OPENAI_API_KEY"),
    reason="no model provider configured",
)


@pytest.fixture(scope="session")
def live_artifacts_dir(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("live-artifacts")


@pytest.fixture(scope="session")
async def live_run(live_artifacts_dir: Path):
    """One real end-to-end run, shared by every test that needs its output."""
    if not os.environ.get("AZURE_OPENAI_API_KEY"):
        pytest.skip("no model provider configured")

    from replayer.workflow import execute

    config = WorkflowConfig.from_env(url=TARGET_URL, session="replayer-live-test")
    config.max_explore_steps = 4
    config.artifacts_dir = str(live_artifacts_dir)
    config.checkpoint_dir = str(live_artifacts_dir / "checkpoints")

    state = await execute(config)
    return state, config
