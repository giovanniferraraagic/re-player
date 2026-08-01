"""Python driver for the playwright-cli command line tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Iterable

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


_SNAPSHOT_LINK_RE = re.compile(r"\[Snapshot\]\((?P<path>[^)]+)\)")
_PAGE_URL_RE = re.compile(r"^\s*-\s*Page URL:\s*(?P<value>.+?)\s*$")
_PAGE_TITLE_RE = re.compile(r"^\s*-\s*Page Title:\s*(?P<value>.+?)\s*$")
_MATCH_COUNT_RE = re.compile(
    r"Found\s+(?P<count>\d+)\s+match(?:es)?\s+for\s+"
)
_REF_RE = re.compile(r"\[ref=(?P<ref>e\d+)\]")
_ROLE_PREFIX_RE = re.compile(
    r"^(?P<role>[^\s\"\[]+)(?:\s+\"(?P<name>[^\"]*)\")?(?P<attrs>(?:\s+\[[^\]]+\])*)\s*$"
)
_ATTR_RE = re.compile(r"(?:\s+\[[^\]]+\])+$")


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
            snapshot_text = self._extract_inline_snapshot_text(result.stdout)
        return self._parse_snapshot_nodes(snapshot_text)

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
                cls._format_error_message(
                    ["list"],
                    completed.returncode,
                    completed.stdout,
                    completed.stderr,
                )
            )
        return cls._parse_session_list(completed.stdout)

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
            raise PlaywrightCliError(cls._format_error_message(list(command), exit_code, stdout, stderr))
        return CommandResult(
            stdout=stdout,
            exit_code=exit_code,
            code_lines=cls._extract_code_lines(stdout),
            snapshot_file_path=cls._extract_snapshot_path(stdout),
            page_url=cls._extract_page_url(stdout),
            page_title=cls._extract_page_title(stdout),
            match_count=cls._extract_match_count(stdout),
        )

    @staticmethod
    def _format_error_message(
        command: list[str],
        exit_code: int,
        stdout: str | None,
        stderr: str | None,
    ) -> str:
        command_text = " ".join(command) if command else "playwright-cli"
        parts = [f"Command failed: {command_text}", f"Exit code: {exit_code}"]
        if stdout:
            parts.append("Stdout:")
            parts.append(stdout.rstrip())
        if stderr:
            parts.append("Stderr:")
            parts.append(stderr.rstrip())
        return "\n".join(parts)

    @staticmethod
    def _extract_code_lines(stdout: str) -> list[str]:
        lines = stdout.splitlines()
        code_lines: list[str] = []
        in_section = False
        in_block = False
        for line in lines:
            if not in_section:
                if line.strip() == "### Ran Playwright code":
                    in_section = True
                continue
            if not in_block:
                if line.startswith("```"):
                    in_block = True
                continue
            if line.startswith("```"):
                break
            code_lines.append(line)
        return code_lines

    @staticmethod
    def _extract_snapshot_path(stdout: str) -> Path | None:
        match = _SNAPSHOT_LINK_RE.search(stdout)
        if match is None:
            return None
        snapshot_path = Path(match.group("path"))
        return snapshot_path if snapshot_path.is_absolute() else Path.cwd() / snapshot_path

    @staticmethod
    def _extract_page_url(stdout: str) -> str | None:
        for line in stdout.splitlines():
            match = _PAGE_URL_RE.match(line)
            if match is not None:
                return match.group("value")
        return None

    @staticmethod
    def _extract_page_title(stdout: str) -> str | None:
        for line in stdout.splitlines():
            match = _PAGE_TITLE_RE.match(line)
            if match is not None:
                return match.group("value")
        return None

    @staticmethod
    def _extract_match_count(stdout: str) -> int | None:
        match = _MATCH_COUNT_RE.search(stdout)
        if match is None:
            return None
        return int(match.group("count"))

    @staticmethod
    def _extract_inline_snapshot_text(stdout: str) -> str:
        lines = stdout.splitlines()
        collecting = False
        in_block = False
        snapshot_lines: list[str] = []
        for line in lines:
            if not collecting:
                if line.strip() == "### Snapshot":
                    collecting = True
                continue
            if not in_block:
                if line.startswith("```"):
                    in_block = True
                continue
            if line.startswith("```"):
                break
            snapshot_lines.append(line)
        return "\n".join(snapshot_lines)

    @classmethod
    def _parse_snapshot_nodes(cls, snapshot_text: str) -> list[SnapshotNode]:
        nodes: list[SnapshotNode] = []
        for raw_line in snapshot_text.splitlines():
            node = cls._parse_snapshot_line(raw_line)
            if node is not None:
                nodes.append(node)
        return nodes

    @staticmethod
    def _parse_snapshot_line(raw_line: str) -> SnapshotNode | None:
        stripped = raw_line.lstrip(" ")
        if not stripped.startswith("- "):
            return None
        indent = len(raw_line) - len(stripped)
        depth = indent // 2
        body = stripped[2:]
        match = _REF_RE.search(body)
        if match is None:
            return None
        prefix = body[: match.start()].strip()
        suffix = body[match.end() :].strip()
        prefix_match = _ROLE_PREFIX_RE.match(PlaywrightCliDriver._strip_trailing_attrs(prefix))
        if prefix_match is None:
            return None
        name = prefix_match.group("name")
        if name is None:
            tail = PlaywrightCliDriver._strip_trailing_attrs(suffix)
            if tail.startswith(":"):
                tail = tail[1:].strip()
            name = tail or None
        return SnapshotNode(
            role=prefix_match.group("role"),
            name=name,
            ref=match.group("ref"),
            depth=depth,
        )

    @staticmethod
    def _strip_trailing_attrs(value: str) -> str:
        return _ATTR_RE.sub("", value).strip()

    @staticmethod
    def _parse_session_list(stdout: str) -> list[str]:
        if "(no browsers)" in stdout:
            return []
        sessions: list[str] = []
        in_section = False
        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped == "### Browsers":
                in_section = True
                continue
            if in_section and stripped.startswith("### "):
                break
            if not in_section:
                continue
            match = re.match(r"^-\s+(?P<name>[^:]+):\s*$", stripped)
            if match is not None:
                name = match.group("name").strip().strip("`")
                sessions.append(name)
        return sessions

