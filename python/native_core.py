"""App-independent native v0 models. No provider or Driver I/O here."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

from core import Candidate


@dataclass(frozen=True)
class Check:
    role: str
    label: str
    equals: str


@dataclass(frozen=True)
class Task:
    goal: str
    app: str
    inputs: tuple[str, ...]
    checks: tuple[Check, ...]

    @classmethod
    def parse(cls, raw: dict[str, Any]) -> Task:
        if not isinstance(raw, dict) or set(raw) != {"goal", "app", "inputs", "checks"}:
            raise ValueError("task requires exactly goal, app, inputs, checks")
        for field in ("goal", "app"):
            if not isinstance(raw[field], str) or not raw[field].strip() or len(raw[field]) > 4000:
                raise ValueError(f"invalid task {field}")
        inputs = raw["inputs"]
        if not isinstance(inputs, list) or len(inputs) > 8 or any(
            not isinstance(s, str) or not s or len(s) > 1000 for s in inputs
        ):
            raise ValueError("inputs must be at most eight nonempty strings of up to 1000 characters")
        checks = raw["checks"]
        if not isinstance(checks, list) or not 1 <= len(checks) <= 8:
            raise ValueError("provide one to eight exact UI readback checks")
        parsed = []
        for check in checks:
            if not isinstance(check, dict) or set(check) != {"role", "label", "equals"} or any(
                not isinstance(s, str) or len(s) > 1000 for s in check.values()
            ) or not check["role"]:
                raise ValueError("invalid check; requires role, label, equals strings")
            parsed.append(Check(**check))
        return cls(raw["goal"], raw["app"], tuple(dict.fromkeys(inputs)), tuple(parsed))


@dataclass(frozen=True)
class Element:
    index: int
    role: str
    label: str
    value: str | None
    token: str | None
    actions: tuple[str, ...]
    enabled: bool
    parent: int | None
    web: bool


@dataclass(frozen=True)
class Observation:
    id: str
    pid: int
    window_id: int
    elements: tuple[Element, ...]
    excluded_menu_elements: int = 0
    complete: bool = True

    def compact(self) -> list[dict[str, Any]]:
        return [dict(id=e.index, role=e.role, label=e.label, value=e.value,
                     actions=list(e.actions), enabled=e.enabled, parent=e.parent)
                for e in self.elements]

    def fingerprint(self) -> str:
        # Snapshot tokens rotate even when the UI does not change.
        return hashlib.sha256(json.dumps(self.compact(), sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Decision:
    selected_id: str
    confidence: float
    probabilities: dict[str, float]
    model: str | None


@dataclass(frozen=True)
class StepResult:
    selected_id: str
    description: str
    outcome: str
    changed: bool


def verify(task: Task, observation: Observation) -> bool:
    """Exact unique element value checks, never model or action-response proof."""
    if not observation.complete:
        return False
    for check in task.checks:
        matches = [e for e in observation.elements
                   if e.role == check.role and e.label == check.label and not e.web]
        if len(matches) != 1 or matches[0].value != check.equals:
            return False
    return True
