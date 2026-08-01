"""Locator catalog construction. Pure code - never calls a model."""

from __future__ import annotations

import json
import re
from pathlib import Path

from replayer.config import WorkflowConfig
from replayer.state import LocatorEntry, RunState, SnapshotNode

#: Roles that are worth turning into locators. Structural containers are noise.
INTERESTING_ROLES: frozenset[str] = frozenset(
    {
        "button",
        "checkbox",
        "combobox",
        "heading",
        "link",
        "listitem",
        "menuitem",
        "option",
        "radio",
        "searchbox",
        "slider",
        "spinbutton",
        "switch",
        "tab",
        "textbox",
    }
)

_ROLE_IN_CODE = re.compile(r"getByRole\('([^']+)'")


def _escape(value: str) -> str:
    """Escape a string for embedding in a single-quoted TypeScript literal."""
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def locator_for(node: SnapshotNode) -> str | None:
    """Build a role-based Playwright locator expression for a snapshot node.

    ``exact: true`` is mandatory. Playwright's default name matching is
    case-insensitive substring matching, while our uniqueness check compares
    whole strings. Without ``exact`` the two disagree: on TodoMVC,
    ``getByRole('link', { name: 'TodoMVC' })`` selects two elements while the
    snapshot contains exactly one node with that name, so an ambiguous locator
    would be admitted into the catalog and fail at run time under strict mode.
    """
    if node.role not in INTERESTING_ROLES:
        return None
    if node.name:
        return (
            f"page.getByRole('{node.role}', "
            f"{{ name: '{_escape(node.name)}', exact: true }})"
        )
    return f"page.getByRole('{node.role}')"


def candidates_from_snapshots(state: RunState) -> dict[str, LocatorEntry]:
    """Collect locator candidates from every captured snapshot."""
    found: dict[str, LocatorEntry] = {}
    for snapshot in state.snapshots:
        for node in snapshot:
            expression = locator_for(node)
            if expression and expression not in found:
                found[expression] = LocatorEntry(
                    expression=expression,
                    role=node.role,
                    name=node.name,
                    ref=node.ref,
                )
    return found


def extract_locator_expressions(line: str) -> list[str]:
    """Pull complete ``page.getBy...(...)`` expressions out of a line of code.

    A regex with ``[^)]*`` truncates on accessible names that contain a closing
    parenthesis, silently degrading the locator to a nameless one. This scanner
    tracks quoting and nesting instead, so names like ``'Item (new)'`` survive.
    """
    results: list[str] = []
    marker = "page.getBy"
    index = line.find(marker)
    while index != -1:
        cursor = index + len(marker)
        while cursor < len(line) and (line[cursor].isalnum() or line[cursor] == "_"):
            cursor += 1
        if cursor >= len(line) or line[cursor] != "(":
            index = line.find(marker, index + 1)
            continue

        depth = 0
        quote: str | None = None
        end = cursor
        while end < len(line):
            char = line[end]
            if quote is not None:
                if char == "\\":
                    end += 2
                    continue
                if char == quote:
                    quote = None
            elif char in {"'", '"', "`"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    results.append(line[index : end + 1])
                    break
            end += 1
        index = line.find(marker, max(end, index + 1))
    return results


def candidates_from_observed_code(state: RunState) -> dict[str, LocatorEntry]:
    """Harvest locators from the Playwright code playwright-cli echoed back.

    These are the strongest candidates available: the tool already executed them
    successfully against the live page.
    """
    found: dict[str, LocatorEntry] = {}
    for line in state.observed_code:
        for expression in extract_locator_expressions(line):
            if expression in found:
                continue
            role_match = re.search(r"getByRole\('([^']+)'", expression)
            name_match = re.search(r"name:\s*'((?:[^'\\]|\\.)*)'", expression)
            role = role_match.group(1) if role_match else "unknown"
            name = name_match.group(1) if name_match else None
            # Re-emit in canonical form so every catalog entry carries exact:true.
            canonical = (
                f"page.getByRole('{role}', {{ name: '{name}', exact: true }})"
                if name is not None
                else f"page.getByRole('{role}')"
            )
            found[canonical] = LocatorEntry(
                expression=canonical, role=role, name=name
            )
    return found


def verify_candidates(
    candidates: dict[str, LocatorEntry], state: RunState
) -> list[LocatorEntry]:
    """Keep only locators proven to select exactly one element.

    A candidate is verified when there is at least one captured snapshot in
    which it matches exactly one node, and no snapshot in which it matches
    more than one. Snapshots are the live accessibility tree, so this is a
    check against the real page, not a guess.
    """
    verified: list[LocatorEntry] = []
    for entry in candidates.values():
        counts = [_count_matches(entry, snapshot) for snapshot in state.snapshots]
        if not counts:
            continue
        if any(count > 1 for count in counts):
            continue
        if not any(count == 1 for count in counts):
            continue
        entry.match_count = 1
        # The first snapshot is the page as a test would find it on load.
        entry.available_at_start = counts[0] == 1
        verified.append(entry)
    return verified


def _count_matches(entry: LocatorEntry, snapshot: list[SnapshotNode]) -> int:
    """How many nodes of one snapshot a role-based locator would select."""
    matches = 0
    for node in snapshot:
        if node.role != entry.role:
            continue
        if entry.name is not None and node.name != entry.name:
            continue
        matches += 1
    return matches


def build_catalog(state: RunState, config: WorkflowConfig) -> list[LocatorEntry]:
    """Derive candidates, verify uniqueness, and persist the catalog."""
    candidates = candidates_from_snapshots(state)
    candidates.update(candidates_from_observed_code(state))

    verified = verify_candidates(candidates, state)
    state.catalog = verified

    path = Path(config.artifacts_dir) / "locator-catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "expression": entry.expression,
                    "role": entry.role,
                    "name": entry.name,
                    "match_count": entry.match_count,
                    "available_at_start": entry.available_at_start,
                }
                for entry in verified
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    return verified
