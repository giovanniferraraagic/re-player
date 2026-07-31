"""Reading and writing the canonical spec format.

The format is an Azure DevOps style step table: a title, a short description,
and rows of ``Test Step | Step Action | Step Expected``. It was chosen because
it is the native shape of ADO Test Plans, stays readable for a human reviewer,
and can be regenerated row by row.
"""

from __future__ import annotations

import re
from pathlib import Path

from replayer.state import RunState, SpecStep

_TABLE_ROW = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "untitled"


def _escape_cell(value: str) -> str:
    """Keep a value inside one table cell."""
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_spec(state: RunState) -> str:
    """Render the spec as Markdown with an ADO-compatible step table."""
    lines = [f"# {state.spec_title}", ""]
    if state.spec_description:
        lines += [state.spec_description, ""]
    lines += [
        f"- **Application**: {state.url}",
        "",
        "| Test Step | Step Action | Step Expected |",
        "|---|---|---|",
    ]
    for step in state.spec_steps:
        lines.append(
            f"| {step.index} | {_escape_cell(step.action)} "
            f"| {_escape_cell(step.expected)} |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_spec_table(markdown: str) -> list[SpecStep]:
    """Read the step table back out of a rendered spec.

    Written so the check can verify the artifact on disk rather than the
    in-memory objects that produced it. Cells are split on unescaped pipes
    only: the renderer escapes any pipe inside a value, and splitting naively
    would silently drop such a row.
    """
    steps: list[SpecStep] = []
    for raw_line in markdown.splitlines():
        match = _TABLE_ROW.match(raw_line.strip())
        if not match:
            continue
        cells = [
            cell.strip().replace("\\|", "|")
            for cell in _UNESCAPED_PIPE.split(match.group("cells"))
        ]
        if len(cells) != 3:
            continue
        index, action, expected = cells
        if index.lower() == "test step" or set(index) <= {"-", ":"}:
            continue
        if not index.isdigit():
            continue
        steps.append(SpecStep(index=int(index), action=action, expected=expected))
    return steps


def write_spec(state: RunState, artifacts_dir: str) -> Path:
    """Persist the spec and record its path on the state."""
    directory = Path(artifacts_dir) / "specs"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slugify(state.spec_title)}.md"
    path.write_text(render_spec(state), encoding="utf-8")
    state.spec_path = str(path)
    return path
