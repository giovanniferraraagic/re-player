"""Parsing of ``playwright-cli`` stdout.

Split out of ``replayer.driver`` because these are pure functions of a string:
they need no subprocess, no browser and no binary on PATH, so they can be tested
directly against captured output. The driver keeps the process concerns.

This is the most brittle code in the harness - it reverse-engineers another
tool's human-readable output - which is exactly why it is the part that should
be cheapest to test.
"""

from __future__ import annotations

import re
from pathlib import Path

from replayer.state import SnapshotNode

_SNAPSHOT_LINK_RE = re.compile(r"\[Snapshot\]\((?P<path>[^)]+)\)")
_PAGE_URL_RE = re.compile(r"^\s*-\s*Page URL:\s*(?P<value>.+?)\s*$")
_PAGE_TITLE_RE = re.compile(r"^\s*-\s*Page Title:\s*(?P<value>.+?)\s*$")
_MATCH_COUNT_RE = re.compile(r"Found\s+(?P<count>\d+)\s+match(?:es)?\s+for\s+")
_REF_RE = re.compile(r"\[ref=(?P<ref>e\d+)\]")
_ROLE_PREFIX_RE = re.compile(
    r"^(?P<role>[^\s\"\[]+)(?:\s+\"(?P<name>[^\"]*)\")?(?P<attrs>(?:\s+\[[^\]]+\])*)\s*$"
)
_ATTR_RE = re.compile(r"(?:\s+\[[^\]]+\])+$")
_SESSION_RE = re.compile(r"^-\s+(?P<name>[^:]+):\s*$")

CODE_HEADING = "### Ran Playwright code"
SNAPSHOT_HEADING = "### Snapshot"


def fenced_block_after(stdout: str, heading: str) -> list[str]:
    """Lines of the first fenced code block following ``heading``.

    Both the echoed Playwright code and the inline snapshot are formatted this
    way, so they share one reader rather than two near-identical loops.
    """
    lines: list[str] = []
    in_section = False
    in_block = False
    for line in stdout.splitlines():
        if not in_section:
            if line.strip() == heading:
                in_section = True
            continue
        if not in_block:
            if line.startswith("```"):
                in_block = True
            continue
        if line.startswith("```"):
            break
        lines.append(line)
    return lines


def extract_code_lines(stdout: str) -> list[str]:
    """The Playwright code the tool reports having run."""
    return fenced_block_after(stdout, CODE_HEADING)


def extract_inline_snapshot_text(stdout: str) -> str:
    """The snapshot printed inline, used when no snapshot file was written."""
    return "\n".join(fenced_block_after(stdout, SNAPSHOT_HEADING))


def extract_snapshot_path(stdout: str) -> Path | None:
    """The path of the snapshot file, resolved against the working directory."""
    match = _SNAPSHOT_LINK_RE.search(stdout)
    if match is None:
        return None
    snapshot_path = Path(match.group("path"))
    return snapshot_path if snapshot_path.is_absolute() else Path.cwd() / snapshot_path


def extract_page_url(stdout: str) -> str | None:
    for line in stdout.splitlines():
        match = _PAGE_URL_RE.match(line)
        if match is not None:
            return match.group("value")
    return None


def extract_page_title(stdout: str) -> str | None:
    for line in stdout.splitlines():
        match = _PAGE_TITLE_RE.match(line)
        if match is not None:
            return match.group("value")
    return None


def extract_match_count(stdout: str) -> int | None:
    match = _MATCH_COUNT_RE.search(stdout)
    if match is None:
        return None
    return int(match.group("count"))


def strip_trailing_attrs(value: str) -> str:
    return _ATTR_RE.sub("", value).strip()


def parse_snapshot_line(raw_line: str) -> SnapshotNode | None:
    """Parse one accessibility-tree line, or return None if it carries no ref."""
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
    prefix_match = _ROLE_PREFIX_RE.match(strip_trailing_attrs(prefix))
    if prefix_match is None:
        return None
    name = prefix_match.group("name")
    if name is None:
        tail = strip_trailing_attrs(suffix)
        if tail.startswith(":"):
            tail = tail[1:].strip()
        name = tail or None
    return SnapshotNode(
        role=prefix_match.group("role"),
        name=name,
        ref=match.group("ref"),
        depth=depth,
    )


def parse_snapshot_nodes(snapshot_text: str) -> list[SnapshotNode]:
    """Every referenceable node of a snapshot, in document order."""
    nodes: list[SnapshotNode] = []
    for raw_line in snapshot_text.splitlines():
        node = parse_snapshot_line(raw_line)
        if node is not None:
            nodes.append(node)
    return nodes


def parse_session_list(stdout: str) -> list[str]:
    """Session names from ``playwright-cli list``."""
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
        match = _SESSION_RE.match(stripped)
        if match is not None:
            sessions.append(match.group("name").strip().strip("`"))
    return sessions


def format_error_message(
    command: list[str],
    exit_code: int,
    stdout: str | None,
    stderr: str | None,
) -> str:
    """A failure message that carries enough context to diagnose the command."""
    command_text = " ".join(command) if command else "playwright-cli"
    parts = [f"Command failed: {command_text}", f"Exit code: {exit_code}"]
    if stdout:
        parts.append("Stdout:")
        parts.append(stdout.rstrip())
    if stderr:
        parts.append("Stderr:")
        parts.append(stderr.rstrip())
    return "\n".join(parts)
