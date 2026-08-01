"""Command line entry point for the replayer harness."""

from __future__ import annotations

import click

from replayer import __version__

DEFAULT_TARGET_URL = "https://demo.playwright.dev/todomvc/"


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="replayer")
def main() -> None:
    """Author and run Playwright end-to-end tests through a reproducible workflow."""


@main.command()
@click.option(
    "--url",
    default=DEFAULT_TARGET_URL,
    show_default=True,
    help="URL of the application under test.",
)
@click.option(
    "--session",
    default="replayer",
    show_default=True,
    help="playwright-cli session name to use.",
)
def run(url: str, session: str) -> None:
    """Run the full authoring workflow against URL."""
    from replayer.workflow import run_workflow

    raise SystemExit(run_workflow(url=url, session=session))


if __name__ == "__main__":
    main()
