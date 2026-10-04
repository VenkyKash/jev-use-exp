import sys
"""Generate options from observed roles, never from an app-specific solution."""
from dataclasses import dataclass
from typing import Callable

from core import Candidate
from native_core import Observation, Task
from native_errors import DiagnosticError
from driver_candidates import native_extras


@dataclass(frozen=True)
class CandidateSet:
    observation_id: str
    candidates: tuple[Candidate, ...]

    def resolve(self, selected_id: str, current_id: str) -> Candidate:
        if current_id != self.observation_id:
            raise ValueError("stale decision set")
        matches = [c for c in self.candidates if c.id == selected_id]
        if len(matches) != 1:
            raise ValueError("unknown or duplicate candidate ID")
        return matches[0]


def reserved() -> list[Candidate]:
    return [Candidate("reobserve", "Obtain a fresh full-window observation without acting; leave any query scope.", None, {}),
            Candidate("abstain", "Stop if no supplied action can safely advance the goal.", None, {})]


def build_native_candidates(task: Task, observation: Observation,
                            accepts: Callable[[str, dict], bool], *, diagnostics=None,
                            read_only=False, last_result=None) -> CandidateSet:
    candidates = []
    if read_only:
        accepts = lambda *_: False
    for element in observation.elements:
        before = len(candidates)
        reasons = []
        if not element.enabled:
            if diagnostics is not None:
                diagnostics.append(dict(element_index=element.index, role=element.role,
                    actions=list(element.actions), parent=element.parent, candidate_ids=[],
                    reasons=["disabled"]))
            continue

        target = {"pid": observation.pid, "window_id": observation.window_id,
                  "delivery_mode": "background" if sys.platform == "darwin" else "foreground"}
        if element.token:
            target["element_token"] = element.token
        else:
            target.update(element_index=element.index, snapshot_id=observation.id)
        child_labels = [e.label or e.value for e in observation.elements
                        if e.parent == element.index and (e.label or e.value)]
        label = element.label or element.value or " / ".join(child_labels[:4]) or "(unlabelled)"
        context = f"{element.role} {label!r} (element {element.index}, parent {element.parent})"
        # v0 understands common native roles and explicitly advertised AXPress.
        # Unknown roles remain visible to Jev but don't acquire invented actions.
        actions = {a.removeprefix("AX").replace("_", "").lower() for a in element.actions}
        if "press" in actions or element.role in {"AXButton", "AXCheckBox", "AXRadioButton", "AXRow", "AXCell", "AXLink", "AXMenuItem", "AXPopUpButton", "AXComboBox", "AXTab"}:
            if accepts("click", target):
                candidates.append(Candidate(f"click-{element.index}", f"Click {context}.", "click", target))
            else:
                reasons.append("read_only_policy" if read_only else "click_schema_rejected")
        if element.role in {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox"}:
            for number, text in enumerate(task.inputs):
                arguments = {**target, "text": text}
                if accepts("type_text", arguments):
                    candidates.append(Candidate(f"type-{element.index}-{number}",
                        f"Insert supplied text {text!r} at the cursor in {context}; this does not replace existing text.",
                        "type_text", arguments))
                else:
                    reasons.append("read_only_policy" if read_only else "type_schema_rejected")
            if not task.inputs:
                reasons.append("no_supplied_text")
        if diagnostics is not None:
            ids = [c.id for c in candidates[before:]]
            diagnostics.append(dict(element_index=element.index, role=element.role,
                actions=list(element.actions), parent=element.parent, candidate_ids=ids,
                reasons=sorted(set(reasons)) if reasons else ([] if ids else ["no_supported_action"])))
    if not read_only:
        # Observed labels supply queries mechanically. Jev selects what to inspect;
        # no task-specific selector, inferred coordinates, or new model is involved.
        seen_queries = set()
        for element in observation.elements:
            query = element.label.strip()
            if not query or query.casefold() in seen_queries:
                continue
            seen_queries.add(query.casefold())
            arguments = dict(pid=observation.pid, window_id=observation.window_id,
                             include_screenshot=True, query=query)
            if accepts("get_window_state", arguments):
                candidates.append(Candidate(f"inspect-{element.index}",
                    f"Read-only inspection of matching text {query!r} and ancestors; does not click or change the app.",
                    "get_window_state", arguments))
        extras = native_extras(task, observation, accepts, last_result)
        candidates.extend(extras)
        if diagnostics is not None:
            for row in diagnostics:
                index = row["element_index"]
                row["candidate_ids"].extend(c.id for c in extras
                    if c.arguments.get("element_index") == index or
                    (c.arguments.get("element_token") is not None and
                     c.arguments.get("element_token") == next(e.token for e in observation.elements if e.index == index)))
                if row["candidate_ids"]:
                    row["reasons"] = [r for r in row["reasons"] if r != "no_supported_action"]
    if observation.readback_text:
        candidates.append(Candidate("review", "Hand the current readback evidence to the calling assistant when the requested actions are complete. Do not answer or claim verification yourself.", None, {}))
    return CandidateSet(observation.id, tuple(candidates + reserved()))
