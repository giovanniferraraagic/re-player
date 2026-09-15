"""Parsing of playwright-cli stdout, tested without the binary or a browser.

This is the harness's most brittle code: it reverse-engineers another tool's
human-readable output, and a silent parsing regression degrades every step
downstream. Before this module was extracted the only coverage was one live
integration test that needed `playwright-cli` on PATH.
"""

from __future__ import annotations

from pathlib import Path

from replayer.driver_parsing import (
    extract_code_lines,
    extract_inline_snapshot_text,
    extract_match_count,
    extract_page_title,
    extract_page_url,
    extract_snapshot_path,
    parse_session_list,
    parse_snapshot_line,
    parse_snapshot_nodes,
)

OPEN_OUTPUT = """### Ran Playwright code
```js
await page.goto('https://demo.playwright.dev/todomvc/');
await page.getByRole('textbox', { name: 'What needs to be done?' }).click();
```

### Page state
- Page URL: https://demo.playwright.dev/todomvc/
- Page Title: React • TodoMVC

### Snapshot
```yaml
- generic [ref=e1]:
  - heading "todos" [level=1] [ref=e2]
  - textbox "What needs to be done?" [ref=e3]
```
"""

SNAPSHOT_TEXT = """- generic [ref=e1]:
  - heading "todos" [level=1] [ref=e2]
  - textbox "What needs to be done?" [ref=e3]
  - listitem [ref=e4]:
    - checkbox [checked] [ref=e5]
"""


# --------------------------------------------------------------------------- #
# Page metadata.
# --------------------------------------------------------------------------- #


def test_page_url_and_title_are_extracted() -> None:
    assert extract_page_url(OPEN_OUTPUT) == "https://demo.playwright.dev/todomvc/"
    assert extract_page_title(OPEN_OUTPUT) == "React • TodoMVC"


def test_missing_metadata_yields_none() -> None:
    assert extract_page_url("### Nothing here") is None
    assert extract_page_title("### Nothing here") is None
    assert extract_match_count("### Nothing here") is None


def test_match_count_is_extracted_for_one_and_many() -> None:
    assert extract_match_count("Found 1 match for 'Buy milk'") == 1
    assert extract_match_count("Found 3 matches for 'todo'") == 3


# --------------------------------------------------------------------------- #
# Fenced blocks.
# --------------------------------------------------------------------------- #


def test_code_lines_stop_at_the_closing_fence() -> None:
    """The code block must not bleed into the sections that follow it."""
    lines = extract_code_lines(OPEN_OUTPUT)
    assert lines == [
        "await page.goto('https://demo.playwright.dev/todomvc/');",
        "await page.getByRole('textbox', { name: 'What needs to be done?' }).click();",
    ]


def test_inline_snapshot_is_read_when_no_file_was_written() -> None:
    text = extract_inline_snapshot_text(OPEN_OUTPUT)
    assert text.splitlines()[0] == "- generic [ref=e1]:"
    assert 'textbox "What needs to be done?" [ref=e3]' in text


def test_absent_sections_yield_empty_results() -> None:
    assert extract_code_lines("nothing at all") == []
    assert extract_inline_snapshot_text("nothing at all") == ""


def test_snapshot_path_is_extracted_and_made_absolute(tmp_path: Path) -> None:
    """A relative path is anchored to the working directory, an absolute one kept.

    ``tmp_path`` supplies a genuinely absolute path for the current platform;
    a hardcoded POSIX path is drive-relative on Windows and would not exercise
    the branch it looks like it exercises.
    """
    absolute_path = tmp_path / "snap.yml"
    absolute = extract_snapshot_path(f"See [Snapshot]({absolute_path.as_posix()})")
    assert absolute == absolute_path

    relative = extract_snapshot_path("See [Snapshot](out/snap.yml)")
    assert relative is not None and relative.is_absolute()
    assert relative == Path.cwd() / "out/snap.yml"


def test_snapshot_path_is_none_when_absent() -> None:
    assert extract_snapshot_path("no link here") is None


# --------------------------------------------------------------------------- #
# Snapshot nodes.
# --------------------------------------------------------------------------- #


def test_named_node_is_parsed_with_role_name_and_ref() -> None:
    node = parse_snapshot_line('  - textbox "What needs to be done?" [ref=e3]')
    assert node is not None
    assert node.role == "textbox"
    assert node.name == "What needs to be done?"
    assert node.ref == "e3"
    assert node.depth == 1


def test_attributes_are_stripped_from_the_name() -> None:
    node = parse_snapshot_line('  - heading "todos" [level=1] [ref=e2]')
    assert node is not None
    assert node.role == "heading"
    assert node.name == "todos"


def test_unnamed_node_has_no_name() -> None:
    node = parse_snapshot_line("    - checkbox [checked] [ref=e5]")
    assert node is not None
    assert node.role == "checkbox"
    assert node.name is None


def test_lines_without_a_ref_are_skipped() -> None:
    """A node the harness cannot address is not a node it can use."""
    assert parse_snapshot_line("- generic:") is None
    assert parse_snapshot_line("not a list item") is None
    assert parse_snapshot_line("") is None


def test_depth_tracks_indentation() -> None:
    nodes = parse_snapshot_nodes(SNAPSHOT_TEXT)
    by_ref = {node.ref: node for node in nodes}
    assert by_ref["e1"].depth == 0
    assert by_ref["e2"].depth == 1
    assert by_ref["e5"].depth == 2


def test_all_referenceable_nodes_are_returned_in_order() -> None:
    nodes = parse_snapshot_nodes(SNAPSHOT_TEXT)
    assert [node.ref for node in nodes] == ["e1", "e2", "e3", "e4", "e5"]


# --------------------------------------------------------------------------- #
# Session list.
# --------------------------------------------------------------------------- #


def test_no_browsers_yields_an_empty_list() -> None:
    assert parse_session_list("### Browsers\n(no browsers)\n") == []


def test_session_names_are_unquoted() -> None:
    stdout = "### Browsers\n- `replayer`:\n- `other-session`:\n"
    assert parse_session_list(stdout) == ["replayer", "other-session"]


def test_session_parsing_stops_at_the_next_section() -> None:
    stdout = "### Browsers\n- `replayer`:\n\n### Other\n- `not-a-session`:\n"
    assert parse_session_list(stdout) == ["replayer"]
