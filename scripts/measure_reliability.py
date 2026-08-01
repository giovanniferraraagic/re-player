"""Measure how often the pipeline produces a passing test.

The end-to-end result is stochastic, so a single green run proves nothing. This
runs the workflow N times and reports the success rate, which is what turns
"it feels better now" into a number you can compare before and after a change.

Usage:
    python scripts/measure_reliability.py --runs 6
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from replayer.config import WorkflowConfig, load_dotenv
from replayer.workflow import execute

TARGET_URL = "https://demo.playwright.dev/todomvc/"


async def one_run(index: int, root: Path, url: str, explore_steps: int) -> dict:
    config = WorkflowConfig.from_env(url=url, session=f"measure-{index}")
    config.max_explore_steps = explore_steps
    config.artifacts_dir = str(root / f"run-{index}" / "artifacts")
    config.checkpoint_dir = str(root / f"run-{index}" / "checkpoints")

    started = time.monotonic()
    try:
        state = await execute(config)
        return {
            "run": index,
            "passed": bool(state.test_passed),
            "seconds": round(time.monotonic() - started, 1),
            "tokens": {step: usage.total_tokens for step, usage in state.usage.items()},
            "spec_title": state.spec_title,
            "error": None,
        }
    except Exception as error:  # noqa: BLE001 - the failure is the measurement
        message = str(error)
        marker = "It was rejected because:"
        reason = (
            message[message.find(marker) :][:400] if marker in message else message[:400]
        )
        return {
            "run": index,
            "passed": False,
            "seconds": round(time.monotonic() - started, 1),
            "tokens": {},
            "spec_title": None,
            "error": reason,
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=6)
    parser.add_argument("--url", default=TARGET_URL)
    parser.add_argument("--explore-steps", type=int, default=3)
    parser.add_argument("--out", default="artifacts/reliability.json")
    args = parser.parse_args()

    load_dotenv()
    root = Path("artifacts") / "reliability"
    root.mkdir(parents=True, exist_ok=True)

    results = []
    for index in range(1, args.runs + 1):
        result = await one_run(index, root, args.url, args.explore_steps)
        results.append(result)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"run {index}/{args.runs}: {status} ({result['seconds']}s)", flush=True)
        if result["error"]:
            print(f"    {result['error'][:200]}", flush=True)

    passed = sum(1 for r in results if r["passed"])
    total_tokens = sum(sum(r["tokens"].values()) for r in results)
    summary = {
        "runs": args.runs,
        "passed": passed,
        "success_rate": round(passed / args.runs, 3),
        "mean_tokens_per_run": round(total_tokens / args.runs) if args.runs else 0,
        "results": results,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nSUCCESS RATE: {passed}/{args.runs} = {summary['success_rate']:.0%}")
    print(f"MEAN TOKENS:  {summary['mean_tokens_per_run']}")
    print(f"written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
