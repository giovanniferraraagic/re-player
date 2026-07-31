# Goal — Harness for a supervised E2E testing agent

> Version 2 (2026-07-31). Recalibrated after prior-art research. See `docs/research/`.

## What & Why

Build an **agent harness** that keeps end-to-end test coverage reliable and runnable over time against the real behaviour of a website.

The real problem: maintaining E2E tests on a changing site costs so much that teams give up on testing altogether.

### Why existing solutions are not enough

Research found that Playwright **v1.56** ships three official Test Agents — `planner`, `generator`, `healer` — covering exploration, a Markdown plan, test generation and repair (`docs/research/00-playwright-test-agents.md`).

But Playwright Test Agents are **agent definitions: markdown prompts plus a list of MCP tools**. They are not a harness. They delegate all control flow to the LLM client that runs them (VS Code, Claude Code, Codex). Consequences:

- **Non-reproducible steps** — the path depends on a runtime model decision, not a defined workflow.
- **High cost** — large models are required, because all reasoning sits in a single generalist loop.
- **Low customisability** — no control over sequence, guardrails, or checkpoints.

**The real gap is the design of a workflow with reproducible steps**, not the prompt.

## Done Looks Like

A harness that:

1. **Defines an explicit, reproducible workflow** with controlled steps, not a free agentic loop.
2. **Assigns each step the smallest model that can do it**, reserving large models for genuinely hard reasoning.
3. **Builds its own reusable building blocks** — the agent produces primitives, helpers and interaction components instead of reasoning from scratch on every run.
4. **Generates tests that follow the identified functional specifications**, not tests disconnected from the plan.
5. **Maintains tests over time**, distinguishing an intentional change from a regression.
6. **Exposes human supervision points** on the test plan.

### Two parallel implementations

| Variant | Base |
|---|---|
| A | **LangChain `deepagents`** |
| B | **Microsoft Agent Framework (MAF)** with Workflows |

They exist to compare two orchestration models on the same problem.

### Success metric

Combined KPI:
- coverage (how much relevant behaviour is tested)
- run stability (reliable tests, not flaky)
- maintenance cost (human effort when the site changes)
- **execution cost** (tokens/models required per cycle)

## Boundaries

- **No new browser automation engine.** Playwright remains the execution layer.
- **Fixing application code is out of scope**: the agent is a tester, not a developer.
- **Adopting existing generalist harnesses as the final solution is out of scope**: too little customisable, too expensive. Playwright Test Agents remain prior art and a possible source of prompts and conventions, not the architectural base.
- **The spec format must be mappable onto external test management systems** (e.g. Azure DevOps Test Plans). Actual integration is out of scope; for now this is only a constraint on format choice.
- **Time horizon is out of scope.**

## Decisions Record

| # | Decision | Origin |
|---|-----------|---------|
| 1 | Primary constraint: automate test orchestration/execution | interview |
| 2 | Two phases, starting with orchestration | interview |
| 3 | First phase extended to planning + execution + maintenance | interview |
| 4 | Maintenance means automatic test modification | interview |
| 5 | Primary responsibility: reliable E2E coverage over time | interview |
| 6 | Metric: combined KPI | interview |
| 7 | No new browser engine; Playwright stays the executor | interview |
| 8 | Time horizon excluded | interview |
| 9 | Fixing application code out of scope | interview |
| 10 | Autonomous browser-based site discovery is part of the goal | review |
| 11 | Human supervision on the test plan; execution and maintenance autonomous | review |
| 12 | Distinguishing intentional change from regression is part of the goal | review |
| 13 | The readable spec is a deliverable, not an internal artifact | review |
| 14 | Spec format must map onto Azure DevOps | review |
| 15 | External integration out of scope: format constraint only | review |
| 16 | **The deliverable is a harness, not a set of prompts** | post-research |
| 17 | **The gap is a workflow with reproducible steps** | post-research |
| 18 | **Two implementations: LangChain deepagents and MAF Workflows** | post-research |
| 19 | **Cost constraint: steps must run on small models** | post-research |
| 20 | **The agent builds its own reusable building blocks** | post-research |

## Open Questions

- What step granularity makes the workflow reproducible without making it rigid?
- Which steps genuinely require an LLM, and which can be deterministic code?
- What exactly are the "building blocks" the agent builds: page objects, custom tools, a reusable interaction library, or parameterised specs?
- Which signals does the workflow use to distinguish a regression from an intentional change (see `docs/research/03-self-healing-and-regression-detection.md`)?
- Canonical spec format: ADO-style step table (recommended in `docs/research/02-test-spec-formats.md`) vs Playwright planner-style Markdown plan.
