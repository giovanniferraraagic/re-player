"""Python driver for the playwright-cli command line tool.

Process concerns only: locating the binary, running commands, timeouts and
session lifecycle. Reading the tool's stdout lives in
``replayer.driver_parsing``, which is pure and testable without a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Iterable

from replayer import driver_parsing

# SnapshotNode lives in replayer.state so the driver and the rest of the harness
# share a single data model.
from replayer.state import SnapshotNode as SnapshotNode


class PlaywrightCliError(RuntimeError):
    """Raised when a playwright-cli command fails."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The parsed result of a playwright-cli command."""

    stdout: str
    exit_code: int
    code_lines: list[str]
    snapshot_file_path: Path | None
    page_url: str | None
    page_title: str | None
    match_count: int | None = None


class PlaywrightCliDriver:
    """Small synchronous wrapper around the playwright-cli binary."""

    def __init__(self, session_name: str) -> None:
        self.session_name = session_name
        self._executable = shutil.which("playwright-cli")
        if self._executable is None:
            raise PlaywrightCliError("playwright-cli was not found on PATH.")
        self._closed = False
        self._opened = False

    def __enter__(self) -> "PlaywrightCliDriver":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Always attempt cleanup, but never let cleanup mask or invent failures.

        Closing a session that was never opened is not an error worth raising,
        and a teardown problem must not replace the exception that caused it.
        """
        if not self._opened:
            self._closed = True
            return False
        try:
            self.close()
        except Exception as close_error:  # noqa: BLE001
            if exc is not None and hasattr(exc, "add_note"):
                exc.add_note(f"Additional close failure: {close_error}")
        return False

    def open(self, url: str) -> CommandResult:
        result = self._run("open", url)
        self._opened = True
        return result

    def goto(self, url: str) -> CommandResult:
        return self._run("goto", url)

    def snapshot(self, depth: int | None = None) -> list[SnapshotNode]:
        args = ["snapshot"]
        if depth is not None:
            args.append(f"--depth={depth}")
        result = self._run(*args)
        if result.snapshot_file_path is not None and result.snapshot_file_path.exists():
            snapshot_text = result.snapshot_file_path.read_text(encoding="utf-8")
        else:
            snapshot_text = driver_parsing.extract_inline_snapshot_text(result.stdout)
        return driver_parsing.parse_snapshot_nodes(snapshot_text)

    def find(self, text: str) -> CommandResult:
        return self._run("find", text)

    def fill(self, ref: str, text: str, submit: bool = False) -> CommandResult:
        args = ["fill", ref, text]
        if submit:
            args.append("--submit")
        return self._run(*args)

    def click(self, ref: str) -> CommandResult:
        return self._run("click", ref)

    def check(self, ref: str) -> CommandResult:
        return self._run("check", ref)

    def press(self, key: str) -> CommandResult:
        return self._run("press", key)

    def type_text(self, text: str) -> CommandResult:
        return self._run("type", text)

    def close(self) -> CommandResult:
        if self._closed:
            return CommandResult("", 0, [], None, None, None)
        try:
            result = self._run("close")
        finally:
            self._closed = True
        return result

    @classmethod
    def list_sessions(cls) -> list[str]:
        executable = shutil.which("playwright-cli")
        if executable is None:
            raise PlaywrightCliError("playwright-cli was not found on PATH.")
        completed = subprocess.run(
            [executable, "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if completed.returncode != 0:
            raise PlaywrightCliError(
                driver_parsing.format_error_message(
                    ["list"],
                    completed.returncode,
                    completed.stdout,
                    completed.stderr,
                )
            )
        return driver_parsing.parse_session_list(completed.stdout)

    def _run(self, *command: str) -> CommandResult:
        completed = self._execute(command)
        return self._parse_result(command, completed.stdout, completed.stderr, completed.returncode)

    def _execute(self, command: Iterable[str]) -> subprocess.CompletedProcess[str]:
        full_command = [self._executable or "playwright-cli", f"-s={self.session_name}", *command]
        try:
            return subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
        except subprocess.TimeoutExpired as error:
            raise PlaywrightCliError(
                f"playwright-cli command timed out: {' '.join(full_command)}"
            ) from error

    @classmethod
    def _parse_result(
        cls,
        command: Iterable[str],
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> CommandResult:
        if exit_code != 0:
            raise PlaywrightCliError(
                driver_parsing.format_error_message(
                    list(command), exit_code, stdout, stderr
                )
            )
        return CommandResult(
            stdout=stdout,
            exit_code=exit_code,
            code_lines=driver_parsing.extract_code_lines(stdout),
            snapshot_file_path=driver_parsing.extract_snapshot_path(stdout),
            page_url=driver_parsing.extract_page_url(stdout),
            page_title=driver_parsing.extract_page_title(stdout),
            match_count=driver_parsing.extract_match_count(stdout),
        )

