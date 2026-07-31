"""Task 6 checks: the spec artifact is well formed and reviewable.

The spec is what a human approves, so the checks read the file from disk and
parse it back, rather than inspecting the objects that produced it. A spec that
only exists in memory cannot be reviewed.
"""

from __future__ import annotations

from pathlib import Path

from replayer.specfile import parse_spec_table, render_spec, slugify
from replayer.state import RunState, SpecStep
from replayer.steps.plan import parse_spec
from _support import requires_provider

# --------------------------------------------------------------------------- #
# Pure checks.
# --------------------------------------------------------------------------- #


def test_parse_spec_drops_steps_without_an_expected_result() -> None:
    _, _, steps = parse_spec(
        '{"title": "T", "description": "D", "steps": ['
        '{"action": "do a", "expected": "see a"},'
        '{"action": "do b", "expected": ""},'
        '{"action": "", "expected": "see c"}]}'
    )
    assert [step.action for step in steps] == ["do a"]
    assert steps[0].index == 1


def test_render_and_parse_round_trip() -> None:
    state = RunState(url="http://example.test", session="s")
    state.spec_title = "Round trip"
    state.spec_steps = [
        SpecStep(index=1, action="Do the thing", expected="The thing happened"),
        SpecStep(index=2, action="Do it again", expected="It happened twice"),
    ]
    parsed = parse_spec_table(render_spec(state))
    assert [(s.index, s.action, s.expected) for s in parsed] == [
        (1, "Do the thing", "The thing happened"),
        (2, "Do it again", "It happened twice"),
    ]


def test_pipe_characters_cannot_break_the_table() -> None:
    state = RunState(url="http://example.test", session="s")
    state.spec_title = "Escaping"
    state.spec_steps = [
        SpecStep(index=1, action="Type a | pipe", expected="It is still one cell")
    ]
    parsed = parse_spec_table(render_spec(state))
    assert len(parsed) == 1


def test_slugify_produces_a_filesystem_safe_name() -> None:
    assert slugify("Add & complete a TODO!") == "add-complete-a-todo"


# --------------------------------------------------------------------------- #
# Live checks - the Definition of Done.
# --------------------------------------------------------------------------- #


@requires_provider
async def test_spec_file_is_written(live_run) -> None:
    state, _ = live_run
    assert state.spec_path, "no spec path recorded"
    assert Path(state.spec_path).exists()


@requires_provider
async def test_spec_table_parses_and_is_complete(live_run) -> None:
    state, _ = live_run
    markdown = Path(state.spec_path).read_text(encoding="utf-8")
    steps = parse_spec_table(markdown)

    assert len(steps) >= 2, f"spec has {len(steps)} steps, expected at least 2"
    for step in steps:
        assert step.action.strip(), f"step {step.index} has an empty action"
        assert step.expected.strip(), f"step {step.index} has no expected result"


@requires_provider
async def test_spec_step_numbering_is_sequential(live_run) -> None:
    state, _ = live_run
    steps = parse_spec_table(Path(state.spec_path).read_text(encoding="utf-8"))
    assert [step.index for step in steps] == list(range(1, len(steps) + 1))


@requires_provider
async def test_spec_mentions_no_code(live_run) -> None:
    """The supervision interface must be readable without opening the test.

    The markers are deliberately code-shaped. An earlier version rejected the
    bare string "page.", which also matches an ordinary English sentence ending
    in "the page." - a check that fails on correct output is worse than no
    check, because it trains you to ignore it.
    """
    state, _ = live_run
    markdown = Path(state.spec_path).read_text(encoding="utf-8").lower()
    for forbidden in ("getbyrole(", "page.getby", "await ", "expect(", "locator("):
        assert forbidden not in markdown, f"spec leaks implementation: {forbidden!r}"
