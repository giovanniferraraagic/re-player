# re-player

A **harness** for a supervised end-to-end testing agent. Given a URL, an explicit workflow explores the application, writes a human-readable test plan, generates a Playwright test, runs it, and reports — with most steps executing as plain code and no LLM call.

## Why

Maintaining E2E tests on a changing site costs so much that teams abandon testing altogether. Playwright already ships `planner` / `generator` / `healer` agents, but they are markdown prompts plus MCP tools: control flow is delegated to whatever LLM client runs them. That means non-reproducible steps, dependence on large models, and no programmable control points.

This project fills that gap: **a workflow with reproducible steps**, where each step runs on the smallest model that can do the job — and four of seven steps run on no model at all.

## Status

Early. The current milestone is the walking skeleton specified in [`specs/walking-skeleton.md`](specs/walking-skeleton.md).

## Layout

| Path | Contents |
|------|----------|
| `src/replayer/` | Python harness (Microsoft Agent Framework Workflows) |
| `e2e/` | Playwright TypeScript tests — the placeholder and generated output |
| `tests/` | pytest suite for the harness |
| `specs/` | Specifications driving implementation |
| `docs/research/` | Verified prior-art research |
| `GOAL.md` | The goal and its decision history |
| `AGENTS.md` | Operating rules for agents working in this repository |

## Requirements

- Python ≥ 3.10
- Node.js ≥ 18
- `@playwright/cli` installed globally: `npm install -g @playwright/cli`

## Getting started

```bash
uv venv
uv pip install -e ".[dev]"
npm install
npx playwright install chromium

replayer --help
```

## License

MIT
