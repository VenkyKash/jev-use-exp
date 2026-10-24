"""Local / Remote test dispatcher and monitor that interacts with the Cloudflare Hub."""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = PROJECT_ROOT / "tasks"


def get_hub_url():
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    url = os.getenv("CLOUDFLARE_HUB_URL")
    if not url:
        print("[ERROR] CLOUDFLARE_HUB_URL is not set in environment or .env file.")
        print("Example: export CLOUDFLARE_HUB_URL=https://jev-crossplatform-hub.yoursubdomain.workers.dev")
        sys.exit(1)
    return url.rstrip("/")


def list_runners(hub_url: str):
    req = urllib.request.Request(f"{hub_url}/api/runners", headers={"User-Agent": "JevMonitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            runners = data.get("runners", [])
            print(f"\nConnected Runners ({len(runners)}):")
            print(f"{'Runner ID':<25} {'OS / Arch':<18} {'Tags':<25} {'Status':<10}")
            print("-" * 80)
            for r in runners:
                tags = ", ".join(r.get("tags", []))
                arch_str = f" ({r.get('arch')})" if r.get("arch") else ""
                platform_str = f"{r.get('os', 'unknown')}{arch_str}"
                print(f"{r.get('runner_id', 'unknown'):<25} {platform_str:<18} {tags:<25} {r.get('status', 'unknown'):<10}")
            print("-" * 80)
    except Exception as exc:
        print(f"[ERROR] Failed to contact hub: {exc}")


def list_results(hub_url: str):
    req = urllib.request.Request(f"{hub_url}/api/results", headers={"User-Agent": "JevMonitor/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            results = data.get("results", [])
            print(f"\nRecent Execution Results ({len(results)}):")
            print(f"{'Runner':<22} {'Task':<22} {'Outcome':<15} {'Status':<10} {'Duration':<10}")
            print("-" * 82)
            for item in results:
                res = item.get("result", {})
                status_str = "PASSED" if res.get("passed") else "FAILED"
                runner_str = str(item.get("runner_id") or "unknown")
                task_str = str(res.get("task") or "unknown")
                outcome_str = str(res.get("outcome") or "unknown")
                dur_val = res.get("duration_s")
                dur_str = f"{dur_val}s" if dur_val is not None else "-"
                print(f"{runner_str:<22} {task_str:<22} {outcome_str:<15} {status_str:<10} {dur_str:<10}")
            print("-" * 82)
    except Exception as exc:
        print(f"[ERROR] Failed to fetch results: {exc}")


def dispatch_task(hub_url: str, task_name: str):
    task_file = TASKS_DIR / f"{task_name}.json"
    if not task_file.exists():
        matches = list(TASKS_DIR.glob(f"*{task_name}*.json"))
        if matches:
            task_file = matches[0]
        else:
            print(f"[ERROR] Task '{task_name}' not found in tasks directory.")
            sys.exit(1)

    payload = json.loads(task_file.read_text())
    payload["name"] = task_file.stem
    print(f"Dispatching task '{payload['name']}' to Cloudflare Hub ({hub_url})...")

    req = urllib.request.Request(
        f"{hub_url}/api/tasks/submit",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "JevMonitor/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"Success: {data.get('message')} (Task ID: {data.get('task_id')})")
    except Exception as exc:
        print(f"[ERROR] Dispatch failed: {exc}")


def main():
    parser = argparse.ArgumentParser(description="Jev Cloudflare Cross-Platform Task Dispatcher & Monitor")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparsers.add_parser("runners", help="List all connected Linux and Windows runners")
    subparsers.add_parser("results", help="List recent task execution outcomes and evidence")
    
    dispatch_parser = subparsers.add_parser("dispatch", help="Submit a task definition to the hub for execution")
    dispatch_parser.add_argument("--task", type=str, required=True, help="Task name (e.g. gnumeric_budget, galculator_calc)")

    args = parser.parse_args()
    hub = get_hub_url()

    if args.cmd == "runners":
        list_runners(hub)
    elif args.cmd == "results":
        list_results(hub)
    elif args.cmd == "dispatch":
        dispatch_task(hub, args.task)


if __name__ == "__main__":
    main()
