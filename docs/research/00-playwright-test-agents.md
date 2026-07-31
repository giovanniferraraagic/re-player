# Playwright Test Agents — verified primary-source findings

**Verified by the orchestrator directly against primary sources on 2026-07-31.**
A sub-agent claimed twice that this feature does not exist. It does. That sub-agent's output was removed from this repository as unverified; this file records what the official documentation actually says.

---

## The finding

Playwright ships **three official Test Agents** out of the box: **planner**, **generator**, **healer**. They were introduced in **Playwright v1.56**.

Verbatim from the official release notes (https://playwright.dev/docs/release-notes, section "Version 1.56"):

> **Playwright Test Agents**
> Introducing Playwright Test Agents, three custom agent definitions designed to guide LLMs through the core process of building a Playwright test:
> - 🎭 **planner** explores the app and produces a Markdown test plan
> - 🎭 **generator** transforms the Markdown plan into the Playwright Test files
> - 🎭 **healer** executes the test suite and automatically repairs failing tests

Verbatim from the docs (https://playwright.dev/docs/test-agents):

> Playwright comes with three Playwright Test Agents out of the box: 🎭 planner, 🎭 generator and 🎭 healer.
> These agents can be used independently, sequentially, or as the chained calls in the agentic loop. Using them sequentially will produce test coverage for your product.

Installation is a single command, with first-class support for several agent runtimes:

```bash
npx playwright init-agents --loop=vscode
npx playwright init-agents --loop=claude
npx playwright init-agents --loop=codex
npx playwright init-agents --loop=opencode
```

---

## Why this matters: it maps almost 1:1 onto our stated goal

| Our goal (from `GOAL.md`) | Playwright Test Agents |
|---|---|
| Autonomously explore the site with a browser | **planner** — "explores the app" |
| Readable test plan / spec as the supervision interface | **planner** — "produces a Markdown test plan", saved to `specs/*.md`, "human-readable but precise enough for test generation" |
| Generate Playwright tests from the spec | **generator** — "transforms the Markdown plan into the Playwright Test files" |
| Automatically maintain tests when the site changes | **healer** — "executes the test suite and automatically repairs failing tests" |
| Distinguish a regression from an intentional change | **healer** — partially; see below |

### The healer, verbatim

> When the test fails, the healer agent:
> - Replays the failing steps
> - Inspects the current UI to locate equivalent elements or flows
> - Suggests a patch (e.g., locator update, wait adjustment, data fix)
> - Re-runs the test until it passes or until guardrails stop the loop
>
> **Output**
> - A passing test, **or a skipped test if the healer believes that functionality is broken.**

That last line is the important one. Playwright's healer **already attempts the regression-vs-intentional-change distinction**: if it concludes the functionality is genuinely broken, it skips the test rather than healing it into a green lie. This is precisely the safety property we identified as the crux of the project (see `03-self-healing-and-regression-detection.md`).

---

## Artifacts and conventions Playwright already imposes

From https://playwright.dev/docs/test-agents:

- `specs/` — "structured plans describing scenarios in human-readable terms. They include steps, expected outcomes, and data. Specs can start from scratch or extend a seed test."
- `tests/` — "Generated Playwright tests, aligned one-to-one with specs wherever feasible."
- `seed.spec.ts` — "Seed tests provide a ready-to-use `page` context to bootstrap execution." The planner runs the seed test to perform global setup, fixtures and hooks before exploring.
- Agent definitions are "collections of instructions and MCP tools ... provided by Playwright and should be regenerated whenever Playwright is updated."

The spec format is **Markdown with numbered steps and bulleted expected outcomes** — not Gherkin. Example structure from the docs (TodoMVC plan): a prose overview of the app's key features, a `**Seed:** tests/seed.spec.ts` reference, then numbered scenarios where each step lists its expected outcomes.

---

## Implications for this project — read before writing any code

1. **The core loop is not a greenfield problem.** Planner → generator → healer already exists, is maintained by Microsoft, and is versioned with Playwright itself.
2. **Our differentiators must be elsewhere.** Candidate areas the official agents do NOT cover, to be validated:
   - Deciding *what* is worth testing at a product/coverage level, and tracking coverage over time (KPI).
   - Orchestration across runs and over time: scheduling, triage of failures, trend reporting.
   - The supervision workflow: approving/versioning the test plan, audit trail of what the healer changed and why.
   - Export/mapping of specs to external test management (Azure DevOps) — see `02-test-spec-formats.md`.
   - Guardrail policy on what the healer may and may not touch — see `03-self-healing-and-regression-detection.md`.
3. **Anything we build should start by adopting `init-agents` and measuring where it falls short**, rather than reimplementing planner/generator/healer.

---

## Sources (fetched directly, 2026-07-31)

1. https://playwright.dev/docs/test-agents — Playwright Test Agents documentation (planner, generator, healer, artifacts, seed tests)
2. https://playwright.dev/docs/release-notes — "Version 1.56 → Playwright Test Agents" release note confirming the version they shipped in
