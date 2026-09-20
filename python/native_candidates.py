"""Generate options from observed roles, never from an app-specific solution."""
from dataclasses import dataclass
from typing import Callable

from core import Candidate
from native_core import Observation, Task
from native_errors import DiagnosticError


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
    return [Candidate("reobserve", "Obtain a fresh observation without acting.", None, {}),
            Candidate("abstain", "Stop if no supplied action can safely advance the goal.", None, {})]


def build_native_candidates(task: Task, observation: Observation,
                            accepts: Callable[[str, dict], bool]) -> CandidateSet:
    candidates = []
    for element in observation.elements:
        if not element.enabled or element.web or not element.label.strip():
            continue
        target = {"pid": observation.pid, "window_id": observation.window_id,
                  "delivery_mode": "background"}
        if element.token:
            target["element_token"] = element.token
        else:
            target.update(element_index=element.index, snapshot_id=observation.id)
        context = f"{element.role} {element.label!r} (element {element.index}, parent {element.parent})"
        # v0 understands common native roles and explicitly advertised AXPress.
        # Unknown roles remain visible to Jev but don't acquire invented actions.
        if "AXPress" in element.actions or element.role in {"AXButton", "AXCheckBox", "AXRadioButton"}:
            if accepts("click", target):
                candidates.append(Candidate(f"click-{element.index}", f"Click {context}.", "click", target))
        if element.role in {"AXTextField", "AXTextArea", "AXSearchField"}:
            for number, text in enumerate(task.inputs):
                arguments = {**target, "text": text}
                if accepts("type_text", arguments):
                    candidates.append(Candidate(f"type-{element.index}-{number}",
                        f"Insert supplied text {text!r} at the cursor in {context}; this does not replace existing text.",
                        "type_text", arguments))
    maximum = 61 if observation.readback_text else 62
    if len(candidates) > maximum:
        raise DiagnosticError("candidate_limit", "candidate set exceeds 64 total choices; v0 refuses instead of hiding alternatives",
                              executable_options=len(candidates))
    if observation.readback_text:
        candidates.append(Candidate("review", "Hand the current readback evidence to the calling assistant when the requested actions are complete. Do not answer or claim verification yourself.", None, {}))
    return CandidateSet(observation.id, tuple(candidates + reserved()))
