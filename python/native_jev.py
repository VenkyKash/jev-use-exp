"""Jev owns selection; no generated arguments, solution sequence, or fallback."""
from __future__ import annotations

import math
import random
from dataclasses import asdict

from native_candidates import CandidateSet
from native_core import Decision, Observation, StepResult, Task
from jev_adapter import choose_bounded_with_typesafe
from native_errors import DiagnosticError


def decision_request(task: Task, observation: Observation | None,
                     candidates: CandidateSet, history: list[StepResult],
                     remaining: int, seed: int) -> dict:
    options = list(candidates.candidates)
    random.Random(seed).shuffle(options)
    return {
        "goal": task.goal,
        "observation": {
            "snapshot_id": candidates.observation_id,
            "scope": "window_content; application and system menu trees excluded",
            "excluded_menu_elements": observation.excluded_menu_elements if observation else 0,
            "complete": observation.complete if observation else True,
            "elements": observation.compact() if observation else [],
            "readback_text": observation.readback_text if observation else "",
            "inputs": list(task.inputs),
            "history": [asdict(step) for step in history[-12:]],
            "remaining_decisions": remaining,
        },
        "criteria": {candidate.id: candidate.description for candidate in options},
    }


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
                answer = response.choices.get("candidate")
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
        except ValueError as error:
            raise DiagnosticError("provider_response_invalid", "provider response failed adapter validation") from error
        return Decision(result.selected_id, result.confidence, result.probabilities, result.model)


class FirstCandidateBaseline:
    """Explicit evaluation baseline. Never used as a live fallback."""
    async def choose(self, request: dict) -> Decision:
        selected = next((key for key in request["criteria"] if key not in {"reobserve", "abstain"}), "abstain")
        return Decision(selected, 1, {key: float(key == selected) for key in request["criteria"]}, "baseline-first")
