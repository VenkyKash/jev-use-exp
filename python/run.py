from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from core import (
    BrowserTask,
    build_browser_candidates,
    VisualObservation,
    VisualObservationError,
    build_candidates,
    classify,
    parse_visual_regions,
    validate_choice,
)
from jev_adapter import choose_live, choose_mock_adapter, choose_with_typesafe


def fixture_state(fixture_url: str) -> dict[str, str | None]:
    with urlopen(f"{fixture_url.rstrip('/')}/state", timeout=2) as response:
        return json.loads(response.read())


def validate_fixture_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError(
            "fixture URL must be an HTTP loopback origin such as http://127.0.0.1:8765/"
        )
    return value.rstrip("/") + "/"


def select_tab_id(tabs: list[dict[str, Any]]) -> str:
    if not tabs:
        raise RuntimeError("isolated browser has no tabs")
    selected = next((tab for tab in tabs if tab.get("active")), tabs[0])
    return str(selected["tab_id"])


def reset_fixture(fixture_url: str) -> None:
    request = Request(f"{fixture_url.rstrip('/')}/reset", method="POST", data=b"")
    with urlopen(request, timeout=2) as response:
        if response.status != 204:
            raise RuntimeError(f"fixture reset failed: HTTP {response.status}")


class Driver:
    def __init__(self, session: ClientSession, label: str) -> None:
        self.session = session
        self.label = label

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self.session.call_tool(name, {**arguments, "session": self.label})
        if result.isError:
            raise RuntimeError(f"{name} failed: {result.content}")
        data = result.structuredContent
        if not isinstance(data, dict):
            raise RuntimeError(f"{name} returned no structured result")
        if data.get("status") == "refused" or data.get("refusal"):
            raise RuntimeError(f"{name} refused: {data.get('refusal', data)}")
        return data


def supports_capture_bound_click(tools: list[Any]) -> bool:
    for tool in tools:
        if getattr(tool, "name", None) != "click":
            continue
        schema = getattr(tool, "inputSchema", None)
        if not isinstance(schema, dict):
            schema = getattr(tool, "input_schema", None)
        properties = schema.get("properties") if isinstance(schema, dict) else None
        return isinstance(properties, dict) and "capture_id" in properties
    return False


async def optional_visual_observation(
    driver: Driver,
    pid: int,
    window_id: int,
    available_tools: set[str],
    capture_bound_click: bool,
) -> VisualObservation | None:
    if not capture_bound_click or not {"get_window_state", "parse_visual_regions"}.issubset(
        available_tools
    ):
        return None
    try:
        capture = await driver.call(
            "get_window_state",
            {
                "pid": pid,
                "window_id": window_id,
                "include_accessibility_tree": False,
            },
        )
        capture_id = capture.get("capture_id")
        if not isinstance(capture_id, str):
            return None
        result = await driver.call(
            "parse_visual_regions",
            {
                "capture_id": capture_id,
                "options": {"kinds": ["text", "icon"], "min_confidence": 0.8, "max_regions": 100},
            },
        )
        return parse_visual_regions(
            result,
            expected_capture_id=capture_id,
            expected_pid=pid,
            expected_window_id=window_id,
        )
    except (RuntimeError, VisualObservationError, KeyError, TypeError):
        return None


async def wait_for_window(driver: Driver, pid: int) -> dict[str, Any]:
    for _ in range(40):
        windows = (await driver.call("list_windows", {"pid": pid})).get("windows", [])
        visible = [window for window in windows if window.get("is_on_screen")]
        if visible:
            return max(
                visible,
                key=lambda window: window["bounds"]["width"] * window["bounds"]["height"],
            )
        await asyncio.sleep(0.25)
    raise RuntimeError("isolated browser window did not become ready")


def write_event(log_path: Path | None, event: dict[str, Any]) -> None:
    line = json.dumps(event, sort_keys=True)
    if log_path and event.get("event") == "browser_evidence":
        snapshot = event["snapshot"]
        print(json.dumps(dict(event="browser_evidence_saved", step=event["step"],
                              page=snapshot.get("page"), snapshot=snapshot.get("snapshot"))), flush=True)
    else:
        print(line, flush=True)
    if log_path:
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


