"""State carried between workflow executors.

A single typed message travels the whole chain. Each executor adds its own
contribution and records what it cost, so the run report can attribute tokens
per step and prove that the code-only steps spent nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class StepUsage:
    """What one executor consumed."""

    step: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class SnapshotNode:
    """One node of a playwright-cli accessibility snapshot."""

    role: str
    name: str | None
    ref: str | None
    depth: int


@dataclass
class LocatorEntry:
    """A verified, role-based Playwright locator."""

    expression: str
    role: str
    name: str | None
    ref: str | None = None
    match_count: int = 0


@dataclass
class SpecStep:
    """One row of an Azure DevOps style step table."""

    index: int
    action: str
    expected: str


@dataclass
class FlowCandidate:
    """A user journey the explorer thinks is worth testing."""

    title: str
    rationale: str = ""
    steps: list[str] = field(default_factory=list)


@dataclass
class RunState:
    """The message passed along the workflow chain."""

    url: str
    session: str

    snapshots: list[list[SnapshotNode]] = field(default_factory=list)
    observed_code: list[str] = field(default_factory=list)
    flows: list[FlowCandidate] = field(default_factory=list)
    catalog: list[LocatorEntry] = field(default_factory=list)

    spec_title: str = ""
    spec_description: str = ""
    spec_steps: list[SpecStep] = field(default_factory=list)
    spec_path: str | None = None

    test_path: str | None = None
    test_source: str = ""

    test_passed: bool | None = None
    test_report: dict[str, Any] = field(default_factory=dict)

    usage: dict[str, StepUsage] = field(default_factory=dict)
    report_path: str | None = None

    def record_usage(
        self,
        step: str,
        *,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self.usage[step] = StepUsage(
            step=step,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    def tokens_for(self, step: str) -> int:
        usage = self.usage.get(step)
        return usage.total_tokens if usage else 0
