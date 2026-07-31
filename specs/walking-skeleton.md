# Spec: Walking Skeleton — reproducible test-authoring workflow

> Goal: prove that an explicit, reproducible workflow can drive small models to author a working Playwright test from nothing but a URL.
> Date: 2026-07-31
> Status: Complete (2026-07-31)

---

## What & Why

`GOAL.md` calls for a harness whose value is a **workflow with reproducible steps**, not a set of prompts. Playwright already ships planner/generator/healer as agent definitions; what it does not ship is programmable control flow, per-step model selection, or checkpoints.

This spec builds the thinnest slice that proves the thesis: given a URL, an explicit MAF workflow explores the site, writes a readable spec, generates a Playwright test, runs it, and reports — with the majority of steps executing as plain code and no LLM call.

It is deliberately **not** the whole goal. Maintenance, healing, regression triage, Azure DevOps export and the second harness variant are all excluded.

## Done Looks Like

- Given only `https://demo.playwright.dev/todomvc/`, a single command runs the workflow to completion and exits 0.
- The workflow **chooses for itself** which user flow to test. The flow is not supplied by a human.
- It writes a human-readable spec file as an ADO-style step table, reviewable without reading any code.
- It writes a TypeScript Playwright test whose locators all come from a machine-verified catalog.
- `npx playwright test` runs that generated test and it passes.
- An OpenTelemetry trace shows the same seven executors in the same order on every run, whatever the models answered.
- A run report states, per step, which model was used and how many tokens it cost — with four of seven steps reporting zero.

---

## Scope

### In Scope

- A Python harness built on **Microsoft Agent Framework Workflows**, with seven executors.
- A `playwright-cli` driver layer callable from plain Python code.
- A **locator catalog**: role-based Playwright locators extracted deterministically from snapshots and verified to resolve to exactly one element.
- Three LLM-backed executors (`explore`, `plan`, `generate`), each with an independently configurable model.
- Four code-only executors (`bootstrap`, `catalog`, `run`, `report`) that never call a model.
- Generated tests in **TypeScript**, executed via `npx playwright test` with the JSON reporter.
- Checkpointing, and replay from a checkpoint using recorded LLM responses.
- Per-step token/cost accounting in the run report.

### Out of Scope

- **Test maintenance, healing, regression-vs-intentional-change triage** — *the whole of phase 2; it needs a workflow that produces real failures first.*
- **The `deepagents`/LangGraph variant** — *comparison is worthless until one variant is known to work.*
- **Azure DevOps export** — *format compatibility is a constraint on the spec format now; the integration is a separate deliverable.*
- **Authentication, multi-page journeys, sites behind login** — *TodoMVC has none; adding them here would confound harness bugs with target complexity.*
- **Coverage KPI and trend reporting over time** — *needs many runs across time; meaningless for a single skeleton run.*
- **A UI of any kind** — *CLI plus OTel trace plus written artifacts are sufficient to verify everything in this spec.*
- **Human approval gate on the test plan** — *the goal requires it, but it verifies nothing here; supervision only becomes meaningful once maintenance can change tests behind your back.*
- **Playwright MCP** — *retained as a documented fallback if `playwright-cli` proves insufficient for exploration; not built now.*

---

## Constraints & Assumptions

### Hard Constraints

- **MAF Workflows, Python.** .NET is prerelease; Python core packages are stable.
- **Playwright is the execution layer.** No new browser automation engine.
- **Every step's model is configurable via environment variables**, per step, provider-agnostic. Without this the cost KPI is unmeasurable.
- **Code-only executors must contain no model call.** This is verified, not assumed.
- **The generator may only emit locators present in the catalog.** Verified statically.
- **English only**, per `AGENTS.md`.

### Assumptions

