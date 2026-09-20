"""Paired Jev inference on recorded states only. No Driver or action dispatch."""
import argparse
import asyncio
from dataclasses import asdict
import json
from pathlib import Path

from decision_context import format_context
from native_audit import audited_client
from native_jev import JevChooser, validate_decision
from native_errors import error_details


def load_pair(path, decision_id):
    events = [json.loads(line) for line in path.read_text().splitlines()]
    requests = [e for e in events if e.get("event") == "decision_request"]
    index = next(i for i, e in enumerate(requests) if e["decision_id"] == decision_id)
    if index == 0:
        raise ValueError("comparison requires an earlier recorded observation")
    return requests[index]["request"], requests[index-1]["request"]["observation"]


async def compare(cases, repeats, emit, live):
    rows = []
    for name, path, decision_id in cases:
        original, previous = load_pair(path, decision_id)
        variants = {"original": original, "compact_current": format_context(original),
                    "compact_before_after": format_context(original, previous)}
        for variant, request in variants.items():
            assert list(request["criteria"].items()) == list(original["criteria"].items())
            emit(dict(event="comparison_input", case=name, variant=variant,
                      source=str(path), decision_id=decision_id, request=request,
                      serialized_characters=len(json.dumps(request, ensure_ascii=False))))
        rows.append((name, variants))
    if not live:
        return
    with audited_client(emit) as client:
        chooser = JevChooser(client, emit)
        for repeat in range(repeats):
            for name, variants in rows:
                order = list(variants)
                if repeat % 2:
                    order.reverse()
                for variant in order:
                    request = variants[variant]
                    emit(dict(event="comparison_start", case=name, variant=variant, repeat=repeat))
                    try:
                        choice = await chooser.choose(request)
                        policy = "accepted"
                        try:
                            validate_decision(choice, request, .5)
                        except ValueError as error:
                            policy = getattr(error, "code", type(error).__name__)
                        emit(dict(event="comparison_result", case=name, variant=variant,
                                  repeat=repeat, policy=policy, **asdict(choice)))
                    except Exception as error:
                        emit(dict(event="comparison_error", case=name, variant=variant,
                                  repeat=repeat, **error_details(error)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", nargs=3, action="append", required=True,
                        metavar=("NAME", "LOG", "DECISION_ID"))
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.repeats <= 5:
        parser.error("repeats must be 1..5")
    with args.log.open("x") as stream:
        def emit(event):
            stream.write(json.dumps(event, ensure_ascii=False)+"\n")
            stream.flush()
            if event["event"] not in {"comparison_input", "provider_client", "provider_answer"}:
                print(json.dumps(event), flush=True)
        asyncio.run(compare([(name, Path(path), decision) for name, path, decision in args.case],
                            args.repeats, emit, args.live))


if __name__ == "__main__":
    main()
