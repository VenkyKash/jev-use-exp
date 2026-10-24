import argparse
import asyncio
import json
import os
import platform
import socket
import sys
import time
import urllib.request
import uuid
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

from native_core import Task
from native_driver import NativeDriver
from native_run import run_loop
from native_jev import FirstCandidateBaseline, JevChooser
from native_audit import audited_client


class RunnerState:
    def __init__(self, runner_id: str, tags: list[str]):
        self.runner_id = runner_id
        self.tags = tags
        self.os_type = platform.system().lower()
        self.arch = platform.machine().lower()
        self.current_task = None
        self.status = "idle"
        self.last_heartbeat = time.time()
        self.completed_tasks = []

    def to_dict(self):
        return {
            "runner_id": self.runner_id,
            "os": self.os_type,
            "arch": self.arch,
            "tags": self.tags,
            "status": self.status,
            "current_task": self.current_task,
            "last_heartbeat": self.last_heartbeat
        }


def make_http_handler(state: RunnerState, task_queue: asyncio.Queue):
    class RequestHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, data: dict):
            payload = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/health" or self.path == "/":
                self._send_json(200, {"ok": True, "runner": state.to_dict()})
            elif self.path == "/status":
                self._send_json(200, state.to_dict())
            else:
                self._send_json(404, {"error": "Not Found"})

        def do_POST(self):
            if self.path == "/tasks":
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                try:
                    task_payload = json.loads(body)
                    asyncio.run_coroutine_threadsafe(task_queue.put(task_payload), loop)
                    self._send_json(202, {"ok": True, "message": "Task queued for execution"})
                except Exception as exc:
                    self._send_json(400, {"error": f"Invalid JSON payload: {exc}"})
            else:
                self._send_json(404, {"error": "Not Found"})

        def log_message(self, format, *args):
            # Suppress default server access logging
            pass

    return RequestHandler


async def execute_task_on_runner(task_data: dict, emit_cb):
    started = time.monotonic()
    task_name = task_data.get("name", "remote_task")
    try:
        task = Task.parse(task_data)
    except Exception as exc:
        return {
            "task": task_name,
            "status": "failed",
            "outcome": "error",
            "passed": False,
            "error": f"Task parse error: {exc}",
            "duration_s": round(time.monotonic() - started, 2)
        }

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    
    driver_bin = os.getenv("CUA_DRIVER_BIN", "cua-driver")
    params = StdioServerParameters(command=driver_bin, args=["mcp"])
    
    # Choose Jev vs baseline
    if os.getenv("TYPESAFE_API_KEY"):
        with audited_client(emit_cb) as client:
            chooser = JevChooser(client, emit=emit_cb)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    driver = await NativeDriver.connect(session, f"runner-{uuid.uuid4().hex[:8]}")
                    driver.emit = emit_cb
                    outcome = await asyncio.wait_for(
                        run_loop(task, driver, chooser, emit_cb, max_steps=task_data.get("max_steps", 24)),
                        timeout=task_data.get("timeout_s", 180)
                    )
    else:
        chooser = FirstCandidateBaseline()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                driver = await NativeDriver.connect(session, f"runner-{uuid.uuid4().hex[:8]}")
                driver.emit = emit_cb
                outcome = await asyncio.wait_for(
                    run_loop(task, driver, chooser, emit_cb, max_steps=task_data.get("max_steps", 24)),
                    timeout=task_data.get("timeout_s", 180)
                )

    passed = outcome == "verified"
    return {
        "task": task_name,
        "status": "completed",
        "outcome": outcome,
        "passed": passed,
        "duration_s": round(time.monotonic() - started, 2)
    }


async def queue_worker(state: RunnerState, task_queue: asyncio.Queue, hub_url: str | None, api_key: str | None):
    while True:
        task_data = await task_queue.get()
        state.status = "busy"
        state.current_task = task_data.get("name", "task")
        print(f"\n[RUNNER] Starting execution of task: {state.current_task}", flush=True)

        events = []
        def emit(event: dict):
            events.append(event)
            print(f"[RUNNER EVENT] {event.get('event')}", flush=True)

        try:
            result = await execute_task_on_runner(task_data, emit)
            result["events"] = events
            state.completed_tasks.append(result)
            print(f"[RUNNER] Task {state.current_task} finished with outcome={result.get('outcome')} (passed={result.get('passed')})", flush=True)

            # Report back to central hub if configured
            if hub_url and api_key:
                report_url = f"{hub_url.rstrip('/')}/api/results"
                req = urllib.request.Request(
                    report_url,
                    data=json.dumps({"runner_id": state.runner_id, "result": result}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                )
                try:
                    urllib.request.urlopen(req, timeout=10)
                except Exception as e:
                    print(f"[RUNNER WARNING] Could not report result to hub: {e}", flush=True)
        except Exception as exc:
            print(f"[RUNNER ERROR] Execution crashed: {exc}", flush=True)
        finally:
            state.status = "idle"
            state.current_task = None
            task_queue.task_done()


async def heartbeat_loop(state: RunnerState, hub_url: str | None, api_key: str | None):
    if not hub_url or not api_key:
        return
    url = f"{hub_url.rstrip('/')}/api/runners/heartbeat"
    while True:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(state.to_dict()).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "JevRunner/1.0"
                }
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception as e:
            print(f"[RUNNER HEARTBEAT ERROR] Failed to send heartbeat: {e}", flush=True)
        await asyncio.sleep(15)


def main():
    parser = argparse.ArgumentParser(description="Cross-platform Jev/Cua runner agent for Linux & Windows")
    parser.add_argument("--port", type=int, default=8787, help="Local HTTP listener port for receiving tasks or tunnel binding")
    parser.add_argument("--id", type=str, default=None, help="Runner ID (defaults to hostname-os)")
    parser.add_argument("--tags", type=str, default="", help="Comma-separated tags (e.g. linux,x11,office)")
    parser.add_argument("--hub", type=str, default=os.getenv("CLOUDFLARE_HUB_URL"), help="Cloudflare Worker Hub URL")
    parser.add_argument("--key", type=str, default=os.getenv("CLOUDFLARE_RUNNER_KEY", "dev-secret-key"), help="Shared auth secret")
    args = parser.parse_args()

    hostname = socket.gethostname().split(".")[0].lower()
    os_name = platform.system().lower()
    runner_id = args.id or f"{hostname}-{os_name}"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    if os_name not in tags:
        tags.append(os_name)

    state = RunnerState(runner_id, tags)
    task_queue = asyncio.Queue()

    global loop
    loop = asyncio.get_event_loop()

    # Start local HTTP server in background thread
    handler_class = make_http_handler(state, task_queue)
    httpd = HTTPServer(("0.0.0.0", args.port), handler_class)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    print(f"============================================================")
    print(f"  Jev Cross-Platform Runner Agent Started")
    print(f"  Runner ID : {runner_id}")
    print(f"  OS / Arch : {os_name} ({platform.machine()})")
    print(f"  Tags      : {', '.join(tags)}")
    print(f"  Listener  : http://0.0.0.0:{args.port}")
    if args.hub:
        print(f"  Hub URL   : {args.hub}")
    print(f"============================================================", flush=True)

    loop.create_task(queue_worker(state, task_queue, args.hub, args.key))
    loop.create_task(heartbeat_loop(state, args.hub, args.key))

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\nShutting down runner agent...")
        httpd.shutdown()


if __name__ == "__main__":
    main()
