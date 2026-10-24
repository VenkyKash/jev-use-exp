"""Jules autonomous suite runner: executes tasks, records evidence, and aggregates improvements."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from native_core import Task
from native_fixture import FixtureDriver
from native_jev import FirstCandidateBaseline, JevChooser
from native_audit import audited_client
from native_run import run_loop


def load_tasks(tasks_dir: Path) -> list[tuple[str, Path]]:
    tasks = []
    if not tasks_dir.exists():
        return tasks
    for path in sorted(tasks_dir.glob("*.json")):
        tasks.append((path.stem, path))
    return tasks


async def run_single_task(task_name: str, task_path: Path, chooser: Any, emit: Any) -> dict[str, Any]:
    started = time.monotonic()
    try:
        content = json.loads(task_path.read_text())
        task = Task.parse(content)
    except Exception as exc:
        return {
            "task": task_name,
            "status": "skipped",
            "reason": f"Failed to parse task definition: {exc}",
            "duration_s": round(time.monotonic() - started, 2)
        }

    # If this is a simulated or fixture app, execute with FixtureDriver
    if task.app.lower() in {"fixture", "calculator", "calc"}:
        driver = FixtureDriver("calculator" if "calc" in task.app.lower() else "form", reverse=False)
        target = (1, 2)
        try:
            outcome = await asyncio.wait_for(
                run_loop(task, driver, chooser, emit, target=target, max_steps=20),
                timeout=120
            )
            passed = outcome == "verified"
            return {
                "task": task_name,
                "status": "completed",
                "outcome": outcome,
                "passed": passed,
                "actions": len(driver.calls) if hasattr(driver, "calls") else 0,
                "duration_s": round(time.monotonic() - started, 2)
            }
        except Exception as exc:
            return {
                "task": task_name,
                "status": "failed",
                "outcome": "error",
                "passed": False,
                "error": str(exc),
                "duration_s": round(time.monotonic() - started, 2)
            }
    else:
        # Live Linux desktop application via cua-driver MCP
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from native_driver import NativeDriver
        import uuid

        driver_bin = os.getenv("CUA_DRIVER_BIN", "cua-driver")
        params = StdioServerParameters(command=driver_bin, args=["mcp"])
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    driver = await NativeDriver.connect(session, f"jules-{uuid.uuid4().hex[:8]}")
                    driver.emit = emit
                    outcome = await asyncio.wait_for(
                        run_loop(task, driver, chooser, emit, max_steps=24),
                        timeout=180
                    )
                    passed = outcome == "verified"
                    return {
                        "task": task_name,
                        "status": "completed",
                        "outcome": outcome,
                        "passed": passed,
                        "actions": len(getattr(driver, "calls", [])),
                        "duration_s": round(time.monotonic() - started, 2)
                    }
        except Exception as exc:
            return {
                "task": task_name,
                "status": "failed",
                "outcome": "error",
                "passed": False,
                "error": str(exc),
                "duration_s": round(time.monotonic() - started, 2)
            }


async def run_suite(tasks_dir: Path, output_dir: Path, provider: str = "first") -> dict[str, Any]:
    task_files = load_tasks(tasks_dir)
    results = []
    log_file = output_dir / f"suite_{provider}.jsonl"

    def emit(event: dict[str, Any]):
        with log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    if provider == "live" and os.getenv("TYPESAFE_API_KEY"):
        with audited_client(emit) as client:
            chooser = JevChooser(client, emit=emit)
            for name, path in task_files:
                res = await run_single_task(name, path, chooser, emit)
                results.append(res)
    else:
        chooser = FirstCandidateBaseline()
        for name, path in task_files:
            res = await run_single_task(name, path, chooser, emit)
            results.append(res)

    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = sum(1 for r in results if r.get("status") == "failed" or (r.get("status") == "completed" and not r.get("passed")))
    skipped = sum(1 for r in results if r.get("status") in {"skipped", "pending_environment"})

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "provider": provider,
        "total_tasks": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "0%",
        "results": results
    }

    summary_file = output_dir / f"suite_summary_{provider}.json"
    summary_file.write_text(json.dumps(summary, indent=2))
    return summary


def generate_improvement_report(summary: dict[str, Any], report_dir: Path) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "jules_autonomous_evaluation_report.md"

    lines = [
        "# Jules Autonomous Task Evaluation & Improvement Report",
        "",
        f"**Date:** {summary['timestamp']}  ",
        f"**Provider Mode:** `{summary['provider']}`  ",
        f"**Tasks Evaluated:** {summary['total_tasks']}  ",
        f"**Passed:** {summary['passed']}  ",
        f"**Failed:** {summary['failed']}  ",
        f"**Skipped/Pending Environment:** {summary['skipped']}  ",
        f"**Pass Rate:** {summary['pass_rate']}",
        "",
        "## Task Breakdown",
        "",
        "| Task Name | Status | Outcome | Passed | Actions | Duration (s) | Notes |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in summary["results"]:
        lines.append(
            f"| `{r['task']}` | {r.get('status')} | {r.get('outcome', '-')} | "
            f"{'✅' if r.get('passed') else '❌'} | {r.get('actions', 0)} | "
            f"{r.get('duration_s', 0)} | {r.get('reason') or r.get('error') or '-'} |"
        )

    lines.extend([
        "",
        "## Key Failure Modes & Recommended Improvements",
        "",
        "1. **AT-SPI vs macOS AX Role Divergence:**",
        "   - On Linux X11/AT-SPI environments, roles differ from macOS AX (e.g., `push button` instead of `AXButton`).",
        "   - Normalization in `python/native_driver.py` and `python/v2_payload/run.py` should map AT-SPI standard roles.",
        "",
        "2. **Semantic Container Discovery:**",
        "   - Containers with generic titles hide target controls. Enable child preview summaries inside collapsed nodes.",
        "",
        "3. **Dual Observation & Geometric Targeting:**",
        "   - Custom visual canvases (spreadsheets, calculators) require optical parsing (`parse_visual_regions`).",
        "   - Ensure bounds are scaled to the active virtual screen dimensions (`1920x1080x24`).",
        "",
        "## Autonomous Iteration Next Steps",
        "- Extend `python/native_driver.py` to accept Linux window listing via `xdotool` or `wmctrl` when `cua-driver` is in headless X11 mode.",
        "- Re-run test suite after applying improvements.",
    ])

    report_path.write_text("\n".join(lines) + "\n")
    return report_path


def sync_to_cloudflare(summary: dict[str, Any], hub_url: str | None, api_key: str | None, runner_id: str):
    if not hub_url:
        return
    import urllib.request
    report_url = f"{hub_url.rstrip('/')}/api/results"
    for r in summary.get("results", []):
        try:
            req = urllib.request.Request(
                report_url,
                data=json.dumps({"runner_id": runner_id, "result": r}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key or 'dev-secret-key'}",
                    "User-Agent": "JevRunner/1.0"
                }
            )
            urllib.request.urlopen(req, timeout=10)
            print(f"[SYNC] Synced result for task '{r.get('task')}' to Cloudflare Hub")
        except Exception as exc:
            print(f"[SYNC WARNING] Failed to sync task '{r.get('task')}' to Cloudflare: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks-dir", type=Path, default=Path(__file__).resolve().parents[1] / "tasks")
    parser.add_argument("--log-dir", type=Path, default=Path(__file__).resolve().parents[1] / "runs")
    parser.add_argument("--report-dir", type=Path, default=Path(__file__).resolve().parents[1] / "reports")
    default_provider = "live" if os.getenv("TYPESAFE_API_KEY") else "first"
    parser.add_argument("--provider", choices=["first", "live"], default=default_provider)
    parser.add_argument("--runner-id", type=str, default=os.getenv("RUNNER_ID", "local-runner"))
    args = parser.parse_args()

    args.log_dir.mkdir(parents=True, exist_ok=True)
    summary = asyncio.run(run_suite(args.tasks_dir, args.log_dir, args.provider))
    report_file = generate_improvement_report(summary, args.report_dir)
    print(f"\n[JULES SUITE COMPLETE] Summary saved to: {args.log_dir}")
    print(f"[JULES SUITE COMPLETE] Improvement report generated at: {report_file}")
    print(json.dumps(summary, indent=2))

    hub_url = os.getenv("CLOUDFLARE_HUB_URL")
    api_key = os.getenv("CLOUDFLARE_RUNNER_KEY")
    if hub_url:
        sync_to_cloudflare(summary, hub_url, api_key, args.runner_id)

    if summary.get("failed", 0) > 0:
        print(f"\n[FAILURE] {summary['failed']} task(s) failed evaluation.")
        sys.exit(1)


if __name__ == "__main__":
    main()