async def run(args: argparse.Namespace) -> str:
    task = BrowserTask.parse(json.loads(Path(args.task).read_text())) if getattr(args, "task", None) else None
    if task and args.provider != "live":
        raise ValueError("browser research requires --provider live; no mock fallback")
    if task and not os.getenv("TYPESAFE_API_KEY"):
        raise ValueError("TYPESAFE_API_KEY required before browser setup")
    token = args.token or f"jev-{uuid.uuid4().hex[:10]}"
    label = f"jev-python-{uuid.uuid4().hex[:8]}"
    history: list[dict[str, Any]] = []
    log_path = Path(args.log) if args.log else None
    if log_path:
        if task:
            with log_path.open("x"):
                pass
        else:
            log_path.write_text("", encoding="utf-8")
    if task and args.dry_run:
        write_event(log_path, {"event": "setup_planned", "start_url": task.start_url})
        return "dry_run"
    if not task:
        reset_fixture(args.fixture_url)

    params = StdioServerParameters(command=os.getenv("CUA_DRIVER_BIN", "cua-driver"), args=["mcp"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            advertised_tools = (await session.list_tools()).tools
            available_tools = {tool.name for tool in advertised_tools}
            capture_bound_click = supports_capture_bound_click(advertised_tools)
            driver = Driver(session, label)
            if task:
                required = {"browser_prepare", "list_windows", "get_browser_state", "browser_navigate", "browser_type", "browser_click"}
                if not required.issubset(available_tools):
                    raise ValueError("required browser tools unavailable")
                write_event(log_path, {"event": "browser_capabilities", "tools": sorted(required)})
            prepared = await driver.call(
                "browser_prepare",
                {"allow_launch": True, "profile": {"mode": "isolated_new"}},
            )
            pid = int(prepared["prepared_pid"])
            window = await wait_for_window(driver, pid)
            bound = await driver.call(
                "get_browser_state", {"pid": pid, "window_id": window["window_id"]}
            )
            target_id = bound["target_id"]
            tab_id = select_tab_id(bound["tabs"])
            await driver.call(
                "browser_navigate",
                {"target_id": target_id, "tab_id": tab_id, "url": task.start_url if task else args.fixture_url},
            )

            if task:
                return await run_research_loop(driver, task, target_id, tab_id, args.max_steps, log_path)

            for step in range(1, args.max_steps + 1):
                oracle = fixture_state(args.fixture_url)
                current = classify(oracle.get("submitted"), token, steps=step - 1, max_steps=args.max_steps)
                if current in {"verified", "refuted"}:
                    write_event(log_path, {"event": "outcome", "outcome": current, "token": token})
                    return current

                started = time.perf_counter()
                snapshot = await driver.call(
                    "get_browser_state",
                    {
                        "target_id": target_id,
                        "tab_id": tab_id,
                        "snapshot_format": "semantic_v2",
                    },
                )
                visual = await optional_visual_observation(
                    driver,
                    pid,
                    int(window["window_id"]),
                    available_tools,
                    capture_bound_click,
                )
                candidates = build_candidates(
                    snapshot,
                    token,
                    visual,
                    capture_bound_click=capture_bound_click,
                )
                if not candidates:
                    write_event(log_path, {"event": "outcome", "outcome": "abstained", "step": step})
                    return "abstained"

                if args.provider == "mock":
                    choice, confidence, probabilities = choose_mock_adapter(
                        candidates, snapshot, visual, history
                    )
                else:
                    choice, confidence, probabilities = await asyncio.to_thread(
                        choose_live, candidates, snapshot, visual, history
                    )
                if choice is None:
                    return "abstained"
                candidate = validate_choice(
                    choice,
                    candidates,
                    current_capture_id=visual.capture_id if visual else None,
                )
                decision_ms = round((time.perf_counter() - started) * 1000, 2)

                if candidate.id == "reobserve":
                    event = {
                        "event": "step",
                        "step": step,
                        "candidate": candidate.id,
                        "confidence": confidence,
                        "probabilities": probabilities,
                        "decision_ms": decision_ms,
                        "action_ms": 0.0,
                        "dry_run": args.dry_run,
                    }
                    history.append(event)
                    write_event(log_path, event)
                    continue

                if candidate.id == "abstain":
                    write_event(
                        log_path,
                        {
                            "event": "outcome",
                            "outcome": "abstained",
                            "step": step,
                            "confidence": confidence,
                            "probabilities": probabilities,
                        },
                    )
                    return "abstained"

                if not args.dry_run:
                    action_started = time.perf_counter()
                    try:
                        assert candidate.tool is not None
                        await driver.call(candidate.tool, candidate.arguments)
                    except Exception as error:
                        write_event(
                            log_path,
                            {
                                "event": "outcome",
                                "outcome": "unknown",
                                "step": step,
                                "phase": "action",
                                "error": type(error).__name__,
                            },
                        )
                        return "unknown"
                    action_ms = round((time.perf_counter() - action_started) * 1000, 2)
                else:
                    action_ms = 0.0
                event = {
                    "event": "step",
                    "step": step,
                    "candidate": candidate.id,
                    "confidence": confidence,
                    "probabilities": probabilities,
                    "decision_ms": decision_ms,
                    "action_ms": action_ms,
                    "dry_run": args.dry_run,
                }
                history.append(event)
                write_event(log_path, event)
                if args.dry_run:
                    return "unknown"
                if candidate.id == "submit-form":
                    for _ in range(20):
                        oracle = fixture_state(args.fixture_url)
                        outcome = classify(
                            oracle.get("submitted"), token, steps=step, max_steps=args.max_steps
                        )
                        if outcome in {"verified", "refuted"}:
                            write_event(
                                log_path, {"event": "outcome", "outcome": outcome, "token": token}
                            )
                            return outcome
                        await asyncio.sleep(0.1)

            oracle = fixture_state(args.fixture_url)
            outcome = classify(
                oracle.get("submitted"), token, steps=args.max_steps, max_steps=args.max_steps
            )
            write_event(log_path, {"event": "outcome", "outcome": outcome, "token": token})
            return outcome


async def run_research_loop(driver, task, target_id, tab_id, max_steps, log_path, chooser=None):
    """Reuse the browser adapter and immutable actions; return evidence, not a truth verdict."""
    from native_audit import audited_client
    from native_errors import error_details
    from contextlib import nullcontext
    import hashlib
    emit = lambda event: write_event(log_path, event)
    history, visits = [], {}
    snapshot = None
    # Tests inject a chooser explicitly; CLI always uses the audited real SDK.
    with (nullcontext(None) if chooser else audited_client(emit)) as client:
        for step in range(1, max_steps + 1):
            if snapshot is None:
                snapshot = await driver.call("get_browser_state", dict(target_id=target_id, tab_id=tab_id, snapshot_format="semantic_v2"))
            if snapshot.get("target_id") != target_id or snapshot.get("tab_id") != tab_id:
                raise ValueError("browser evidence target mismatch")
            try:
                task.check_url(snapshot["page"]["url"])
            except ValueError:
                emit(dict(event="outcome", outcome="outside_allowed_hosts"))
                return "outside_allowed_hosts"
            emit(dict(event="browser_evidence", step=step, snapshot=snapshot))
            fingerprint = hashlib.sha256(json.dumps([snapshot.get("page", {}).get("url"), snapshot.get("outline")], sort_keys=True).encode()).hexdigest()
            visits[fingerprint] = visits.get(fingerprint, 0) + 1
            if visits[fingerprint] > 3:
                emit(dict(event="outcome", outcome="no_progress"))
                return "no_progress"
            candidates = build_browser_candidates(snapshot, task)
            emit(dict(event="browser_candidates", step=step,
                      candidates=[dict(id=c.id, description=c.description) for c in candidates]))
            try:
                if chooser:
                    choice, confidence, probabilities = await chooser(candidates, snapshot, history)
                else:
                    choice, confidence, probabilities = await asyncio.to_thread(
                        choose_with_typesafe, client, candidates, snapshot, None, history[-12:], goal=task.goal)
                candidate = validate_choice(choice, candidates)
            except Exception as error:
                emit(dict(event="outcome", outcome="provider_failed", **error_details(error)))
                return "provider_failed"
            emit(dict(event="decision", step=step, selected_id=choice, confidence=confidence, probabilities=probabilities))
            if choice in {"finish", "abstain"}:
                outcome = "evidence_collected" if choice == "finish" else "abstained"
                emit(dict(event="outcome", outcome=outcome, independently_verified=False))
                return outcome
            history.append(dict(candidate=choice, description=candidate.description))
            snapshot = None
            if candidate.tool:
                emit(dict(event="dispatch", step=step, tool=candidate.tool, arguments=dict(candidate.arguments)))
                try:
                    result = await driver.call(candidate.tool, dict(candidate.arguments))
                except Exception as error:
                    emit(dict(event="outcome", outcome="unknown", **error_details(error)))
                    return "unknown"  # Never retry uncertain actions.
                if candidate.tool == "get_browser_state":
                    snapshot = result  # Consume this generation before requesting another.
        emit(dict(event="outcome", outcome="budget_exhausted"))
        return "budget_exhausted"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("mock", "live"), default="mock")
    parser.add_argument(
        "--fixture-url", type=validate_fixture_url, default="http://127.0.0.1:8765/"
    )
    parser.add_argument("--token")
    parser.add_argument("--task", help="declarative public-web research JSON; preserves the fixture demo when omitted")
    parser.add_argument("--max-steps", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--log", help="optional JSONL output path")
    args = parser.parse_args()
    if args.task and not 1 <= args.max_steps <= 50:
        parser.error("max steps must be 1..50")
    return args


def main() -> None:
    args = parse_args()
    async def bounded():
        return await asyncio.wait_for(run(args), 180) if args.task else await run(args)
    try:
        outcome = asyncio.run(bounded())
    except Exception as error:
        if not args.task:
            raise
        from native_errors import error_details
        # Setup may have failed because this log already exists; never append to it.
        write_event(None, dict(event="outcome", outcome="unknown", **error_details(error)))
        outcome = "unknown"
    raise SystemExit(0 if outcome in {"verified", "evidence_collected"} or args.dry_run else 1)


if __name__ == "__main__":
    main()
