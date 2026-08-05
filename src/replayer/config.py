"""Per-step configuration for the replayer workflow.

Every LLM-backed step reads its own model from the environment, so the cost of a
step can be changed - and re-measured - without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from replayer.models import ModelClient

#: Executors that must never invoke a language model.
CODE_ONLY_STEPS: tuple[str, ...] = ("bootstrap", "catalog", "run", "report")

#: Executors that are backed by a language model.
LLM_STEPS: tuple[str, ...] = ("explore", "plan", "generate")

#: The full executor sequence, in the order the workflow runs them.
EXECUTOR_SEQUENCE: tuple[str, ...] = (
    "bootstrap",
    "explore",
    "catalog",
    "plan",
    "generate",
    "run",
    "report",
)

DEFAULT_MODEL = "gpt-5-mini"

#: Providers with a client wired in ``replayer.models``. Kept here so a bad
#: provider is rejected while the configuration is being built, rather than
#: several steps later on the first model call.
SUPPORTED_PROVIDERS: tuple[str, ...] = ("azure",)

DEFAULT_PROVIDER = "azure"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a .env file without overriding the shell.

    Secrets live in .env, which is git-ignored. Existing environment variables
    win so CI can override anything the file declares.
    """
    from pathlib import Path

    env_file = Path(path)
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class StepModel:
    """Model binding for a single LLM-backed step."""

    step: str
    model: str
    provider: str

    @classmethod
    def from_env(cls, step: str) -> "StepModel":
        suffix = step.upper()
        model = os.environ.get(f"REPLAYER_MODEL_{suffix}") or os.environ.get(
            "REPLAYER_MODEL", DEFAULT_MODEL
        )
        provider = os.environ.get(f"REPLAYER_PROVIDER_{suffix}") or os.environ.get(
            "REPLAYER_PROVIDER", DEFAULT_PROVIDER
        )
        return cls(step=step, model=model, provider=provider)


@dataclass
class WorkflowConfig:
    """Runtime configuration for one workflow run."""

    url: str
    session: str = "replayer"
    stub_llm: bool = False
    dry_run: bool = False
    max_explore_steps: int = 8
    artifacts_dir: str = "artifacts"
    checkpoint_dir: str = ".checkpoints"
    generated_tests_dir: str = "e2e/generated"
    record_path: str | None = None
    replay_path: str | None = None
    models: dict[str, StepModel] = field(default_factory=dict)
    #: Cached model client for this run. Built once, because a recording client
    #: that were rebuilt per call would truncate its own transcript each time.
    #: This is per-run state rather than configuration; it lives here because
    #: the config object is what every step is handed.
    client: "ModelClient | None" = field(default=None, repr=False, compare=False)

    @classmethod
    def from_env(
        cls,
        url: str,
        session: str = "replayer",
        *,
        stub_llm: bool | None = None,
        dry_run: bool | None = None,
    ) -> "WorkflowConfig":
        load_dotenv()
        resolved_stub = _env_flag("REPLAYER_STUB_LLM") if stub_llm is None else stub_llm
        resolved_dry_run = _env_flag("REPLAYER_DRY_RUN") if dry_run is None else dry_run
        replay_path = os.environ.get("REPLAYER_REPLAY_PATH") or None
        models = {step: StepModel.from_env(step) for step in LLM_STEPS}

        # A provider with no client wired used to surface as NotImplementedError
        # from inside the first model call, several steps into a run. Reject it
        # here instead - but only when a real provider would actually be used.
        if not (resolved_stub or resolved_dry_run or replay_path):
            unsupported = sorted(
                {
                    binding.provider
                    for binding in models.values()
                    if binding.provider not in SUPPORTED_PROVIDERS
                }
            )
            if unsupported:
                raise ValueError(
                    f"No model client is wired for provider(s) {unsupported}. "
                    f"Supported: {list(SUPPORTED_PROVIDERS)}. Set REPLAYER_PROVIDER "
                    "to a supported value, or set REPLAYER_STUB_LLM=1 to run "
                    "without a provider."
                )

        return cls(
            url=url,
            session=session,
            stub_llm=resolved_stub,
            dry_run=resolved_dry_run,
            max_explore_steps=int(os.environ.get("REPLAYER_MAX_EXPLORE_STEPS", "8")),
            artifacts_dir=os.environ.get("REPLAYER_ARTIFACTS_DIR", "artifacts"),
            checkpoint_dir=os.environ.get("REPLAYER_CHECKPOINT_DIR", ".checkpoints"),
            generated_tests_dir=os.environ.get(
                "REPLAYER_GENERATED_TESTS_DIR", "e2e/generated"
            ),
            record_path=os.environ.get("REPLAYER_RECORD_PATH") or None,
            replay_path=replay_path,
            models=models,
        )

    def model_for(self, step: str) -> StepModel | None:
        return self.models.get(step)
