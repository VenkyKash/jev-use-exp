"""CI environment diagnostics: gather desktop/driver state and post it to the Cloudflare hub.

Read-only evidence collection. It never drives tasks; it only reports what the runner
environment looks like so launch failures can be understood from the dashboard.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_CHARS = 6000


def sh(cmd: str, timeout: int = 20) -> str:
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout,
                              executable="/bin/bash")
        out = (proc.stdout or "") + (proc.stderr or "")
        return f"$ {cmd}\n[exit {proc.returncode}]\n{out}"[:MAX_CHARS]
    except subprocess.TimeoutExpired as exc:
        partial = ((exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes)
                   else (exc.stdout or ""))
        return f"$ {cmd}\n[timeout {timeout}s]\n{partial}"[:MAX_CHARS]


def tail(path: str, lines: int = 40) -> str:
    try:
        text = Path(path).read_text(errors="replace").splitlines()[-lines:]
        return f"--- {path}\n" + "\n".join(text)
    except OSError as exc:
        return f"--- {path}\n[unreadable: {exc}]"


def collect() -> list[dict]:
    sections: list[dict] = []

    def add(title: str, body: str):
        sections.append({"event": "diagnostic", "section": title, "output": body[:MAX_CHARS]})

    add("env", "\n".join(f"{k}={os.environ.get(k)}" for k in
        ["DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "GTK_MODULES",
         "QT_ACCESSIBILITY", "NO_AT_BRIDGE", "CUA_DRIVER_BIN", "HOME", "USER"]))
    add("processes", sh("ps -eo pid,ppid,user,etime,cmd | grep -Ei 'Xvfb|fluxbox|dbus|at-spi|gnumeric|mousepad|galculator|cua' | grep -v grep"))
    add("binaries", sh("which cua-driver gnumeric mousepad galculator pinta xdotool xwininfo; cua-driver --version"))
    add("desktop_files", sh("ls /usr/share/applications | grep -Ei 'gnumeric|mousepad|galculator|pinta|chrom'"))
    add("xdpyinfo", sh("xdpyinfo -display :99 | head -n 12"))
    add("x_windows_before", sh("xwininfo -display :99 -root -tree | head -n 30"))

    log_dirs = sorted(glob.glob(str(ROOT / "runs" / "jules_*")))
    if log_dirs:
        d = log_dirs[-1]
        for name in ["xvfb.log", "fluxbox.log", "atspi.log", "driver_doctor.log"]:
            add(f"log:{name}", tail(f"{d}/{name}"))
    else:
        add("startup_logs", "no runs/jules_* directory found")

    add("driver_doctor", sh("cua-driver doctor", timeout=30))

    # Direct launch, bypassing the driver, to see whether the app can show a window at all.
    for app in ["mousepad", "galculator"]:
        launch = (f"({app} >/tmp/{app}.out 2>&1 & echo $! >/tmp/{app}.pid); sleep 6; "
                  f"echo '--- {app} stdout/stderr'; tail -n 20 /tmp/{app}.out; "
                  f"echo '--- alive?'; kill -0 $(cat /tmp/{app}.pid) 2>&1 && echo alive || echo dead; "
                  f"echo '--- windows'; xwininfo -display :99 -root -tree | grep -Ei '{app}' | head; "
                  f"kill $(cat /tmp/{app}.pid) 2>/dev/null; true")
        add(f"direct_launch:{app}", sh(launch, timeout=40))

    add("dbus_activation_names", sh("busctl --user list 2>&1 | head -n 20"))
    return sections


def post(events: list[dict]) -> None:
    hub = os.environ.get("CLOUDFLARE_HUB_URL")
    if not hub:
        print("[diagnose] CLOUDFLARE_HUB_URL not set; printing only")
        return
    body = {
        "runner_id": os.environ.get("RUNNER_ID", "local-runner"),
        "result": {"task": "ci_diagnostics", "status": "completed", "outcome": "diagnostic",
                   "passed": False, "duration_s": 0, "events": events,
                   "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
    }
    req = urllib.request.Request(
        f"{hub.rstrip('/')}/api/results", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "JevRunner/1.0",
                 "Authorization": f"Bearer {os.environ.get('CLOUDFLARE_RUNNER_KEY') or 'dev-secret-key'}"})
    try:
        urllib.request.urlopen(req, timeout=15)
        print("[diagnose] posted diagnostics to hub")
    except Exception as exc:
        print(f"[diagnose] post failed: {exc}")


if __name__ == "__main__":
    events = collect()
    for e in events:
        print(f"==== {e['section']}\n{e['output']}")
    post(events)
    sys.exit(0)
