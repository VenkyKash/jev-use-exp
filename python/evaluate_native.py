"""Evaluate selection on simulated controls; never opens desktop applications."""
import argparse
import asyncio
import json
import os
from pathlib import Path

from native_core import Task
from native_fixture import FixtureDriver
from native_jev import FirstCandidateBaseline, JevChooser
from native_run import run_loop


def cases():
    for a, b in [(17, 23), (8, 6), (24, 12)]:
        yield "calculator", Task.parse(dict(goal=f"Calculate {a} × {b} using the calculator buttons.",
            app="Fixture", inputs=[], checks=[dict(role="AXStaticText", label="Display", equals=str(a*b))]))
    for name, city in [("Ada", "Paris"), ("Morgan", "Oslo")]:
        yield "form", Task.parse(dict(goal=f"Enter {name} in Name and {city} in City, then submit the form.",
            app="Fixture", inputs=[name, city],
            checks=[dict(role="AXStaticText", label="Receipt", equals=f"{name} | {city}")]))


async def evaluate(chooser, emit):
    results = []
    for number, (kind, task) in enumerate(cases()):
        for reverse in [False, True]:
            driver = FixtureDriver(kind, reverse)
            case = f"{kind}-{number}-{'reverse' if reverse else 'normal'}"
            def record(event):
                emit(dict(case=case, **event))
            outcome = await asyncio.wait_for(run_loop(task, driver, chooser, record,
                target=(1,2), max_steps=20, seed=number*7+int(reverse)), 180)
            # Compare actual fixture backing state, independent of agent's declaration.
            actual = driver.display if kind == "calculator" else " | ".join(driver.submitted or ())
            passed = outcome == "verified" and actual == task.checks[0].equals
            result = dict(case=case, outcome=outcome, passed=passed, actions=len(driver.calls))
            results.append(result)
            emit(dict(event="case_result", **result))
    return dict(event="evaluation", environment="simulated", cases=len(results),
                passed=sum(r["passed"] for r in results), results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["first", "live"], default="first")
    parser.add_argument("--log", type=Path, required=True, help="new trace file")
    args = parser.parse_args()
    if args.provider == "live" and not os.getenv("TYPESAFE_API_KEY"):
        parser.error("TYPESAFE_API_KEY required for live evaluation")
    with args.log.open("x", encoding="utf-8") as stream:
        def emit(event):
            stream.write(json.dumps(event, sort_keys=True)+"\n")
            stream.flush()
        if args.provider == "live":
            from typesafe_sdk import TypeSafeClient, RetryPolicy
            with TypeSafeClient(timeout=10, retry=RetryPolicy(max_retries=0)) as client:
                summary = asyncio.run(evaluate(JevChooser(client), emit))
        else:
            summary = asyncio.run(evaluate(FirstCandidateBaseline(), emit))
        summary["provider"] = args.provider
        emit(summary)
        print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
