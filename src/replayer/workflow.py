"""The replayer workflow.

Seven executors run in a fixed order:

    bootstrap -> explore -> catalog -> plan -> generate -> run -> report

Four of them - bootstrap, catalog, run, report - are plain code and never touch
a language model. The graph, not the model, decides the sequence: that is the
property this project exists to demonstrate.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent_framework import (
    FileCheckpointStorage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)

from replayer.config import EXECUTOR_SEQUENCE, WorkflowConfig
from replayer.state import RunState


def build_workflow(config: WorkflowConfig) -> Workflow:
    """Build the seven-executor graph for a given configuration."""

    artifacts = Path(config.artifacts_dir)
    artifacts.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- code step
    @executor(id="bootstrap")
    async def bootstrap(state: RunState, ctx: WorkflowContext[RunState]) -> None:
        """Open the target application and take the first snapshot. No model."""
        if not config.dry_run:
            from replayer.driver import PlaywrightCliDriver

            with PlaywrightCliDriver(config.session) as driver:
                result = driver.open(state.url)
                state.observed_code.extend(result.code_lines)
                state.snapshots.append(driver.snapshot())
        state.record_usage("bootstrap")
        await ctx.send_message(state)

    # ----------------------------------------------------------------- llm step
    @executor(id="explore")
    async def explore(state: RunState, ctx: WorkflowContext[RunState]) -> None:
        """Choose what is worth testing. Backed by a model unless stubbed."""
        from replayer.steps.explore import run_explore

        await run_explore(state, config)
        await ctx.send_message(state)

    # ---------------------------------------------------------------- code step
    @executor(id="catalog")
    async def catalog(state: RunState, ctx: WorkflowContext[RunState]) -> None:
        """Derive and verify role-based locators. Pure code, no model."""
        from replayer.catalog import build_catalog

        build_catalog(state, config)
        state.record_usage("catalog")
        await ctx.send_message(state)

    # ----------------------------------------------------------------- llm step
    @executor(id="plan")
    async def plan(state: RunState, ctx: WorkflowContext[RunState]) -> None:
        """Write the human-readable spec. Backed by a model unless stubbed."""
        from replayer.steps.plan import run_plan

        await run_plan(state, config)
        await ctx.send_message(state)

    # ----------------------------------------------------------------- llm step
    @executor(id="generate")
    async def generate(state: RunState, ctx: WorkflowContext[RunState]) -> None:
        """Emit the TypeScript test. Backed by a model unless stubbed."""
        from replayer.steps.generate import run_generate

        await run_generate(state, config)
        await ctx.send_message(state)

    # ---------------------------------------------------------------- code step
    @executor(id="run")
    async def run(state: RunState, ctx: WorkflowContext[RunState]) -> None:
        """Execute the generated test with Playwright. Pure code, no model."""
        from replayer.runner import run_playwright

        if not config.dry_run:
            run_playwright(state, config)
        state.record_usage("run")
        await ctx.send_message(state)

    # ---------------------------------------------------------------- code step
    @executor(id="report")
    async def report(state: RunState, ctx: WorkflowContext) -> None:
        """Write the run report, including per-step token attribution. No model."""
        state.record_usage("report")
        path = artifacts / "run-report.json"
        payload = {
            "url": state.url,
            "spec_path": state.spec_path,
            "test_path": state.test_path,
            "test_passed": state.test_passed,
            "catalog_size": len(state.catalog),
            "flows": [flow.title for flow in state.flows],
            "usage": {
                step: {
                    "model": usage.model,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "total_tokens": usage.total_tokens,
                }
                for step, usage in state.usage.items()
            },
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        state.report_path = str(path)
        await ctx.yield_output(state)

    checkpoint_storage = FileCheckpointStorage(config.checkpoint_dir)

    return (
        WorkflowBuilder(start_executor=bootstrap, checkpoint_storage=checkpoint_storage)
        .add_edge(bootstrap, explore)
        .add_edge(explore, catalog)
        .add_edge(catalog, plan)
        .add_edge(plan, generate)
        .add_edge(generate, run)
        .add_edge(run, report)
        .build()
    )


async def execute(config: WorkflowConfig) -> RunState:
    """Run the workflow to completion and return the final state."""
    workflow = build_workflow(config)
    initial = RunState(url=config.url, session=config.session)
    result = await workflow.run(initial)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError("Workflow produced no output")
    return outputs[-1]


def run_workflow(url: str, session: str = "replayer") -> int:
    """Entry point used by the CLI. Returns a process exit code."""
    import asyncio

    config = WorkflowConfig.from_env(url=url, session=session)
    state = asyncio.run(execute(config))

    print(f"Spec:   {state.spec_path}")
    print(f"Test:   {state.test_path}")
    print(f"Report: {state.report_path}")
    for step in EXECUTOR_SEQUENCE:
        usage = state.usage.get(step)
        tokens = usage.total_tokens if usage else 0
        model = (usage.model if usage else None) or "-"
        print(f"  {step:<10} tokens={tokens:<7} model={model}")

    return 0 if state.test_passed else 1

