"""Jev owns selection; no generated arguments, solution sequence, or fallback."""
from __future__ import annotations

import math
import random
from dataclasses import asdict

from native_candidates import CandidateSet
from native_core import Decision, Observation, StepResult, Task
from jev_adapter import choose_bounded_with_typesafe


def decision_request(task: Task, observation: Observation | None,
                     candidates: CandidateSet, history: list[StepResult],
                     remaining: int, seed: int) -> dict:
    options = list(candidates.candidates)
    random.Random(seed).shuffle(options)
    return {
        "goal": task.goal,
        "observation": {
            "snapshot_id": candidates.observation_id,
            "elements": observation.compact() if observation else [],
            "inputs": list(task.inputs),
            "history": [asdict(step) for step in history[-12:]],
            "remaining_decisions": remaining,
        },
        "criteria": {candidate.id: candidate.description for candidate in options},
    }


def validate_decision(choice: Decision, request: dict, minimum_confidence: float) -> None:
    criteria = request["criteria"]
    if choice.selected_id not in criteria:
        raise ValueError("provider selected an unknown candidate")
    if not math.isfinite(choice.confidence) or not minimum_confidence <= choice.confidence <= 1:
        raise ValueError("invalid or insufficient confidence")
    # Full distributions make candidate-order comparisons auditable.
    if set(choice.probabilities) != set(criteria):
        raise ValueError("provider must score exactly the supplied candidates")
    values = list(choice.probabilities.values())
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in values):
        raise ValueError("invalid candidate probability")
    if not math.isclose(sum(values), 1, abs_tol=0.01):
        raise ValueError("candidate probabilities must sum to one")


class JevChooser:
    def __init__(self, client):
        self.client = client

    async def choose(self, request: dict) -> Decision:
        import asyncio
        result = await asyncio.to_thread(choose_bounded_with_typesafe, self.client, **request)
        return Decision(result.selected_id, result.confidence, result.probabilities, result.model)


class FirstCandidateBaseline:
    """Explicit evaluation baseline. Never used as a live fallback."""
    async def choose(self, request: dict) -> Decision:
        selected = next((key for key in request["criteria"] if key not in {"reobserve", "abstain"}), "abstain")
        return Decision(selected, 1, {key: float(key == selected) for key in request["criteria"]}, "baseline-first")
