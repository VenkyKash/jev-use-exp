"""Jules API client & autonomous background session manager.

Interacts with the Google Jules REST API (v1alpha) to:
- List connected sources/repositories
- Create new coding sessions
- Poll session state & stream activities asynchronously
- Auto-approve plans and relay human messages
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

BASE_URL = "https://jules.googleapis.com/v1alpha"


def get_api_key() -> str:
    key = os.getenv("JULES_API_KEY")
    if not key:
        # Check .env file
        env_path = Path(__file__).resolve().parents[1] / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip().upper() == "JULES_API_KEY":
                    key = v.strip().strip("\"'")
                    break
    if not key:
        raise ValueError("JULES_API_KEY not found in environment or .env file.")
    return key


class JulesClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or get_api_key()
        self.headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "Jules-CLI-Manager/1.0"
        }

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict[str, Any]:
        url = f"{BASE_URL}/{path.lstrip('/')}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            raise RuntimeError(f"Jules API {method} {path} returned HTTP {exc.code}: {error_body}") from exc

    def list_sources(self) -> list[dict[str, Any]]:
        """List all connected GitHub repositories."""
        data = self._request("GET", "sources")
        return data.get("sources", [])

    def list_sessions(self, page_size: int = 10) -> list[dict[str, Any]]:
        """List recent Jules coding sessions."""
        data = self._request("GET", f"sessions?pageSize={page_size}")
        return data.get("sessions", [])

    def get_session(self, session_id: str) -> dict[str, Any]:
        """Fetch session metadata and current state."""
        clean_id = session_id.split("/")[-1]
        return self._request("GET", f"sessions/{clean_id}")

    def create_session(self, prompt: str, source_id: str, branch: str = "jules", title: str | None = None) -> dict[str, Any]:
        """Create a new autonomous coding session in Jules."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "sourceContext": {
                "source": source_id if "/" in source_id else f"sources/{source_id}",
                "githubRepoContext": {
                    "startingBranch": branch
                },
                "environmentVariablesEnabled": True
            }
        }
        if title:
            payload["title"] = title
        return self._request("POST", "sessions", payload)

    def approve_plan(self, session_id: str) -> dict[str, Any]:
        """Approve a multi-step plan when AWAITING_PLAN_APPROVAL."""
        clean_id = session_id.split("/")[-1]
        return self._request("POST", f"sessions/{clean_id}:approvePlan", {})

    def send_message(self, session_id: str, message: str) -> dict[str, Any]:
        """Send follow-up instructions or answer a question from Jules."""
        clean_id = session_id.split("/")[-1]
        return self._request("POST", f"sessions/{clean_id}:sendMessage", {"prompt": message})

    def list_activities(self, session_id: str, page_size: int = 50, page_token: str | None = None) -> dict[str, Any]:
        """Fetch activity stream (agent messages, command executions, diffs)."""
        clean_id = session_id.split("/")[-1]
        query = f"pageSize={page_size}"
        if page_token:
            query += f"&pageToken={urllib.parse.quote(page_token)}"
        try:
            return self._request("GET", f"sessions/{clean_id}/activities?{query}")
        except RuntimeError as exc:
            if "HTTP 404" in str(exc):
                # When queued or initializing, activities endpoint may return 404 until first event
                return {"activities": []}
            raise


def manage_session(client: JulesClient, session_id: str, auto_approve: bool = True, interval: int = 6) -> None:
    clean_id = session_id.split("/")[-1]
    print(f"\n[JULES MANAGER] Attaching to session: {clean_id}")
    print(f"[JULES MANAGER] Auto-approve plans: {auto_approve} | Poll interval: {interval}s\n")

    seen_activities = set()
    last_state = None

    while True:
        try:
            session = client.get_session(clean_id)
            state = session.get("state", "UNKNOWN")

            if state != last_state:
                print(f"\n>>> STATE CHANGED: {last_state} -> \033[1;32m{state}\033[0m")
                last_state = state

            # Poll activities
            activities_data = client.list_activities(clean_id)
            activities = activities_data.get("activities", [])

            for act in activities:
                act_name = act.get("name")
                if act_name not in seen_activities:
                    seen_activities.add(act_name)
                    act_type = act.get("type", "EVENT")
                    msg = act.get("message") or act.get("description") or ""
                    timestamp = act.get("createTime", "")[:19]
                    print(f"[{timestamp}] [\033[1;34m{act_type}\033[0m] {msg}")

            # Auto-approve plan if Jules is waiting
            if state == "AWAITING_PLAN_APPROVAL" and auto_approve:
                print("\n[JULES MANAGER] Auto-approving generated plan...")
                client.approve_plan(clean_id)
                time.sleep(2)
                continue

            if state in ("COMPLETED", "FAILED", "CANCELLED"):
                print(f"\n[JULES MANAGER] Session reached terminal state: \033[1;33m{state}\033[0m")
                break

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[JULES MANAGER] Detached from monitoring. Session remains active in Jules cloud.")
            break
        except Exception as exc:
            print(f"[JULES MANAGER WARNING] Transient poll error: {exc}")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Jules Autonomous Session Manager")
    subparsers = parser.add_subparsers(dest="command")

    # Sources
    subparsers.add_parser("sources", help="List connected repository sources")

    # List sessions
    subparsers.add_parser("list", help="List active and past Jules sessions")

    # Create session
    create_p = subparsers.add_parser("create", help="Create a new Jules session")
    create_p.add_argument("--prompt", required=True, help="Task prompt for Jules")
    create_p.add_argument("--source", required=True, help="Repository source name/ID")
    create_p.add_argument("--branch", default="jules", help="Branch name (default: jules)")
    create_p.add_argument("--follow", action="store_true", help="Automatically follow session after creation")

    # Follow / attach to session
    follow_p = subparsers.add_parser("follow", help="Attach to and manage an active session")
    follow_p.add_argument("--session-id", required=True, help="Session ID to monitor")
    follow_p.add_argument("--no-auto-approve", action="store_true", help="Do not auto-approve plans")

    # Send message
    msg_p = subparsers.add_parser("send", help="Send a message/instruction to Jules")
    msg_p.add_argument("--session-id", required=True, help="Target session ID")
    msg_p.add_argument("--message", required=True, help="Message text")

    # Approve plan
    app_p = subparsers.add_parser("approve", help="Approve plan for session")
    app_p.add_argument("--session-id", required=True, help="Session ID")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        client = JulesClient()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print("Please add 'JULES_API_KEY=...' to your .env file or environment.", file=sys.stderr)
        sys.exit(1)

    if args.command == "sources":
        sources = client.list_sources()
        print(json.dumps(sources, indent=2))
    elif args.command == "list":
        sessions = client.list_sessions()
        print(json.dumps(sessions, indent=2))
    elif args.command == "create":
        res = client.create_session(args.prompt, args.source, args.branch)
        print(f"Created session: {res.get('name')}")
        if args.follow and "name" in res:
            manage_session(client, res["name"])
    elif args.command == "follow":
        manage_session(client, args.session_id, auto_approve=not args.no_auto_approve)
    elif args.command == "send":
        res = client.send_message(args.session_id, args.message)
        print(f"Message sent: {res}")
    elif args.command == "approve":
        res = client.approve_plan(args.session_id)
        print(f"Plan approved: {res}")


if __name__ == "__main__":
    main()
