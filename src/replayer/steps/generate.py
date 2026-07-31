"""Generation step - emits the TypeScript Playwright test.

The catalog constraint is enforced, not merely requested. Any locator the model
invents is detected by parsing the generated source and fed back for another
attempt. That is the mechanism that lets a small model produce reliable tests:
choosing from a verified list is a far easier task than inventing selectors.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from replayer.catalog import extract_locator_expressions
from replayer.config import WorkflowConfig
from replayer.models import invoke_model
from replayer.specfile import slugify
from replayer.state import RunState

MAX_ATTEMPTS = 5

_TEST_STEP = re.compile(r"\btest\.step\s*\(")
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\n|\n```$")

PROMPT_TEMPLATE = """Write a Playwright test in TypeScript for this specification.

Application under test: {url}
Title: {title}

Specification steps:
{steps}

You may use ONLY these locators, copied exactly as written:
{catalog}

Rules:
- Use `import {{ test, expect }} from '@playwright/test';`
- Navigate with `await page.goto('./');`
- The application starts EMPTY: no data exists until your test creates it.
- Wrap each specification step in `await test.step('...', async () => {{ ... }});`
- Emit exactly {step_count} test.step calls, one per specification step.
- Assert every expected result with `expect`.
- Never write a locator that is not in the list above.
{feedback}
Reply with a single JSON object: {{"test_source": "<the complete .ts file>"}}
"""


def normalise_locator(expression: str) -> str:
    """Compare locators ignoring insignificant whitespace."""
    return re.sub(r"\s+", "", expression)


def parse_test_source(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    source = payload.get("test_source")
    if not isinstance(source, str):
        return ""
    return _CODE_FENCE.sub("", source.strip())


def find_locator_violations(source: str, catalog_expressions: list[str]) -> list[str]:
    """Locators used by the generated test that are not in the catalog."""
    allowed = {normalise_locator(item) for item in catalog_expressions}
    violations: list[str] = []
    for line in source.splitlines():
        for expression in extract_locator_expressions(line):
            if normalise_locator(expression) not in allowed:
                violations.append(expression)
    return sorted(set(violations))


def count_test_steps(source: str) -> int:
    return len(_TEST_STEP.findall(source))


def _render_steps(state: RunState) -> str:
    return "\n".join(
        f"{step.index}. {step.action} -> expected: {step.expected}"
        for step in state.spec_steps
    )


def _render_catalog(state: RunState) -> str:
    """Group locators by availability.

    An element that only exists after an interaction cannot be asserted before
    that interaction has happened. Failing to say so was the single largest
    cause of generated tests that type-checked and still failed.
    """
    at_start = [e.expression for e in state.catalog if e.available_at_start]
    later = [e.expression for e in state.catalog if not e.available_at_start]

    lines: list[str] = []
    lines.append("Present when the page first loads:")
    lines.extend(f"- {expression}" for expression in at_start or ["(none)"])
    if later:
        lines.append("")
        lines.append(
            "Appear only AFTER an interaction creates them - never assert these "
            "before your test has performed the action that produces them:"
        )
        lines.extend(f"- {expression}" for expression in later)
    return "\n".join(lines)


def write_test(state: RunState) -> Path:
    """Persist the generated test next to the hand-written ones."""
    directory = Path("e2e") / "generated"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{slugify(state.spec_title)}.spec.ts"
    path.write_text(state.test_source, encoding="utf-8")
    state.test_path = path.as_posix()
    return path


async def run_generate(state: RunState, config: WorkflowConfig) -> None:
    """Generate a test, then prove it works before handing it on.

    Constraining locators to the catalog removes one class of failure, but not
    wrong assertions: across repeated runs the generator sometimes produced a
    test that type-checked, used only catalog locators, and still failed. So the
    step verifies its own output by executing it, exactly as Playwright's own
    generator agent does, and feeds any failure back for another attempt.

    The retry lives *inside* this executor on purpose. Adding an edge from `run`
    back to `generate` would introduce a branch in the graph, and the absence of
    branches is what makes the step order impossible for a model to influence.
    """
    from replayer.runner import failure_messages, run_playwright

    catalog_expressions = [entry.expression for entry in state.catalog]
    expected_steps = len(state.spec_steps)
    feedback = ""
    source = ""

    for _ in range(MAX_ATTEMPTS):
        prompt = PROMPT_TEMPLATE.format(
            url=state.url,
            title=state.spec_title,
            steps=_render_steps(state),
            catalog=_render_catalog(state),
            step_count=expected_steps,
            feedback=feedback,
        )
        response = await invoke_model(
            step="generate", config=config, prompt=prompt, state=state
        )
        source = parse_test_source(response.text)

        problems = _static_problems(source, catalog_expressions, expected_steps)

        if not problems:
            state.test_source = source
            write_test(state)
            if config.dry_run:
                return
            if run_playwright(state, config):
                return
            problems = [
                "The test was executed and failed: " + message
                for message in failure_messages(state.test_report)
            ] or ["The test was executed and failed for an unknown reason."]

        feedback = (
            "\nYour previous attempt is below. REPAIR it - keep everything that "
            "worked and change only what is needed.\n\n"
            "```typescript\n"
            f"{source}\n"
            "```\n\n"
            "It was rejected because:\n"
            + "\n".join(f"- {problem}" for problem in problems)
            + "\n"
        )

    # Keep the last attempt so the failure is inspectable rather than invisible.
    state.test_source = source
    if source.strip():
        write_test(state)
    raise RuntimeError(
        "Generator could not produce a passing test that respects the catalog "
        f"after {MAX_ATTEMPTS} attempts: {feedback.strip()}"
    )


def _static_problems(
    source: str, catalog_expressions: list[str], expected_steps: int
) -> list[str]:
    """Checks that do not require running the test."""
    if not source.strip():
        return ["The response contained no test source."]

    problems: list[str] = []
    violations = find_locator_violations(source, catalog_expressions)
    if violations:
        problems.append(
            "These locators are not in the catalog and must be replaced: "
            + ", ".join(violations)
        )
    actual_steps = count_test_steps(source)
    if expected_steps and actual_steps != expected_steps:
        problems.append(
            f"Found {actual_steps} test.step calls but the specification has "
            f"{expected_steps} steps."
        )
    return problems