- **A small model can choose the next action from a `find`/`snapshot --depth` view.** *If wrong: the exploration budget grows, or `explore` escalates to a larger model — per-step model config makes this a config change, not a rewrite. This is the assumption most likely to be wrong and is deliberately tested early, in Task 5.*
- **`playwright-cli` snapshots expose stable element refs within a session.** *If wrong: fall back to Playwright MCP, which is why it stays a documented fallback.*
- **Role-based locators on TodoMVC resolve uniquely.** *If wrong: the catalog needs a disambiguation strategy (nth, scoping) — a change confined to Task 3.*
- **`demo.playwright.dev/todomvc/` stays available and stable.** *If wrong: vendor a local copy. This is why the target is a demo app rather than a real site.*

---

## Decisions Already Made

| Decision | Rationale |
|----------|-----------|
| MAF Workflows as the harness | Only candidate giving an explicit graph, typed executors, per-executor model, checkpoint per superstep, native OTel |
| Harness in Python, generated tests in TypeScript | MAF Python is stable; TS is Playwright's native ecosystem for `@playwright/test`, reporters and trace viewer |
| `playwright-cli` as primary browser channel | `find` and `snapshot --depth` return only what is asked for, and ref-based actions are callable from code with no LLM |
| Playwright MCP as documented fallback | Microsoft recommends MCP for exploratory loops; kept as an escape hatch if CLI exploration proves too thin |
| The building block is a verified locator catalog | Turns selector correctness from generation into lookup — the failure mode that most penalises small models |
| Spec format is an ADO-style step table | Native shape of Azure DevOps Test Plans; readable; LLM-updatable row by row |
| Target is `https://demo.playwright.dev/todomvc/` | Stable, public, and the app used by Playwright's own agent documentation |
| Python package named `replayer` | Matches the repository name |
| Reproducibility means fixed executor sequence + checkpoint replay | An LLM is not deterministic; the workflow must be, and the two halves are separately verifiable |

---

## Task Breakdown

### Task 1: Project scaffolding

- **Depends on**: none
- **Description**: Python package `replayer` with a CLI entry point; a TypeScript Playwright project under `tests/` with `@playwright/test` configured for the JSON reporter; dependency manifests for both.
- **Done when**: `replayer --help` exits 0, and `npx playwright test` runs a committed placeholder test to green in a clean checkout.
- **Evaluation**:
  - **Deterministic check**: `replayer --help` → exit 0; `npx playwright test` → exit 0, JSON report written to the configured path.

### Task 2: `playwright-cli` driver

- **Depends on**: Task 1
- **Description**: Python wrappers over `playwright-cli` for `open`, `goto`, `snapshot` (with `--depth`), `find`, `click`, `fill`, `check`, `press`, `close`, with session handling and parsed output. Plain functions — no model involvement.
- **Done when**: a driver call sequence opens TodoMVC, returns a snapshot containing element refs, adds a todo, and closes the session without leaking a browser process.
- **Evaluation**:
  - **Deterministic check**: `pytest tests/test_driver.py` → exit 0; asserts the snapshot contains a textbox role, that an added todo appears in a subsequent snapshot, and that `playwright-cli list` reports no session after teardown.

### Task 3: Locator catalog extractor — the building block

- **Depends on**: Task 2
- **Description**: Build the catalog from two deterministic sources: (a) the YAML accessibility snapshot, whose nodes carry role, accessible name and ref; and (b) the Playwright code `playwright-cli` echoes for every action it executes, e.g. `page.getByRole('textbox', { name: 'What needs to be done?' })`. Verify each candidate against the live page with `find`, keeping only those resolving to exactly one element. Serialise to a catalog artifact.
- **Done when**: a catalog file exists for TodoMVC with at least 5 entries, and every entry is proven to resolve to exactly one element.
- **Evaluation**:
  - **Deterministic check**: `pytest tests/test_catalog.py` → exit 0; asserts `len(catalog) >= 5` and that for every entry the live element count is exactly 1. Any entry resolving to 0 or more than 1 fails the task.

### Task 4: Workflow graph with stub steps

