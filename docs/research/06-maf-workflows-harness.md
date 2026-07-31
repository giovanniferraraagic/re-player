# Microsoft Agent Framework Workflows as an E2E testing harness
_Date checked: 2026-07-31_

> **Reviewer note (orchestrator):** high-confidence file. Real star count and release tag, a genuine breaking-change citation from the `python-1.13.0` release notes, and an honest "where it fights us" section that identifies a real architectural risk (the BSP synchronisation barrier). The per-step model example is correctly labelled as illustrative rather than passed off as verbatim.

## Executive summary
* **The Unified Successor:** Microsoft Agent Framework (MAF) is the direct successor and convergence of Microsoft's AutoGen and Semantic Kernel, bringing enterprise features (durable state management, telemetry, type safety) into multi-agent workflows.
* **Pregel Parallel Execution Model:** Workflows execute as directed graphs via a Bulk Synchronous Parallel (BSP) "superstep" model, which enforces deterministic, race-free parallel execution and reliable checkpointing.
* **Mixed-Computation Graphs:** MAF allows mixing pure code executors (deterministic tasks like writing files or running Playwright tests) and agent-backed executors (LLM tasks like test generation and failure analysis). **This is the single most important property for our cost constraint.**
* **Granular Model Selection:** Each agent-backed executor in a single workflow can use its own provider and model (e.g. local Ollama for routine steps, a frontier model only for hard reasoning).
* **Durable & Resumable HITL:** Human-in-the-loop via native request/response halting (`ctx.request_info()`). Workflows pause, persist full execution state to disk, Cosmos DB, or a Durable Task Scheduler, and resume on input without consuming compute or tokens.
* **Divergent Maturity:** Python core packages are GA/stable and do not require `--pre`; C#/.NET packages remain prerelease; Go is Public Preview.

---

