"""Task 7 checks: the generated test type-checks and stays inside the catalog.

The catalog constraint is the mechanism that makes a small model reliable here,
so it is checked by parsing the emitted TypeScript rather than by trusting the
generator's own report.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from replayer.specfile import parse_spec_table
from replayer.steps.generate import (
    _static_problems,
    count_test_steps,
    find_disallowed_imports,
    find_locator_violations,
    normalise_locator,
    parse_test_source,
)
from _support import requires_provider

CATALOG = [
    "page.getByRole('textbox', { name: 'What needs to be done?', exact: true })",
    "page.getByRole('heading', { name: 'todos', exact: true })",
]

# --------------------------------------------------------------------------- #
# Pure checks.
# --------------------------------------------------------------------------- #


def test_violations_are_detected() -> None:
    source = (
        "await page.getByRole('heading', { name: 'todos', exact: true }).click();\n"
        "await page.getByRole('button', { name: 'Invented' }).click();\n"
    )
    violations = find_locator_violations(source, CATALOG)
    assert violations == [
        "page.getByRole('button', { name: 'Invented' })"
    ]


def test_whitespace_differences_are_not_violations() -> None:
    source = "page.getByRole('heading',{name:'todos',exact:true})"
    assert find_locator_violations(source, CATALOG) == []


def test_locator_with_parentheses_in_the_name_is_extracted_whole() -> None:
    catalog = ["page.getByRole('button', { name: 'Item (new)', exact: true })"]
    source = "await page.getByRole('button', { name: 'Item (new)', exact: true }).click();"
    assert find_locator_violations(source, catalog) == []


def test_count_test_steps() -> None:
    source = "await test.step('a', async () => {});\nawait test.step( 'b', async () => {});"
    assert count_test_steps(source) == 2


def test_parse_test_source_strips_code_fences() -> None:
    payload = '{"test_source": "```ts\\nimport x;\\n```"}'
    assert parse_test_source(payload) == "import x;"


def test_normalise_locator_ignores_spacing() -> None:
    assert normalise_locator("page.getByRole('a', { b: 1 })") == (
        "page.getByRole('a',{b:1})"
    )


# --------------------------------------------------------------------------- #
# The generated file is executed, so its imports are a privilege boundary.
# --------------------------------------------------------------------------- #


def test_the_playwright_import_is_allowed() -> None:
    source = "import { test, expect } from '@playwright/test';\n"
    assert find_disallowed_imports(source) == []


def test_other_imports_are_rejected() -> None:
    """Page content reaches the prompt, so the reply is untrusted input."""
    source = (
        "import { test, expect } from '@playwright/test';\n"
        "import { execSync } from 'child_process';\n"
    )
    assert find_disallowed_imports(source) == ["child_process"]


def test_bare_and_default_imports_are_rejected() -> None:
    assert find_disallowed_imports("import 'fs';\n") == ["fs"]
    assert find_disallowed_imports("import fs from 'fs';\n") == ["fs"]


def test_require_is_rejected() -> None:
    assert find_disallowed_imports("const cp = require('child_process');") == [
        "require()"
    ]


def test_a_disallowed_import_is_a_static_problem() -> None:
    """It must be caught before the file is written and executed."""
    source = (
        "import { test, expect } from '@playwright/test';\n"
        "import { execSync } from 'child_process';\n"
        "test('x', async ({ page }) => {\n"
        "  await test.step('a', async () => {});\n"
        "});\n"
    )
    problems = _static_problems(source, CATALOG, 1)
    assert any("@playwright/test" in problem for problem in problems)


# --------------------------------------------------------------------------- #
# Live checks - the Definition of Done.
# --------------------------------------------------------------------------- #


@requires_provider
async def test_generated_test_file_exists(live_run) -> None:
    state, _ = live_run
    assert state.test_path, "no test path recorded"
    assert Path(state.test_path).exists()


@requires_provider
async def test_generated_locators_are_all_from_the_catalog(live_run) -> None:
    state, _ = live_run
    source = Path(state.test_path).read_text(encoding="utf-8")
    violations = find_locator_violations(
        source, [entry.expression for entry in state.catalog]
    )
    assert violations == [], f"generated test invented locators: {violations}"


@requires_provider
async def test_test_step_count_matches_the_spec(live_run) -> None:
    state, _ = live_run
    source = Path(state.test_path).read_text(encoding="utf-8")
    spec_steps = parse_spec_table(
        Path(state.spec_path).read_text(encoding="utf-8")
    )
    assert count_test_steps(source) == len(spec_steps), (
        "the generated test must mirror the specification step for step"
    )


@requires_provider
async def test_generated_test_type_checks(live_run) -> None:
    """tsc is the arbiter, not our own opinion of the emitted source."""
    completed = subprocess.run(
        ["npx", "tsc", "--noEmit"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        shell=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