- **Depends on**: Task 1
- **Description**: The seven-executor MAF graph — `bootstrap → explore → catalog → plan → generate → run → report` — wired end to end with the three LLM executors stubbed. Per-executor model configuration read from environment variables. OTel tracing and checkpointing enabled.
- **Done when**: the workflow runs to completion with stubs, and its OTel trace contains exactly seven `executor.process` spans in the defined order.
- **Evaluation**:
  - **Deterministic check**: `pytest tests/test_workflow_shape.py` → exit 0; asserts the ordered executor id sequence from the exported trace equals the expected list, and that `bootstrap`, `catalog`, `run`, `report` emit **zero** model-invocation spans.

### Task 5: `explore` executor

- **Depends on**: Tasks 2, 4
- **Description**: LLM-backed exploration bounded by a maximum number of interactions. Receives a compact page view built with `find` / `snapshot --depth`, chooses the next action, and emits a list of discovered candidate user flows. Model configurable via env.
- **Done when**: from the TodoMVC URL alone, the executor emits at least one candidate flow describing a real, exercisable journey, within the interaction budget.
- **Evaluation**:
  - **Deterministic check**: `pytest tests/test_explore.py` → exit 0; asserts at least one flow is emitted, the interaction budget was not exceeded, and every action issued referenced a ref present in the preceding snapshot.
  - **LLM-as-judge**: Is the discovered flow a genuine user journey for this app? → 1 = unrelated to the app; 2 = names a UI element but not a journey; 3 = plausible journey, vaguely stated; 4 = real journey with a clear start and end; 5 = a journey a tester would prioritise. → Pass ≥ 3.

### Task 6: `plan` executor

- **Depends on**: Task 5
- **Description**: Turn a chosen flow into a spec file: an ADO-style step table with `Test Step | Step Action | Step Expected`, plus a title and a short app description.
- **Done when**: a spec file is written whose table parses, and where every row has a non-empty action and a non-empty expected result.
- **Evaluation**:
  - **Deterministic check**: `pytest tests/test_plan.py` → exit 0; parses the emitted table and asserts ≥ 2 rows, no empty `Step Action`, no empty `Step Expected`, and sequential step numbering.
  - **LLM-as-judge**: Could a human tester execute this spec manually, without reading any code, and know whether it passed? → 1 = incomprehensible; 2 = steps present but expectations missing or untestable; 3 = executable with guesswork; 4 = unambiguous actions and checkable expectations; 5 = also states preconditions and test data. → Pass ≥ 4.

### Task 7: `generate` executor

- **Depends on**: Tasks 3, 6
- **Description**: Emit a TypeScript `@playwright/test` file implementing the spec, using `test.step()` boundaries mirroring the spec rows, and drawing **every** locator from the catalog.
- **Done when**: a `.spec.ts` file is written, it type-checks, and static analysis confirms every locator expression in it appears in the catalog.
- **Evaluation**:
  - **Deterministic check**: `npx tsc --noEmit` → exit 0; `pytest tests/test_generate.py` → exit 0, asserting the set of locator expressions extracted from the generated file is a subset of the catalog, and that the count of `test.step()` calls equals the number of spec rows.

### Task 8: `run` and `report` executors

- **Depends on**: Task 7
- **Description**: Code-only execution of `npx playwright test` with the JSON reporter, parsing of the result, and a run report recording per-step model and token usage alongside the test outcome.
- **Done when**: the full workflow runs from URL to report on TodoMVC, the generated test passes, and the report attributes tokens per step with zero for the four code-only steps.
- **Evaluation**:
  - **Deterministic check**: `replayer run --url https://demo.playwright.dev/todomvc/` → exit 0; the generated test result is `passed` in the JSON report; the run report contains a per-step token table where `bootstrap`, `catalog`, `run`, `report` are exactly 0 and the three LLM steps are greater than 0.

### Task 9: Checkpoint replay

