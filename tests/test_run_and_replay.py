"""Tasks 8 and 9: the run report attributes cost, and a run can be replayed.

Together these close the loop on the project's two claims. The report proves
that four of the seven executors cost nothing. The replay proves that the
sequence of steps and the artifacts they produce are reproducible, with the
model's non-determinism factored out into a recording.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from _support import requires_provider

from replayer.config import CODE_ONLY_STEPS, LLM_STEPS, WorkflowConfig
from replayer.workflow import execute

TARGET_URL = "https://demo.playwright.dev/todomvc/"


# --------------------------------------------------------------------------- #
# Task 8 - run and report.
# --------------------------------------------------------------------------- #


@requires_provider
async def test_generated_test_passed(live_run) -> None:
    state, _ = live_run
    assert state.test_passed is True, "the generated test did not pass"


@requires_provider
async def test_run_report_is_written(live_run) -> None:
    state, _ = live_run
    assert state.report_path
    payload = json.loads(Path(state.report_path).read_text(encoding="utf-8"))
    assert payload["test_passed"] is True
    assert payload["spec_path"]
    assert payload["test_path"]


@requires_provider
async def test_cost_attribution_separates_code_from_model_steps(live_run) -> None:
    """The headline claim: four of seven executors cost nothing."""
    state, _ = live_run
    payload = json.loads(Path(state.report_path).read_text(encoding="utf-8"))
    usage = payload["usage"]

    for step in CODE_ONLY_STEPS:
        assert usage[step]["total_tokens"] == 0, f"{step} spent tokens"
    for step in LLM_STEPS:
        assert usage[step]["total_tokens"] > 0, f"{step} reported no cost"


@requires_provider
async def test_cli_runs_the_whole_workflow(live_artifacts_dir: Path) -> None:
    """`replayer run` is the user-facing entry point, so exercise it as a process."""
    import os

    env = dict(os.environ)
    env["REPLAYER_ARTIFACTS_DIR"] = str(live_artifacts_dir / "cli")
    env["REPLAYER_CHECKPOINT_DIR"] = str(live_artifacts_dir / "cli-checkpoints")
    env["REPLAYER_MAX_EXPLORE_STEPS"] = "3"

    completed = subprocess.run(
        [str(Path(".venv/Scripts/replayer.exe").resolve()), "run", "--url", TARGET_URL],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
        env=env,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Report:" in completed.stdout


# --------------------------------------------------------------------------- #
# Task 9 - replay.
# --------------------------------------------------------------------------- #


@requires_provider
async def test_replay_reproduces_the_same_artifacts(tmp_path: Path) -> None:
    """A recorded run, replayed, yields byte-identical spec and test files."""
    original_dir = tmp_path / "original"
    replay_dir = tmp_path / "replay"
    recording = tmp_path / "transcript.jsonl"

    original_config = WorkflowConfig.from_env(
        url=TARGET_URL, session="replayer-record"
    )
    original_config.max_explore_steps = 3
    original_config.artifacts_dir = str(original_dir)
    original_config.checkpoint_dir = str(tmp_path / "cp1")
    original_config.record_path = str(recording)

    original = await execute(original_config)
    original_spec = Path(original.spec_path).read_bytes()
    original_test = Path(original.test_path).read_bytes()

    assert recording.exists() and recording.stat().st_size > 0

    replay_config = WorkflowConfig.from_env(url=TARGET_URL, session="replayer-replay")
    replay_config.max_explore_steps = 3
    replay_config.artifacts_dir = str(replay_dir)
    replay_config.checkpoint_dir = str(tmp_path / "cp2")
    replay_config.replay_path = str(recording)

    replayed = await execute(replay_config)

    assert Path(replayed.spec_path).read_bytes() == original_spec
    assert Path(replayed.test_path).read_bytes() == original_test
    assert list(replayed.usage) == list(original.usage)


@requires_provider
async def test_replay_costs_nothing_from_the_provider(tmp_path: Path) -> None:
    """Replaying must not call the provider again - that is the point."""
    recording = tmp_path / "transcript.jsonl"
    record_config = WorkflowConfig.from_env(url=TARGET_URL, session="replayer-rec2")
    record_config.max_explore_steps = 2
    record_config.artifacts_dir = str(tmp_path / "a")
    record_config.checkpoint_dir = str(tmp_path / "cp3")
    record_config.record_path = str(recording)
    await execute(record_config)

    from replayer.models import AzureOpenAIChatClient, ReplayModelClient, client_for

    replay_config = WorkflowConfig.from_env(url=TARGET_URL, session="replayer-rep2")
    replay_config.replay_path = str(recording)
    client = client_for(replay_config)

    assert isinstance(client, ReplayModelClient)
    assert not isinstance(client, AzureOpenAIChatClient)
