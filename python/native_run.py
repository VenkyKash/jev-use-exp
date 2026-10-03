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

from native_candidates import build_native_candidates, CandidateSet
from driver_candidates import choice_menu, catalog, thaw
from native_core import StepResult, Task, verify
from native_driver import NativeDriver, select_window, normalize
from native_errors import error_details
from native_audit import audited_client
from native_jev import JevChooser, decision_request, validate_decision
from evidence import evidence_handoff


async def run_loop(task, driver, chooser, emit, *, target=None, max_steps=24,
                   no_progress_limit=3, minimum_confidence=.1, seed=0, dry_run=False,
                   read_only=False, hierarchy=False):
    history = []
    stalled = 0
    refusal_recoveries = 0
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
                      scope="window text before system menu tree", inspection=observation.inspection),
                 observation.readback_text, reason=reason, complete=None))
    emit(dict(event="observation", snapshot_id=observation.id, elements=observation.compact()))
    visits = {observation.fingerprint(): 1} if observation else {}
    candidate_path = ()
    last_result = None
    previous_observation = None
    tree = None
    previous_view = None
    for step in range(max_steps):
        if observation and verify(task, observation):
            return "verified"
        coverage = []
        view = observation
        if hierarchy:
            from native_hierarchy import HierarchyView
            if tree is None or tree.observation.id != observation.id:
                tree = HierarchyView(observation)
            view = tree.project()
        candidates = build_native_candidates(task, view,
                                            (lambda *_: False) if read_only else driver.accepts,
                                            diagnostics=coverage, read_only=read_only, last_result=last_result)
        if hierarchy:
            # Hierarchy expansion replaces substring inspection in this mode.
            from core import Candidate
            candidates = CandidateSet(observation.id, tuple(
                c for c in candidates.candidates if not c.id.startswith("inspect-")) + tuple(tree.choices()) + (
                    (Candidate("review", "Hand full local readback to the caller for verification only when the task is complete.", None, {}),)
                    if observation.readback_text else ()))
        emit(dict(event="candidate_coverage", schema="jev.candidate_coverage.v1",
                  snapshot_id=observation.id, decision_id=f"decision-{step+1}",
                  read_only=read_only, observation_complete=observation.complete,
                  elements=coverage))
        if hasattr(driver, "schemas"):
            emit(dict(event="tool_catalog", tools=catalog(driver.schemas, candidates.candidates)))
        menu, groups = choice_menu(candidates.candidates, candidate_path)
        candidates = CandidateSet(observation.id, tuple(menu))
        request = decision_request(task, view, candidates, history, max_steps-step, seed+step,
                                   before=previous_view if hierarchy else previous_observation)
        from decision_payload import compact_catalog, structured_choices
        request["criteria"], request["bindings"] = structured_choices(candidates.candidates, groups)
        request["tools"] = compact_catalog(getattr(driver, "schemas", {}))
        request["observation"]["candidate_path"] = list(candidate_path)
        if last_result is not None:
            result_text = json.dumps(last_result)
            request["observation"]["last_tool_result"] = result_text[:12000]
            request["observation"]["result_characters_omitted"] = max(0, len(result_text)-12000)
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
        if hierarchy and candidate.id.startswith("tree-"):
            if dry_run:
                return "dry_run"
            tree.navigate(candidate.id, observation.id)
            candidate_path = ()
            history.append(dict(**asdict(choice), description=candidate.description,
                                outcome="hierarchy_inspected", executed=False))
            emit(dict(event="hierarchy_inspected", decision_id=decision_id,
                      selected_id=candidate.id, snapshot_id=observation.id))
            continue
        if candidate.id in groups:
            if dry_run:
                return "dry_run"
            candidate_path += (candidate.id,)
            history.append(dict(**asdict(choice), description=candidate.description,
                                outcome="candidate_group_selected", executed=False))
            emit(dict(event="candidate_group_selected", decision_id=decision_id,
                      group=candidate.id, options=len(groups[candidate.id])))
            continue  # No UI action or refreshed snapshot for a choice-menu drilldown.
        candidate_path = ()
        if candidate.id == "abstain":
            handoff("jev_abstained")
            return "abstained"
        if dry_run:
            return "dry_run"  # No launch, click, typing, or navigation.
        if candidate.id == "review":
            handoff("jev_requested_review")
            return "review_required"
        previous_observation = observation
        previous_view = view
        tree = None  # UI actions and reobserve invalidate local branch addressing.
        before = observation.fingerprint() if observation else None
        started = time.monotonic()
        result = None
        if candidate.tool:
            try:
                if candidate.tool == "click" and "x" in candidate.arguments:
                    from native_geometry import validate_pixel_target
                    await validate_pixel_target(driver, observation)
                emit(dict(event="dispatch", decision_id=decision_id, tool=candidate.tool,
                          arguments=thaw(candidate.arguments), snapshot_id=candidates.observation_id))
                result = await driver.call(candidate.tool, thaw(candidate.arguments))
                last_result = result
                emit(dict(event="tool_result", decision_id=decision_id, tool=candidate.tool, result=result))
                if candidate.tool == "bring_to_front":
                    emit(dict(event="activation_readback", verified=result.get("exact_window_effect", {}).get("verified") is True,
                              status=result.get("status")))
            except Exception as error:
                # Never repeat an uncertain mutation. Retain a fresh readback if possible.
                emit(dict(event="action_failed", decision_id=decision_id, **error_details(error)))
                if target:
                    try:
                        after = await driver.observe(*target)
                        emit(dict(event="failure_readback", snapshot_id=after.id, elements=after.compact()))
                        if verify(task, after):
                            return "verified"
                        details = getattr(error, "details", {})
                        refused = (details.get("driver_effect") == "refused"
                                   and details.get("driver_code") in {"element_outside_target_window", "off_space_or_ax_unresolved", "type_text_incomplete"})
                        action_error = (getattr(error, "code", None) == "driver_tool_error"
                                        and details.get("driver_code") == "tool_invocation_failed")
                        if (refused or action_error) and refusal_recoveries < 3:
                            refusal_recoveries += 1
                            observation = after
                            last_result = None
                            history.append(dict(**asdict(choice), description=candidate.description,
                                                outcome="refused_before_execution" if refused else "action_failed_effect_unknown",
                                                driver_code=details["driver_code"],
                                                error_details=details.get("driver_response", "")[:1000],
                                                recovery="Fresh observation available. Assess the actual effect against the task. Choose another target, inspect further, or dismiss an irrelevant menu if observed. Do not blindly repeat an uncertain mutation; no action was retried automatically."))
                            emit(dict(event="refusal_recovery" if refused else "action_error_recovery", decision_id=decision_id,
                                      snapshot_id=after.id, recovery_count=refusal_recoveries))
                            continue
                    except Exception:
                        pass
                return "unknown"
        inspecting = candidate.tool == "get_window_state"
        if inspecting:
            # This call already created the fresh index map. Do not invalidate it
            # with another observation before presenting its candidates to Jev.
            emit(dict(event="raw_observation", response=result))
            observation = normalize(result, *target, query=candidate.arguments.get("query"))
            last_result = None  # State is represented once, in Current.
        elif target:
            if driver.accepts("list_windows", {"pid": target[0]}):
                windows = (await driver.call("list_windows", {"pid": target[0]})).get("windows", [])
                new_id = select_window(windows, target[0])
                if new_id is not None and new_id != target[1]:
                    target = (target[0], new_id)
                    emit(dict(event="target_rebound", pid=target[0], window_id=new_id))
            observation = await driver.observe(*target)
        changed = observation is not None and before != observation.fingerprint()
        outcome = "inspection_read_not_task_progress" if inspecting else "observed_change" if changed else "no_change"
        history.append(dict(**asdict(choice), description=candidate.description,
                            outcome=outcome, changed=changed,
                            action_ms=round((time.monotonic()-started)*1000, 2),
                            driver_effect=result.get("effect") if result else None))
        if candidate.tool == "click":
            history[-1]["targeting"] = dict(
                method="coordinates" if "x" in candidate.arguments else "element",
                target=getattr(candidate, "target_index", None),
                area=getattr(candidate, "area_index", None),
                source_snapshot=candidates.observation_id,
                delivery=candidate.arguments.get("delivery_mode"),
                route=result.get("route") if result else None,
                point=[candidate.arguments.get("x"), candidate.arguments.get("y")]
                      if "x" in candidate.arguments else None)
        emit(dict(event="step_result", decision_id=decision_id, **history[-1]))
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
    parser.add_argument("--minimum-confidence", type=float, default=.1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--hierarchy", action="store_true", help="Jev-directed local hierarchy inspection; default flat mode unchanged")
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
            driver.emit = emit
            if args.doctor:
                emit(dict(event="capabilities", tools=catalog(driver.schemas, ())))
                return "inspected"
            if args.inspect:
                observation = await driver.observe(args.pid, args.window_id)
                emit(dict(event="observation", snapshot_id=observation.id, elements=observation.compact()))
                return "inspected"
            with audited_client(emit) as client:
                try:
                    return await run_loop(task, driver, JevChooser(client, emit=emit), emit,
                        target=(args.pid, args.window_id) if args.pid else None,
                        max_steps=args.max_steps, minimum_confidence=args.minimum_confidence,
                        seed=args.seed, dry_run=args.dry_run, read_only=args.read_only,
                        hierarchy=args.hierarchy)
                finally:
                    if driver.restore_target is not None:
                        try:
                            result = await asyncio.wait_for(driver.restore_focus(), 10)
                            emit(dict(event="focus_restored", result=result))
                        except Exception as error:
                            emit(dict(event="focus_restore_failed", **error_details(error)))


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