- **Depends on**: Task 8
- **Description**: Record LLM responses during a run; replay the workflow from a checkpoint using those recordings and produce the same artifacts.
- **Done when**: replaying a recorded run reproduces the spec file and the generated test identically, and the executor sequence matches the original.
- **Evaluation**:
  - **Deterministic check**: `pytest tests/test_replay.py` → exit 0; asserts the replayed spec file and generated test are byte-identical to the originals after normalising timestamps and session identifiers, and that the replayed executor sequence equals the original.

---

## Evaluation Criteria

### Deterministic Checks

| Check | Task | How to run | Pass condition |
|-------|------|------------|----------------|
| Entry points work | 1 | `replayer --help`; `npx playwright test` | Both exit 0 |
| Driver round-trip | 2 | `pytest tests/test_driver.py` | Exit 0; no leaked session |
| Catalog uniqueness | 3 | `pytest tests/test_catalog.py` | ≥ 5 entries; every entry resolves to exactly 1 element |
| Executor sequence | 4 | `pytest tests/test_workflow_shape.py` | Trace shows the 7 executors in order |
| Code steps are LLM-free | 4 | `pytest tests/test_workflow_shape.py` | Zero model spans for `bootstrap`, `catalog`, `run`, `report` |
| Exploration is grounded | 5 | `pytest tests/test_explore.py` | ≥ 1 flow; budget respected; every ref existed in the prior snapshot |
| Spec table is well-formed | 6 | `pytest tests/test_plan.py` | ≥ 2 rows; no empty action or expectation; sequential numbering |
| Generated test type-checks | 7 | `npx tsc --noEmit` | Exit 0 |
| Locators come only from the catalog | 7 | `pytest tests/test_generate.py` | Extracted locator set is a subset of the catalog; `test.step()` count equals spec row count |
| End-to-end green | 8 | `replayer run --url https://demo.playwright.dev/todomvc/` | Exit 0; generated test `passed` |
| Cost attribution | 8 | Inspect run report | Four code steps at exactly 0 tokens; three LLM steps above 0 |
| Replay determinism | 9 | `pytest tests/test_replay.py` | Artifacts byte-identical after normalisation; same executor sequence |

### LLM-as-Judge Criteria

| Criterion | Task | Question | Evidence to examine | Scale | Pass boundary |
|-----------|------|----------|---------------------|-------|---------------|
| Flow is a real journey | 5 | Is the discovered flow a genuine user journey for this app? | The emitted flow list and the TodoMVC app | 1 unrelated · 2 element not journey · 3 plausible but vague · 4 clear start and end · 5 a journey a tester would prioritise | ≥ 3 |
| Spec is humanly executable | 6 | Could a tester execute this manually, without reading code, and know if it passed? | The generated spec file only — no code | 1 incomprehensible · 2 expectations missing · 3 executable with guesswork · 4 unambiguous and checkable · 5 also states preconditions and data | ≥ 4 |
| Test reflects the spec | 7 | Does the generated test verify what the spec says, or merely execute the actions? | Spec file and generated test side by side | 1 unrelated · 2 actions only, no assertions · 3 assertions weaker than the spec · 4 every expected result asserted · 5 also covers the implied negative case | ≥ 4 |

### Verification Protocol

- **Adversarial**: the verifying model MUST differ from the implementing model.
- **Process**: the verifier runs every deterministic check, scores every judge criterion with cited evidence, produces pass/fail per criterion, and lists concrete issues for the implementer.
- **Trust nothing self-reported**: a check counts only if its command output is shown. "Tests pass" without an exit code is not evidence — this repository has already been burned by fabricated claims.

### Convergence

- **Quality floor**: every deterministic check passes and every judge criterion meets its pass boundary. Below this the work is not done, regardless of iteration count.
- **Diminishing returns**: stop when the last iteration improved no criterion by more than 10%.
- **Max iterations**: 5. On reaching the limit without clearing the floor, stop and report which criteria failed and why, rather than continuing to spend.

---

## Notes

