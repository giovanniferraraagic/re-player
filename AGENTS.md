# AGENTS.md

Operating context for AI agents working in this repository. Keep it short. If something here is longer than it needs to be, cut it.

## What this repo is

A **harness** for a supervised E2E testing agent. The agent explores a website, writes a human-readable test plan, generates Playwright tests, runs them, and maintains them as the site changes.

Full goal and decision history: `GOAL.md`. Research evidence: `docs/research/README.md`.

## Non-negotiable constraints

1. **The deliverable is a harness, not a set of prompts.** Playwright v1.56 already ships `planner`/`generator`/`healer` agents — but they are markdown prompts + MCP tools with LLM-decided control flow. The gap we fill is **reproducible workflow steps**.
2. **No new browser automation engine.** Playwright is the execution layer.
3. **Cost is a design constraint.** Every step runs on the smallest model that can do it. Deterministic steps must be plain code with no LLM call.
4. **Never auto-heal assertions.** Locator repair is allowed; changing an expected value silently converts a real bug into a green test. Failed assertions and server errors escalate — they do not get repaired.
5. **The agent does not fix application code.** It is a tester, not a developer.

## Architecture direction

Two harness variants under evaluation:

- **A** — LangGraph / `deepagents` (LangChain). Better suited to exploratory authoring, where the path is not known in advance.
- **B** — Microsoft Agent Framework Workflows. Explicit graph, typed executors, per-executor model selection, checkpoint per superstep. Better suited to reproducible execution and maintenance.

These may be phases of one system rather than competing products. Do not assume an either/or without evidence.

Canonical spec format: **Azure DevOps-style step tables** (`Test Step | Step Action | Step Expected`). Playwright is the executable derivative; mirror step boundaries with `test.step()`.

## Working rules

- **English only.** Every artifact in this repository — docs, code, comments, commit messages, spec files, agent output — is written in English, regardless of the language the request came in.
- **`docs/research/` holds verified material only.** Every claim must trace to a fetched source. Star counts, version numbers and feature claims are checked, never estimated. Anything that cannot be verified is **deleted**, not committed with a caveat; open leads may be listed as leads, never as findings.
- **Challenge cheap model output.** Research delegated to small models has produced fabricated citations and star counts wrong by an order of magnitude in this repo. A verification pass is mandatory, not optional.
- **Measure before concluding.** Reliability claims come from `scripts/measure_reliability.py` over several runs, never from one observation. This repo once recorded "fails half the time" as a property of the product when the cause was self-inflicted test interference.
- **`playwright-cli close-all` is global.** Never run it, or any other whole-machine browser command, while a workflow or measurement is in flight — it will kill that run and the failure will look like a product defect.
- **Conventional commits.** Branch for changes; ask before pushing or opening a PR.

## Agent skills

### Issue tracker

Issues live in GitHub Issues for `giovanniferraraagic/re-player`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Maintaining this file

This file is maintained by the agents that work here. Update it in the same change that makes it stale — never as a follow-up task.

**Update when:**
- A constraint or architectural decision changes, or a new one is confirmed with the user.
- A variant (A/B) is chosen, dropped, or the relationship between them changes.
- A convention is established that a future agent would otherwise have to rediscover.
- A recurring mistake is identified and a rule prevents it from recurring.
- Directory layout, entry points, or the build/test commands change.

**Do not add:**
- Research findings — those belong in `docs/research/`.
- Task status, plans, or history — those belong in `GOAL.md` or the tracker.
- Anything already obvious from reading the code.

**When updating:** replace stale lines rather than appending. If this file grows past roughly one screen, something in it has stopped being essential — remove it.
