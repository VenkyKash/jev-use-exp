"""Standalone native v0. Run --help for limits and read-only inspection."""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from native_candidates import build_native_candidates
from native_core import StepResult, Task, verify
from native_driver import NativeDriver, select_window
from native_errors import error_details
from native_audit import audited_client
from native_jev import JevChooser, decision_request, validate_decision
from evidence import evidence_handoff


async def run_loop(task, driver, chooser, emit, *, target=None, max_steps=24,
                   no_progress_limit=3, minimum_confidence=.4, seed=0, dry_run=False,
                   read_only=False):
    history = []
    stalled = 0
    if target is None:
        if dry_run:
            emit(dict(event="setup_planned", tool="launch_app", arguments={"name": task.app}))
            return "dry_run"
        emit(dict(event="setup_dispatch", tool="launch_app", arguments={"name": task.app},
                  authority="explicit_task_app"))
        try:
            result = await driver.call("launch_app", {"name": task.app})
        except Exception as error:
            emit(dict(event="setup_failed", **error_details(error)))
            return "unknown"  # Never repeat an uncertain launch.
        pid = result.get("pid")
        if type(pid) is not int or pid <= 0:
            return "unknown"
        windows = result.get("windows", [])
        for _ in range(5):
            if select_window(windows, pid) is not None:
                break
            await asyncio.sleep(.2)
            windows = (await driver.call("list_windows", {"pid": pid})).get("windows", [])
        window_id = select_window(windows, pid)
        if window_id is None:
            emit(dict(event="target_required", pid=pid, windows=windows))
            return "needs_window_selection"
        target = (pid, window_id)
        emit(dict(event="target_bound", pid=pid, window_id=window_id,
                  rule="unique_named_or_only_window"))
    observation = await driver.observe(*target) if target else None
    def handoff(reason):
        if observation.readback_text:
            emit(evidence_handoff(task.goal,
                 dict(kind="native_window", app=task.app, pid=observation.pid,
                      window_id=observation.window_id, snapshot_id=observation.id,
                      scope="window text before system menu tree"),
                 observation.readback_text, reason=reason, complete=None))
    emit(dict(event="observation", snapshot_id=observation.id, elements=observation.compact()))
    visits = {observation.fingerprint(): 1} if observation else {}
    for step in range(max_steps):
        if observation and verify(task, observation):
            return "verified"
        candidates = build_native_candidates(task, observation,
                                            (lambda *_: False) if read_only else driver.accepts)
        request = decision_request(task, observation, candidates, history, max_steps-step, seed+step)
        decision_id = f"decision-{step+1}"
        emit(dict(event="decision_request", decision_id=decision_id, request=request,
                  executable_options=sum(c.tool is not None for c in candidates.candidates)))
        started = time.monotonic()
        try:
            choice = await chooser.choose(request)
            validate_decision(choice, request, minimum_confidence)
        except Exception as error:
            emit(dict(event="decision_failed", decision_id=decision_id, **error_details(error)))
            handoff("decision_failed")
            return "provider_failed"
        emit(dict(event="decision", decision_id=decision_id, **asdict(choice),
                  decision_ms=round((time.monotonic()-started)*1000, 2)))
        candidate = candidates.resolve(choice.selected_id, observation.id if observation else "startup")
        if candidate.id == "abstain":
            handoff("jev_abstained")
            return "abstained"
        if dry_run:
            return "dry_run"  # No launch, click, typing, or navigation.
        if candidate.id == "review":
            handoff("jev_requested_review")
            return "review_required"
        before = observation.fingerprint() if observation else None
        started = time.monotonic()
        result = None
        if candidate.tool:
            emit(dict(event="dispatch", decision_id=decision_id, tool=candidate.tool,
                      arguments=dict(candidate.arguments), snapshot_id=candidates.observation_id))
            try:
                result = await driver.call(candidate.tool, dict(candidate.arguments))
            except Exception as error:
                # Never repeat an uncertain mutation. Retain a fresh readback if possible.
                emit(dict(event="action_failed", decision_id=decision_id, **error_details(error)))
                if target:
                    try:
                        after = await driver.observe(*target)
                        emit(dict(event="failure_readback", snapshot_id=after.id, elements=after.compact()))
                        if verify(task, after):
                            return "verified"
                    except Exception:
                        pass
                return "unknown"
        if target:
            observation = await driver.observe(*target)
        changed = observation is not None and before != observation.fingerprint()
        outcome = "observed_change" if changed else "no_change"
        history.append(StepResult(candidate.id, candidate.description, outcome, changed))
        emit(dict(event="step_result", decision_id=decision_id, **asdict(history[-1]),
                  action_ms=round((time.monotonic()-started)*1000, 2),
                  driver_effect=result.get("effect") if result else None))
        if observation:
            emit(dict(event="observation", snapshot_id=observation.id, elements=observation.compact()))
            if verify(task, observation):
                return "verified"
            fingerprint = observation.fingerprint()
            visits[fingerprint] = visits.get(fingerprint, 0)+1
            if changed and visits[fingerprint] >= 3:
                handoff("repeated_state")
                return "repeated_state"
        stalled = 0 if changed else stalled+1
        if stalled >= no_progress_limit:
            handoff("no_progress")
            return "no_progress"
    handoff("budget_exhausted")
    return "budget_exhausted"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", type=Path)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--window-id", type=int)
    parser.add_argument("--inspect", action="store_true", help="read a specified window without Jev or actions")
    parser.add_argument("--doctor", action="store_true", help="read MCP capabilities without opening apps")
    parser.add_argument("--dry-run", action="store_true", help="one Jev decision, no mutations")
    parser.add_argument("--read-only", action="store_true", help="allow explicit app setup, then only observation or abstention")
    parser.add_argument("--max-steps", type=int, default=24)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--minimum-confidence", type=float, default=.4)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--log", type=Path, help="new JSONL file, never overwritten; contains UI and input text")
    args = parser.parse_args()
    if bool(args.pid) != bool(args.window_id) or (args.pid is not None and min(args.pid, args.window_id) <= 0):
        parser.error("supply both positive --pid and --window-id")
    if args.inspect and args.pid is None:
        parser.error("--inspect requires --pid and --window-id")
    if not (args.inspect or args.doctor) and args.task is None:
        parser.error("--task is required")
    if not 1 <= args.max_steps <= 100 or not math.isfinite(args.timeout) or not 0 < args.timeout <= 600:
        parser.error("max steps must be 1..100; timeout must be >0 and <=600")
    if not math.isfinite(args.minimum_confidence) or not 0 <= args.minimum_confidence <= 1:
        parser.error("minimum confidence must be between zero and one")
    return args