The riskiest assumption in this spec is that a small model can explore usefully from a `find`-based page view. Task 5 is the earliest point at which the project can learn it is wrong — and per-step model configuration is what makes being wrong cheap.

## Phase 1 verification log (2026-07-31)

External assumptions were checked before implementation began:

| Assumption | Result |
|---|---|
| `@playwright/cli` exists and works | Verified — v0.1.17 installs; `open`, `fill --submit`, `find`, `list`, `close` all confirmed against TodoMVC |
| `@playwright/test` available | Verified — v1.62.1 |
| `agent-framework` supports our Python | Verified — v1.13.0, `requires_python >= 3.10`; environment has 3.12 |
| TodoMVC reachable | Verified — HTTP 200 |
| Snapshots expose stable refs | Verified — YAML accessibility tree with `[ref=eN]`, role and accessible name per node |

**Discovery that improves the design:** `playwright-cli` echoes the exact Playwright code it executed for every action, for example `page.getByRole('textbox', { name: 'What needs to be done?' }).fill('Buy groceries')`. The ref-to-locator mapping is therefore produced by the tool itself rather than inferred by us, which makes the locator catalog verified by construction. Task 3 was updated accordingly.

**Risk noted:** `@playwright/cli` is at version 0.1.17 — very early. Playwright MCP remains the documented fallback.

## Implementation log (2026-07-31)

All nine tasks pass. Suite: 47 pytest tests, `npx tsc --noEmit` clean, `npx playwright test` green, no leaked browser sessions. Verified with Azure OpenAI `gpt-5.4-mini` against the live TodoMVC app.

Representative run cost: `bootstrap` 0, `explore` 2269, `catalog` 0, `plan` 450, `generate` 997, `run` 0, `report` 0 tokens.

### What adversarial review changed

A second model reviewed tasks 1–4 and was right on every count worth acting on:

- **The executor-sequence test was theatre.** It asserted order from a fully deterministic stub, so a model-routed graph would have passed too. Order is now proven by inspecting graph topology without running anything, and by a rogue client that emits `skip`/`goto`/`terminate` directives while the sequence stays fixed.
- **The "zero model spans" assertion was vacuous** because models were globally disabled. All model calls now route through one choke point that records the calling step and raises if a code-only step attempts a call.
- **The catalog was unsound.** Playwright matches accessible names case-insensitively as substrings; our verification compared whole strings. Confirmed on the target: `getByRole('link', { name: 'TodoMVC' })` selects two elements on TodoMVC. Locators now emit `exact: true`, and Playwright itself verifies every entry.

### Flakiness found and fixed

The end-to-end result was initially unreliable: the generated test type-checked, used only catalog locators, and still failed on some runs. Two causes:

1. **The catalog had no notion of availability.** Elements such as the Toggle Todo checkbox and the All/Active/Completed filters exist only after a todo is created, and the generator asserted them on an empty page. Entries now carry `available_at_start` and are presented to the model in two groups.
2. **Retries regenerated from scratch** instead of repairing. The previous source is now fed back for repair, and the attempt limit matches this spec's convergence bound of 5.

The generator also verifies its own output by executing it, mirroring what Playwright's own generator agent does. That retry lives *inside* the `generate` executor deliberately: an edge from `run` back to `generate` would introduce a branch, and the absence of branches is what makes step order impossible for a model to influence.

### Deviations from the spec as written

- Python tests live in `tests/`, generated Playwright tests in `e2e/`. The spec asked for both under `tests/`, which collides with `pytest tests/test_driver.py`.
- Reproducibility is demonstrated by recording and replaying model responses rather than by resuming from a MAF checkpoint id. Checkpoint storage is configured and written; artifact-level determinism is what the check proves.

### Known limitation

Success depends on a stochastic model. Two consecutive full-suite runs passed after the fixes above, which is evidence of repeatability but not proof of it. A larger sample, or a stricter model for `generate`, is the obvious next measurement.
