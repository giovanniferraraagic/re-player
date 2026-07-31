# Research

Evidence gathered on **2026-07-31** by parallel sub-agents on cheap models (Haiku 4.5, Gemini 3.5/3.6 Flash, GPT-5.4 mini), then cross-checked by the orchestrator.

**Everything in this directory is traceable to a fetched source.** Unverifiable material is removed, not kept with a caveat. See `AGENTS.md`.

## Index

| File | Topic |
|---|---|
| `00-playwright-test-agents.md` | Playwright Test Agents (planner / generator / healer) |
| `01-browser-agent-tooling.md` | Tooling that lets an LLM drive a browser |
| `02-test-spec-formats.md` | E2E spec formats and Azure DevOps mapping |
| `03-self-healing-and-regression-detection.md` | Self-healing and the regression-vs-intentional-change problem |
| `04-deepagents-harness.md` | LangChain `deepagents` as a harness |
| `05-maf-workflows-harness.md` | Microsoft Agent Framework Workflows as a harness |

## What was removed and why

A prior-art survey of AI E2E testing products was **deleted**. Its star counts were fabricated (it reported "3K+" for a repository with 107k stars), it denied twice that Playwright Test Agents exist, and its commercial-vendor claims could not be tied to fetched pages. Its only verified content overlapped with `01-browser-agent-tooling.md`.

Vendor names it surfaced remain useful as **leads to verify**, not as findings: Autify, Katalon, Testsigma, Meticulous, Momentic, Testim, Reflect, QA.tech, mabl, Rainforest, Virtuoso, testRigor, Ranorex, TestComplete, Functionize.

Two other corrections were applied: a fabricated IEEE TSE citation in `03-` was replaced with three real papers after a challenge round, and a fabricated explanation of GitHub star counts in `01-` was removed (the numbers themselves were correct and have been re-verified against the GitHub API).

**Operational lesson, now a repository rule: cheap-model research requires a mandatory verification pass. It cannot be trusted on delivery.**

---

## Conclusions that matter for the project

### 1. Prior art exists, but it is not a harness

Playwright v1.56 ships `planner` / `generator` / `healer`. They cover exploration to Markdown plan to tests to repair. **But they are agent definitions: markdown prompts plus MCP tools.** Control flow is delegated to whatever LLM client runs them (VS Code, Claude Code, Codex).

Consequences: non-reproducible steps, dependency on large models, no programmable control points.

**Worth reusing anyway:** the conventions (`specs/` + `tests/` layout, the seed test as context bootstrap, the plan format) are sound and battle-tested. There is no reason to reinvent them.

### 2. The cost-control pattern is known and documented

Separate the two phases cleanly:

```
AUTHORING     LLM-heavy, exploratory, expensive
     |        emits reproducible artifacts
     v
EXECUTION     deterministic, CI, near-zero tokens
              LLM invoked ONLY when something actually breaks
```

Concrete reference: **Stagehand** (Browserbase) — *"auto-caching combined with self-healing remembers previous actions, runs without LLM inference, and knows when to involve AI"*. This is exactly the "building blocks" idea: the first run reasons, subsequent runs replay.

### 3. Comparing the two harness candidates

| Criterion | `deepagents` (LangChain) | MAF Workflows (Microsoft) |
|---|---|---|
| Step order pinnable | No — model-driven loop; docs point to LangGraph instead | Yes — explicit graph, `WorkflowBuilder`, conditional edges |
| Deterministic steps without an LLM | Partial — tools yes, but orchestration stays agentic | Yes — `@executor` on a plain function, zero LLM |
| Checkpoint / resume | Yes — checkpointer + `thread_id` | Yes — every superstep, full state |
| Human-in-the-loop | Yes — `interrupt_on` | Yes — `ctx.request_info()` with precise resume |
| Per-step model | Partial — sub-agent granularity | Yes — per executor, different providers allowed |
| Observability | LangSmith | Native OpenTelemetry, span per executor, propagation to MCP |
| Maturity | 0.7.1, beta, declared churn | Python stable, .NET prerelease, active breaking changes |
| Main risk | Does not guarantee reproducibility | BSP barrier: one slow test stalls the whole superstep |

**Reading:** against the stated requirement — *reproducible steps and small models per step* — **MAF Workflows is on paper the closer fit**. `deepagents` suits the exploratory authoring phase, where the path is not known in advance.

Hypothesis to validate: **this is not necessarily either/or.** Exploratory authoring (deepagents/LangGraph) plus reproducible execution and maintenance (MAF Workflows) could be two phases of one system rather than competing products.

### 4. Non-negotiable safety constraint

No existing tool autonomously distinguishes a regression from an intentional change. Every serious one repairs **locators only**, never assertions. Playwright's `healer` is the only one that claims to skip a test when it believes the functionality is broken.

Derived tier policy (detail in `03-`):

| Tier | Case | Action |
|---|---|---|
| 0 | Broken locator, high confidence | Repair, log |
| 1 | UI refactor / changed flow / low confidence | Propose a patch, do not apply |
| 2 | **Failed assertion, server error** | **Fail. Never repair.** |

Signals available for the distinction: failure type (locator vs assertion), blast radius (1 test vs 40), the application's git/PR context, visual baselines, semantic similarity, confidence thresholds.

### 5. Recommended spec format

**Azure DevOps-style step tables** (`Test Step | Step Action | Step Expected`): readable, generable and updatable row-by-row by an LLM, and the native import/export format of ADO Test Plans. Playwright stays the executable derivative, with `test.step()` mirroring step boundaries.

To be built: a deterministic converter between the Playwright planner's Markdown plan and the ADO table. Small, concrete, and clearly the harness's job.

---

## Open questions

- Step granularity: how fine before the workflow becomes rigid?
- Which steps genuinely need an LLM, and which are deterministic code?
- What exactly are the reusable "building blocks": page objects, custom tools, a Stagehand-style action cache, or parameterised specs?
- Is MAF's BSP barrier a real problem for our workload, or is it mitigated by per-executor timeouts?