async def execute(args, emit):
    task = Task.parse(json.loads(args.task.read_text())) if args.task else None
    if not (args.inspect or args.doctor) and not os.getenv("TYPESAFE_API_KEY"):
        raise ValueError("TYPESAFE_API_KEY is required; no fallback provider")
    params = StdioServerParameters(command=os.getenv("CUA_DRIVER_BIN", "cua-driver"), args=["mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            driver = await NativeDriver.connect(session, f"jev-exp-{uuid.uuid4().hex[:8]}")
            if args.doctor:
                emit(dict(event="capabilities", tools={name: name in driver.schemas for name in
                          ["launch_app", "list_windows", "get_window_state", "click", "type_text", "parse_visual_regions"]}))
                return "inspected"
            if args.inspect:
                observation = await driver.observe(args.pid, args.window_id)
                emit(dict(event="observation", snapshot_id=observation.id, elements=observation.compact()))
                return "inspected"
            with audited_client(emit) as client:
                return await run_loop(task, driver, JevChooser(client, emit=emit), emit,
                    target=(args.pid, args.window_id) if args.pid else None,
                    max_steps=args.max_steps, minimum_confidence=args.minimum_confidence,
                    seed=args.seed, dry_run=args.dry_run, read_only=args.read_only)


def main():
    args = parse_args()
    if not (args.inspect or args.doctor) and not os.getenv("TYPESAFE_API_KEY"):
        raise SystemExit("TYPESAFE_API_KEY is required; no app was opened and no fallback will run")
    if sys.platform != "darwin" and not args.doctor:
        raise SystemExit("native v0 currently supports macOS AX roles only")
    stream = args.log.open("x", encoding="utf-8") if args.log else None
    def emit(event):
        line = json.dumps(event, sort_keys=True)
        print(line, flush=True)
        if stream:
            stream.write(line+"\n")
            stream.flush()
    async def bounded():
        try:
            return await asyncio.wait_for(execute(args, emit), args.timeout)
        except asyncio.TimeoutError:
            return "timeout_unknown"
        except Exception as error:
            # Exception messages may contain credentials or application content.
            emit(dict(event="error", **error_details(error)))
            return "unknown"
    try:
        outcome = asyncio.run(bounded())
        emit(dict(event="outcome", outcome=outcome))
    finally:
        if stream:
            stream.close()
    raise SystemExit(0 if outcome in {"verified", "review_required", "dry_run", "inspected"} else 1)


if __name__ == "__main__":
    main()
