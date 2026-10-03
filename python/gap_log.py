"""Offline, local test-drive gap reports. Never calls Jev or controls the desktop."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

CATEGORIES = ("candidate", "observation", "decision", "execution", "environment", "handoff")


def summarize(path):
    """Count diagnostic facts, not inferred bugs; tolerate interrupted final lines."""
    reasons, events = Counter(), Counter()
    malformed = 0
    for line in Path(path).read_text().splitlines():
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("not an event")
        except (ValueError, TypeError):
            malformed += 1
            continue
        event = row.get("event")
        if isinstance(event, str):
            events[event] += 1
        if event == "candidate_coverage":
            for element in row.get("elements", []):
                for reason in element.get("reasons", []):
                    reasons[reason] += 1
    return dict(events=dict(events), coverage_reason_occurrences=dict(reasons),
                malformed_lines=malformed,
                coverage_available=events["candidate_coverage"] > 0)


def record_gap(directory, *, run, category, expected, actual, evidence,
               status="suspected", related=None):
    if category not in CATEGORIES or status not in ("suspected", "confirmed", "resolved"):
        raise ValueError("invalid category or status")
    if not all(isinstance(v, str) and v.strip() for v in (expected, actual, evidence)):
        raise ValueError("expected, actual, and evidence are required")
    source = Path(run).resolve(strict=True)
    if not source.is_file():
        raise ValueError("run must be a file")
    if status == "resolved" and not related:
        raise ValueError("resolution must reference the original gap ID")
    report = dict(schema="jev.gap.v1", id=uuid.uuid4().hex,
                  created_at=datetime.now(timezone.utc).isoformat(),
                  run=str(source), category=category, status=status, related=related,
                  expected=expected, actual=actual, evidence=evidence)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (report["id"] + ".json")
    with destination.open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    summary = commands.add_parser("summary")
    summary.add_argument("run")
    add = commands.add_parser("add")
    add.add_argument("--run", required=True)
    add.add_argument("--directory", default="runs/gaps")
    add.add_argument("--category", choices=CATEGORIES, required=True)
    add.add_argument("--expected", required=True)
    add.add_argument("--actual", required=True)
    add.add_argument("--evidence", required=True, help="Decision/snapshot ID or trace line and factual evidence; no secrets")
    add.add_argument("--status", choices=("suspected", "confirmed", "resolved"), default="suspected")
    add.add_argument("--related", help="Original gap ID for a follow-up or resolution")
    args = vars(parser.parse_args())
    command = args.pop("command")
    if command == "summary":
        print(json.dumps(summarize(args["run"]), indent=2))
    else:
        print(record_gap(**args))


if __name__ == "__main__":
    main()