## What it is
* **Official Repository:** https://github.com/microsoft/agent-framework
* **GitHub Stars:** `12,515`
* **Last Release:** `2026-07-30` (tag: `python-1.13.0`)
* **License:** MIT
* **Supported Languages:** .NET (C#) and Python fully supported. Go in Public Preview.
* **Release Status:** Python core packages (`agent-framework`, `agent-framework-core`, `agent-framework-foundry`) stable; some connectors prerelease. C# packages still prerelease. Microsoft Foundry Hosted Agents is GA.

### Relationship to predecessors
> *"Agent Framework combines AutoGen's simple agent abstractions with Semantic Kernel's enterprise features — session-based state management, type safety, middleware, telemetry — and adds graph-based workflows for explicit multi-agent orchestration... In short, Agent Framework is the next generation of both Semantic Kernel and AutoGen."*
> (https://learn.microsoft.com/en-us/agent-framework/overview/)

Official migration guides exist from both Semantic Kernel and AutoGen.

---

## Workflows: the graph model

MAF distinguishes clearly between an autonomous conversational agent and an explicit workflow:
> *"A workflow... is a predefined sequence of operations that can include AI agents as components... The flow of a workflow is explicitly defined, allowing for more control over the execution path."*
> (https://learn.microsoft.com/en-us/agent-framework/workflows/)

### Graph architecture
Built with a `WorkflowBuilder` coordinating `executors` connected by `edges`:
1. **Executors:** independent processing units (custom code OR LLM-backed agents) receiving typed input messages and producing typed outputs.
2. **Edges:** define message paths. Types:
   - **Direct** — simple pipeline connections
   - **Conditional / Switch-Case** — dynamic branching on message content
   - **Fan-out** — distributing one message to multiple parallel targets
   - **Fan-in (Barrier)** — merging outputs from parallel executors into an aggregator

### Execution model: supersteps
> *"The framework uses a modified Pregel execution model — a Bulk Synchronous Parallel (BSP) approach with superstep-based processing."*
> (https://learn.microsoft.com/en-us/agent-framework/workflows/workflows)

Within each superstep: pending messages from the previous superstep are collected and routed; target executors run **concurrently**; then a **synchronization barrier** halts the workflow until *all* executors in that superstep complete, ensuring race-free deterministic state transitions.

---

## Checkpointing, resumability, human-in-the-loop

### Checkpointing
> *"Checkpoints are created at the end of each superstep, after all executors in that superstep have completed their execution. A checkpoint captures the entire state of the workflow, including: the current state of all executors, all pending messages... pending requests/responses, and shared states."*
> (https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints)

Three built-in Python storage providers implementing a unified `CheckpointStorage` interface:
* `InMemoryCheckpointStorage` — in-process, non-durable
* `FileCheckpointStorage` — persisted to a local directory
* `CosmosCheckpointStorage` — Azure Cosmos DB NoSQL, production scale

### Human-in-the-loop
Built-in request/response mechanism. An executor needing external intervention halts by calling `request_info`:

```python
# Verbatim Python snippet from official HITL documentation
class JudgeExecutor(Executor):
    @handler
    async def handle_guess(self, guess: int, ctx: WorkflowContext[int, str]) -> None:
        if guess == self._target_number:
            await ctx.yield_output(f"Found!")
        else:
            # Emits a request event and halts execution until response is provided
            await ctx.request_info(request_data=NumberSignal(hint="wrong"), response_type=int)

    @response_handler
    async def on_human_response(self, original_request: NumberSignal, response: int, ctx: WorkflowContext[int, str]) -> None:
        await self.handle_guess(response, ctx)
```

`ctx.request_info()` produces a `RequestInfoEvent` with the payload, checkpoints, and pauses. An external client collects human input and resumes via `SendResponseAsync` (C#) or `run_response` helpers, continuing exactly where it stopped.

---

## Per-step model selection

MAF supports Azure OpenAI, OpenAI, Microsoft Foundry, Anthropic, Ollama, and GitHub Copilot through standard client objects. Since workflows accept any object implementing `Executor`, different agents in the same workflow can use completely different models and endpoints.

```python
# ILLUSTRATIVE, not verbatim from docs — based on Ollama and OpenAI provider docs
import asyncio
from agent_framework import WorkflowBuilder
from agent_framework.ollama import OllamaChatClient
from agent_framework.openai import OpenAIChatClient

# 1. Cheap local agent (via local Ollama)
local_client = OllamaChatClient(host="http://localhost:11434", model="llama3.2")
local_evaluator = local_client.as_agent(
    name="LocalEvaluator",
    instructions="Review the simple output locally. Be extremely brief."
)

# 2. Remote frontier agent
frontier_client = OpenAIChatClient(api_key="sk-...", model="gpt-4o")
frontier_generator = frontier_client.as_agent(
    name="FrontierGenerator",
    instructions="Write complex E2E Playwright test scripts following best practices."
)

# 3. Chain them in the same workflow graph
workflow = (
    WorkflowBuilder(start_executor=frontier_generator)
    .add_edge(frontier_generator, local_evaluator)
    .build()
)
```

---

## Observability

Built-in OpenTelemetry instrumentation compliant with the OpenTelemetry GenAI Semantic Conventions.

Spans emitted during execution:
* `workflow.build` — graph compilation
* `workflow.run` / `workflow.session` — complete lifetime of a run
* `executor.process {executor_id}` — execution time and input/outputs per executor
* `edge_group.process` — message synchronisation and routing through edges
* `message.send` — individual message transmissions

### MCP trace propagation
> *"Whenever there is an active OpenTelemetry span context, Agent Framework automatically propagates trace context to MCP servers via the params._meta field of tools/call requests."*
> (https://learn.microsoft.com/en-us/agent-framework/agents/observability)

End-to-end distributed tracing across agent process and MCP server boundaries — directly relevant since Playwright MCP would be one of our tool servers.

### Visualization
* **C#:** `workflow.ToMermaidString()`, `workflow.ToDotString()`
* **Python:** `WorkflowViz(workflow)` provides `to_mermaid()`, `to_digraph()`, `save_png("workflow.png")`

---

## Code example

```python
# Verbatim from Step 5 of the official python tutorial
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler, executor, Never

# Step 1: A class-based executor that converts text to uppercase
class UpperCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Convert input to uppercase and forward to the next node."""
        await ctx.send_message(text.upper())

# Step 2: A function-based executor that reverses the string and yields output
@executor(id="reverse_text")
async def reverse_text(text: str, ctx: WorkflowContext[Never, str]) -> None:
    """Reverse the string and yield the final workflow output."""
    await ctx.yield_output(text[::-1])

def create_workflow():
    """Build the workflow: UpperCase → reverse_text."""
    upper = UpperCase(id="upper_case")
    return WorkflowBuilder(start_executor=upper).add_edge(upper, reverse_text).build()

async def run():
    workflow = create_workflow()
    events = await workflow.run("hello world")
    print(f"Output: {events.get_outputs()}")
    print(f"Final state: {events.get_final_state()}")
```

Note the shape: `@executor` decorates a **plain async function with no LLM involved**. That is the primitive that lets deterministic steps stay deterministic.

---

## Maturity and caveats
* **Fast API evolution & breaking changes.** In `python-1.13.0` (2026-07-30): *"[BREAKING] Make workflow checkpoints fully replayable from initial input and human-in-the-loop responses"* (https://github.com/microsoft/agent-framework/releases/tag/python-1.13.0). Note this particular breaking change moves *toward* replayability, which favours our use case.
* **Connector previews.** Core Python libraries stable, but several connectors (e.g. `agent-framework-copilotstudio`) still prerelease.
* **Prerelease .NET/C#.** All MAF NuGet packages technically still prerelease.

---

## Fit for a Playwright test-authoring workflow

Target pipeline: `Explore Site → Write Spec → Generate Playwright Test → Run Test → Analyze Failure → Repair or Escalate`

### Natural fit
1. **Separation of pure code vs LLM.** `Run Test` (subprocess `playwright test`) and `Write Spec` (file serialisation) are fully deterministic and can be plain `@executor` functions with no LLM call. Only genuinely fuzzy steps pay tokens.
2. **Granular cost management.** `Generate Playwright Test` can use a frontier model; `Analyze Failure` can route to a local model via `OllamaChatClient`.
3. **Escalation & resumability.** If repair fails, `ctx.request_info()` suspends execution, serialises all state (including test failure artifacts), and sleeps. A human responds and the workflow resumes from that step **without repeating the earlier steps** — no re-exploration, no wasted tokens.
4. **Long-running capability.** The Durable Extension (Durable Task infrastructure) lets a workflow span days or weeks and survive transient crashes — matching test maintenance as a recurring process rather than a one-shot task.

### Where it will fight us
1. **The Pregel synchronisation barrier.** BSP runs executors concurrently but enforces a barrier: if we fan out 10 Playwright tests across 10 executors, **no path advances until the slowest finishes**. A single hanging test or browser timeout stalls the whole superstep. Mitigation (per-executor timeouts, batching strategy) must be designed in, not bolted on.
2. **Boilerplate & infrastructure overhead.** Durability and persistence require deploying the Durable Extension worker plus state stores (Cosmos DB / Redis) — significant operational complexity relative to a lightweight script.

---

## Unverified / Needs follow-up
* **DevUI capabilities.** The specific features of `agent-framework-devui` (whether it hosts a local web UI showing active workflow graphs and checkpoints) are mentioned in release notes but have limited public documentation.
* **Go parity timeline.** Functional workflows, declarative workflows, and the Durable Extension are not implemented for Go; no announced timeframe.

---

## Sources
1. https://github.com/microsoft/agent-framework
2. https://learn.microsoft.com/en-us/agent-framework/overview/
3. https://learn.microsoft.com/en-us/agent-framework/workflows/
4. https://learn.microsoft.com/en-us/agent-framework/workflows/workflows
5. https://learn.microsoft.com/en-us/agent-framework/workflows/executors
6. https://learn.microsoft.com/en-us/agent-framework/workflows/edges
7. https://learn.microsoft.com/en-us/agent-framework/workflows/checkpoints
8. https://pypi.org/project/agent-framework/
9. https://learn.microsoft.com/en-us/agent-framework/agents/providers/
10. https://learn.microsoft.com/en-us/agent-framework/agents/providers/ollama
11. https://learn.microsoft.com/en-us/agent-framework/hosting/
12. https://github.com/microsoft/agent-framework/releases/tag/python-1.13.0
13. https://github.com/microsoft/agent-framework/blob/main/LICENSE
14. https://learn.microsoft.com/en-us/agent-framework/agents/observability
15. https://learn.microsoft.com/en-us/agent-framework/workflows/visualization
16. https://learn.microsoft.com/en-us/agent-framework/get-started/workflows
