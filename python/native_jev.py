"""Jev owns selection; no generated arguments, solution sequence, or fallback."""
from __future__ import annotations

import math
import random
from dataclasses import asdict

from native_candidates import CandidateSet
from native_core import Decision, Observation, StepResult, Task
from jev_adapter import choose_bounded_with_typesafe
from native_errors import DiagnosticError


def application_context(task, observation):
    observed = observation.app_name if observation else None
    name = observed or task.app
    # Identity hints only: this table never selects controls, shortcuts, or actions.
    types = {
        "google chrome": "web_browser", "chrome": "web_browser",
        "safari": "web_browser", "firefox": "web_browser",
        "microsoft edge": "web_browser", "brave browser": "web_browser",
        "visual studio code": "code_editor", "vscode": "code_editor",
        "code": "code_editor", "cursor": "code_editor", "xcode": "ide",
        "textedit": "text_editor", "obsidian": "note_editor",
        "microsoft excel": "spreadsheet", "calculator": "calculator",
    }
    kind = types.get(name.strip().casefold(), "unknown")
    return {"name": name, "name_source": "observed" if observed else "task",
            "type": kind, "type_source": "inferred_from_app_name" if kind != "unknown" else "unknown",
            "window_title": observation.window_title if observation else None}


def decision_request(task: Task, observation: Observation | None,
                     candidates: CandidateSet, history: list[StepResult],
                     remaining: int, seed: int, before: Observation | None = None) -> dict:
    options = list(candidates.candidates)
    random.Random(seed).shuffle(options)
    elements = observation.compact() if observation else []
    total = len(elements)
    readback = observation.readback_text if observation else ""
    request = {
        "goal": task.goal,
        "application": application_context(task, observation),
        "observation": {
            "snapshot_id": observation.id if observation else candidates.observation_id,
            "pid": observation.pid if observation else None,
            "window_id": observation.window_id if observation else None,
            "application": application_context(task, observation),
            "background_input": observation.background_input if observation else None,
            "scope": "window_content; application and system menu trees excluded",
            "excluded_menu_elements": observation.excluded_menu_elements if observation else 0,
            "complete": observation.complete if observation else True,
            "inspection": observation.inspection if observation else None,
            "availability": observation.availability if observation else None,
            "geometry": observation.geometry if observation else None,
            "elements": elements,
            "element_count": total,
            "context_elements_omitted": total-len(elements),
            "readback_text": readback[:12000],
            "readback_characters_omitted": max(0, len(readback)-12000),
            "context_scope": ("Local hierarchy branch/page plus its parent. Other controls remain reachable through inspection choices; see inspection metadata."
                              if observation and (observation.inspection or {}).get("kind") == "local_hierarchy"
                              else "All normalized window-content elements; no first-N or candidate-target filtering. Readback text may be bounded separately."),
        },
        "criteria": {candidate.id: candidate.description for candidate in options},
    }
    current = request["observation"]
    from native_geometry import AreaClick
    areas = {c.id: dict(target=c.target_index, area=c.area_index, method="coordinates")
             for c in options if isinstance(c, AreaClick)}
    if areas:
        current["click_targets"] = areas
    if observation and observation.root_context is not None:
        current["root"] = observation.root_context
    # Current-only trial. Keep the optional before argument for easy rollback;
    # history and local execution/readback state remain unchanged.
    request["observation"] = {"current": current,
                              "inputs": list(task.inputs), "remaining_decisions": remaining}
    request["history"] = [asdict(step) if isinstance(step, StepResult) else step for step in history[-12:]]
    # task.goal is the caller's prompt, not an inferred plan or progress model.
    return request


def validate_decision(choice: Decision, request: dict, minimum_confidence: float) -> None:
    criteria = request["criteria"]
    if choice.selected_id not in criteria:
        raise DiagnosticError("unknown_choice", "provider selected an unknown candidate")
    if not math.isfinite(choice.confidence) or not minimum_confidence <= choice.confidence <= 1:
        raise DiagnosticError("confidence_rejected", "invalid or insufficient confidence", minimum_confidence=minimum_confidence)
    # Full distributions make candidate-order comparisons auditable.
    if set(choice.probabilities) != set(criteria):
        raise DiagnosticError("probability_keys", "provider must score exactly the supplied candidates")
    values = list(choice.probabilities.values())
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
        raise DiagnosticError("invalid_probability", "invalid candidate probability")
    # Preserve the intended inclusive one-percent rounding tolerance at 0.99/1.01.
    if not math.isclose(sum(values), 1, rel_tol=0, abs_tol=0.01 + 1e-12):
        raise DiagnosticError("probability_sum", "candidate probabilities must sum to one", probability_sum=sum(values))


class JevChooser:
    def __init__(self, client, emit=lambda event: None):
        self.client = client
        self.emit = emit

    async def choose(self, request: dict) -> Decision:
        import asyncio
        owner = self
        class RecordingClient:
            def system_one(self, **kwargs):
                response = owner.client.system_one(**kwargs)
                answer = response.choices.get("driver_action") or response.choices.get("candidate")
                usage = getattr(response, "usage", None)
                owner.emit(dict(event="provider_answer", model=getattr(response, "model", None),
                    selected_id=getattr(answer, "choice", None),
                    confidence=getattr(answer, "confidence", None),
                    probabilities=getattr(answer, "probabilities", None),
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None)))
                return response
        try:
            result = await asyncio.to_thread(choose_bounded_with_typesafe, RecordingClient(), **request)
        except DiagnosticError:
            raise
        except ValueError as error:
            raise DiagnosticError("provider_response_invalid", "provider response failed adapter validation") from error
        return Decision(result.selected_id, result.confidence, result.probabilities, result.model)


class FirstCandidateBaseline:
    """Explicit evaluation baseline. Never used as a live fallback."""
    async def choose(self, request: dict) -> Decision:
        selected = next((key for key in request["criteria"] if key not in {"reobserve", "abstain"}), "abstain")
        return Decision(selected, 1, {key: float(key == selected) for key in request["criteria"]}, "baseline-first")
