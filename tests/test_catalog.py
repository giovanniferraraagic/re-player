"""Task 3 checks: the locator catalog is real, and every entry is unambiguous.

The catalog is the project's "building block". Its whole value is that the
generator can pick from it instead of inventing selectors, so an entry that
selects zero or several elements is worse than no entry at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from replayer.catalog import (
    build_catalog,
    candidates_from_observed_code,
    candidates_from_snapshots,
)
from replayer.config import WorkflowConfig
from replayer.driver import PlaywrightCliDriver
from replayer.state import RunState

TARGET_URL = "https://demo.playwright.dev/todomvc/"
MINIMUM_ENTRIES = 5


@pytest.fixture(scope="module")
def explored_state() -> RunState:
    """Drive TodoMVC far enough to produce a realistic set of snapshots."""
    state = RunState(url=TARGET_URL, session="replayer-catalog-test")
    with PlaywrightCliDriver(state.session) as driver:
        opened = driver.open(TARGET_URL)
        state.observed_code.extend(opened.code_lines)
        first = driver.snapshot()
        state.snapshots.append(first)

        textbox = next(node for node in first if node.role == "textbox")
        filled = driver.fill(textbox.ref, "Buy groceries", submit=True)
        state.observed_code.extend(filled.code_lines)
        state.snapshots.append(driver.snapshot())
    return state


@pytest.fixture(scope="module")
def catalog(explored_state: RunState, tmp_path_factory) -> list:
    tmp = tmp_path_factory.mktemp("catalog")
    config = WorkflowConfig.from_env(
        url=TARGET_URL, session=explored_state.session, stub_llm=True
    )
    config.artifacts_dir = str(tmp)
    return build_catalog(explored_state, config)


def _count_matches(entry, snapshot) -> int:
    return sum(
        1
        for node in snapshot
        if node.role == entry.role
        and (entry.name is None or node.name == entry.name)
    )


def test_catalog_has_enough_entries(catalog) -> None:
    assert len(catalog) >= MINIMUM_ENTRIES, (
        f"catalog has {len(catalog)} entries, expected at least {MINIMUM_ENTRIES}"
    )


def test_every_entry_resolves_to_exactly_one_element(catalog, explored_state) -> None:
    """Independently recount every entry rather than trusting build_catalog."""
    for entry in catalog:
        counts = [
            _count_matches(entry, snapshot) for snapshot in explored_state.snapshots
        ]
        assert max(counts) == 1, (
            f"{entry.expression!r} matches {max(counts)} elements; "
            "a catalog entry must be unambiguous"
        )
        assert 1 in counts, f"{entry.expression!r} never matched anything"


def test_catalog_entries_are_role_based_playwright_locators(catalog) -> None:
    for entry in catalog:
        assert entry.expression.startswith("page.getBy"), entry.expression


def test_observed_code_contributes_candidates(explored_state) -> None:
    """playwright-cli echoes the code it ran; those locators are pre-proven."""
    from_code = candidates_from_observed_code(explored_state)
    assert from_code, "expected at least one locator harvested from echoed code"


def test_snapshot_candidates_are_found(explored_state) -> None:
    from_snapshots = candidates_from_snapshots(explored_state)
    assert from_snapshots, "expected at least one locator derived from snapshots"


def test_catalog_artifact_is_written(catalog, explored_state, tmp_path) -> None:
    config = WorkflowConfig.from_env(
        url=TARGET_URL, session=explored_state.session, stub_llm=True
    )
    config.artifacts_dir = str(tmp_path)
    build_catalog(explored_state, config)

    written = Path(tmp_path) / "locator-catalog.json"
    assert written.exists()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert len(payload) >= MINIMUM_ENTRIES
    assert all(item["match_count"] == 1 for item in payload)

