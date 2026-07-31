# LangChain deepagents as an E2E testing harness
_Date checked: 2026-07-31_

> **Reviewer note (orchestrator):** high-confidence file. The sub-agent pulled facts from the GitHub API and PyPI JSON rather than estimating, read the actual `graph.py` source, and cited three real open issues. The key answer to our architectural question is in "Control flow, reproducibility" — read that section first.

## Executive summary
- `deepagents` is LangChain's Python harness repo (`langchain-ai/deepagents`), not a new runtime: it wraps LangChain/LangGraph, ships at version `0.7.1`, is MIT-licensed, has 27,159 GitHub stars, and the latest release/commit found are `2026-07-30` / `2026-07-31T06:01:01Z` respectively. (https://github.com/langchain-ai/deepagents, https://api.github.com/repos/langchain-ai/deepagents, https://pypi.org/pypi/deepagents/json)
- It is an opinionated agent harness with built-in filesystem, subagents, context management, planning, and HITL, but the core loop is still LLM/tool-calling driven; `create_deep_agent` assembles middleware and then returns a compiled LangChain/LangGraph graph. (https://docs.langchain.com/oss/python/deepagents/overview.md, https://raw.githubusercontent.com/langchain-ai/deepagents/main/libs/deepagents/deepagents/graph.py)
- Reproducibility is partial: you can checkpoint, resume by `thread_id`, and gate tool calls with interrupts, but Deep Agents does not expose a fixed step DSL; the model still decides when to plan, delegate, or fan out.
- Per-step model choice is supported at the subagent level (`model=` on `SubAgent`, or arbitrary `CompiledSubAgent`/async subagents), not as a built-in per-tool router for the main loop.
- For a Playwright harness, it fits best as an orchestration layer around tools (browser actions, file writes, test runner, repair) plus subagents and approval gates; **it fights you if you need a rigid, reproducible workflow engine.**

## What it is
- **Repo**: `https://github.com/langchain-ai/deepagents`
- **Language**: Python
- **License**: MIT
- **Stars**: 27,159
- **Open issues**: 183
- **Current version**: `0.7.1`
- **Latest release**: `deepagents==0.7.1`, published `2026-07-30T20:34:46Z`
- **Latest commit on `main`**: `bebafaa0c8331af27665ac09461111ba8c75ad7f`, authored `2026-07-31T06:01:01Z`

> PyPI summary: "General purpose 'deep agent' with sub-agent spawning, todo list capabilities, and mock file system. Built on LangGraph." (https://pypi.org/pypi/deepagents/json)

## Architecture and primitives
- **Planning / todo list**: opt-in only in v0.7; `TodoListMiddleware` adds a `write_todos` tool, and tasks persist in agent state with `pending` / `in_progress` / `completed`.
  > "Pass `TodoListMiddleware` to the middleware parameter to give the agent a `write_todos` tool…"
  > "Tasks support status tracking … and are persisted in agent state."
  (https://docs.langchain.com/oss/python/deepagents/overview.md)
- **Virtual filesystem**: a pluggable virtual filesystem backed by in-memory state, local disk, LangGraph store, composite routing, or custom backends; built-in ops include `ls`, `read_file`, `write_file`, `edit_file`, `delete`, `glob`, `grep`, `execute`.
  > "The harness provides a configurable virtual filesystem…"
- **Subagents / context isolation**:
  > "Fresh context: Each invocation creates a new agent instance with its own context."
  > "Stateless messaging: Subagents are stateless and cannot send multiple messages back."
  > "Skill state is fully isolated—a subagent's loaded skills are not visible to the parent, and vice versa."
  (https://docs.langchain.com/oss/python/deepagents/subagents.md)
- **System-prompt design**: caller prompt first, profile base in the middle, suffix last.
  > "The final authored prompt is assembled as `USER` -> `BASE` -> `SUFFIX`."
  (https://raw.githubusercontent.com/langchain-ai/deepagents/main/libs/deepagents/deepagents/graph.py)
- **LangGraph relation**: Deep Agents is a harness on top of LangChain/LangGraph, not its own scheduler.
  > "It uses the LangGraph runtime for durable execution, streaming, human-in-the-loop, and other features."
  > `create_deep_agent(...).with_config(...)` returns a compiled graph after calling `create_agent(...)`.

## Control flow, reproducibility, human-in-the-loop

**This is the decisive section for our project.**

- **Can you pin the exact sequence?** Not really. The harness is still model-driven.
  > "Deep Agents is an 'agent harness'… same core tool calling loop as other agent frameworks"
  > "Dynamic dispatch is implicit: the agent decides to fan work out from code based on the shape of the task, not a per-call flag."
  (https://docs.langchain.com/oss/python/deepagents/overview.md, https://docs.langchain.com/oss/python/deepagents/subagents.md)
- **Checkpointing / resumability**: yes. `create_deep_agent` exposes `checkpointer`, and production docs say `thread_id` scopes message history + checkpoints.
  > "`thread_id` scopes the conversation (message history, checkpoints)."
  > `create_deep_agent(..., checkpointer: Checkpointer | None = None, store: BaseStore | None = None, ...)`
- **Human approval gates**: yes, via `interrupt_on`; `HumanInTheLoopMiddleware` is added automatically when set.
  > "Deep Agents support human-in-the-loop workflows through LangGraph's interrupt capabilities."
  > "`interrupt_on={"edit_file": True}` pauses before every edit…"
  > "Checkpointer is REQUIRED for human-in-the-loop"
  (https://docs.langchain.com/oss/python/deepagents/human-in-the-loop.md)
- **Durable state**: yes, via LangGraph runtime + checkpointer/store + thread-scoped state; also exposes `state_schema` and `context_schema`.
- **Bottom line**: reproducible *pauses* and *resume points* are supported; reproducible *agent step ordering* is not the default abstraction. **If you need a fixed workflow, the docs point you to a custom LangGraph workflow instead.** (https://docs.langchain.com/oss/python/deepagents/customization.md)

## Per-step model selection
- **Yes, but at subagent granularity**:
  > `model` is "Optional. Overrides the main agent's model."
  > "Tasks requiring different model capabilities" is a listed reason to use subagents.
  (https://docs.langchain.com/oss/python/deepagents/subagents.md)
- **Also yes via compiled subgraphs**: `CompiledSubAgent` accepts any compiled LangGraph runnable, so the subagent can be built around any model stack you want.
- **Async subagents are separate deployments** and can be pointed at different graph IDs / URLs, so they can also use different models behind the scenes.
- **No built-in per-step router** for the main loop; the main agent itself still has one `model=`.

## Custom tools
Deep Agents accepts plain callables, LangChain tools, dict tools, and MCP server tools.
> "Pass any callable … directly to `tools=`."
> "Deep Agents fully support Model Context Protocol (MCP)…"
(https://docs.langchain.com/oss/python/deepagents/tools.md)

Docs example:
```python
import os
from typing import Literal
from tavily import TavilyClient
from deepagents import create_deep_agent

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search"""
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )

agent = create_deep_agent(
    model="openai:gpt-5.5",
    tools=[internet_search],
)
```

## Maturity and caveats
- PyPI marks it **Development Status :: 4 - Beta**.
- Feature churn is explicit:
  - async subagents are a **preview feature**
  - dynamic subagents are **beta**
  - task planning moved to **opt-in** in v0.7
  - `model=None` is deprecated
  - `BASE_AGENT_PROMPT` is deprecated and slated for removal
- Security model is intentionally permissive:
  > "Deep Agents follows a 'trust the LLM' model. The agent can do anything its tools allow."
- Open bugs worth noting:
  - `#5136` subagent checkpoints are written but history is unreadable (`Subgraph tools not found`)
  - `#5113` delete permission ordering bug
  - `#5112` shell-safe grep issue in sandbox path globs
- Net: usable, active, but not "stable API frozen" territory.

## Fit for a Playwright test-authoring workflow
Good fit if you want:
- site exploration via tools
- spec/test-file writing via filesystem
- test execution via `execute` (sandbox backend)
- analysis/repair via subagents
- approval gates on destructive edits or reruns via `interrupt_on`

Where it fights you:
- the default loop is still LLM-decided, so a fixed sequence like `explore → write spec → generate test → run → analyze → repair/escalate` is **not guaranteed** unless you build that sequence yourself in LangGraph
- planning (`write_todos`) is advisory/stateful, not a deterministic orchestrator
- subagents are intentionally stateless one-shots, so mid-flight stepwise coordination needs async subagents or your own graph

**Practical verdict:** use Deep Agents as a harness around Playwright tools if you want agentic execution with checkpoints and approvals; **do not use it if you need a reproducible, model-minimal, stage-by-stage workflow engine** — for that, drop to LangGraph directly.

## Unverified / Needs follow-up
- Crash/restart behaviour on a real backend was not independently benchmarked; the docs show resumability, but operational guarantees depend on the selected checkpointer/store/backend.
- LangGraph's own docs were not fetched directly; control-flow conclusions are based on Deep Agents docs + source.

## Sources
1. https://github.com/langchain-ai/deepagents
2. https://api.github.com/repos/langchain-ai/deepagents
3. https://api.github.com/repos/langchain-ai/deepagents/releases/latest
4. https://api.github.com/repos/langchain-ai/deepagents/commits?per_page=1
5. https://pypi.org/pypi/deepagents/json
6. https://docs.langchain.com/oss/python/deepagents/overview.md
7. https://docs.langchain.com/oss/python/deepagents/customization.md
8. https://docs.langchain.com/oss/python/deepagents/subagents.md
9. https://docs.langchain.com/oss/python/deepagents/human-in-the-loop.md
10. https://docs.langchain.com/oss/python/deepagents/going-to-production.md
11. https://docs.langchain.com/oss/python/deepagents/profiles.md
12. https://docs.langchain.com/oss/python/deepagents/tools.md
13. https://docs.langchain.com/oss/python/deepagents/async-subagents.md
14. https://raw.githubusercontent.com/langchain-ai/deepagents/main/libs/deepagents/deepagents/graph.py
15. https://github.com/langchain-ai/deepagents/issues/5136
16. https://github.com/langchain-ai/deepagents/issues/5113
17. https://github.com/langchain-ai/deepagents/issues/5112
