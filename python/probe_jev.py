"""One identifiable Jev request with HTTP evidence, no Driver or desktop actions."""
import argparse
import asyncio
import json
from pathlib import Path
import uuid

from native_audit import audited_client
from native_jev import JevChooser, validate_decision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    args = parser.parse_args()
    marker = "jev-exp-probe-"+uuid.uuid4().hex[:12]
    with args.log.open("x", encoding="utf-8") as stream:
        def emit(event):
            line = json.dumps(event, sort_keys=True)
            print(line, flush=True)
            stream.write(line+"\n")
            stream.flush()
        request = dict(goal=f"Diagnostic {marker}: select acknowledge. This does not control a computer.",
                       observation={"diagnostic_marker": marker},
                       criteria={"acknowledge": "Acknowledge this diagnostic request.",
                                 "abstain": "Decline this diagnostic request."})
        emit(dict(event="probe", marker=marker))
        with audited_client(emit) as client:
            choice = asyncio.run(JevChooser(client, emit=emit).choose(request))
            validate_decision(choice, request, 0)
        emit(dict(event="probe_complete", selected_id=choice.selected_id, model=choice.model,
                  note="HTTP evidence does not establish dashboard workspace attribution"))


if __name__ == "__main__":
    main()
