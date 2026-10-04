from __future__ import annotations
import sys

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, Mapping
from urllib.parse import urlsplit

Outcome = Literal["verified", "refuted", "unknown", "abstained", "budget_exhausted"]


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class Candidate:
    id: str
    description: str
    tool: str | None
    arguments: Mapping[str, Any]
    capture_id: str | None = None
    screenshot_reference: str | None = None
    aliases: tuple[str, ...] = field(default=(), kw_only=True)

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", _freeze(dict(self.arguments)))


@dataclass(frozen=True)
class VisualRegion:
    id: str
    kind: Literal["text", "icon"]
    text: str | None
    label: str | None
    confidence: float
    interactive: bool
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class VisualObservation:
    capture_id: str
    screenshot_reference: str
    screenshot_width: int
    screenshot_height: int
    pid: int
    window_id: int
    action_origin_x: float
    action_origin_y: float
    action_units_per_pixel_x: float
    action_units_per_pixel_y: float
    regions: tuple[VisualRegion, ...]

    def screenshot_center(self, region: VisualRegion) -> tuple[float, float]:
        return (region.x + region.width / 2, region.y + region.height / 2)


class VisualObservationError(ValueError):
    pass


def _nonempty(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VisualObservationError("visual result contains an empty string")
    return value


def _positive_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise VisualObservationError("visual result contains an invalid positive integer")
    return value


def _pixel_int(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise VisualObservationError("visual result contains an invalid pixel coordinate")
    return value


def parse_visual_regions(
    payload: Mapping[str, Any],
    *,
    expected_capture_id: str,
    expected_pid: int,
    expected_window_id: int,
) -> VisualObservation:
    if payload.get("schema") != "cua.visual_regions_v1":
        raise VisualObservationError("unsupported visual region schema")
    capture = payload.get("capture")
    if not isinstance(capture, dict) or capture.get("capture_id") != expected_capture_id:
        raise VisualObservationError("visual result is stale or capture-mismatched")
    source = capture.get("source")
    if (
        not isinstance(source, dict)
        or source.get("kind") != "window"
        or source.get("pid") != expected_pid
        or source.get("window_id") != expected_window_id
    ):
        raise VisualObservationError("visual result has a mismatched window target")
    screenshot = capture.get("screenshot")
    if not isinstance(screenshot, dict) or screenshot.get("mime_type") != "image/png":
        raise VisualObservationError("visual result has invalid screenshot provenance")
    screenshot_reference = _nonempty(screenshot.get("reference"))
    screenshot_width = _positive_int(screenshot.get("width"))
    screenshot_height = _positive_int(screenshot.get("height"))

    coordinate_space = capture.get("action_coordinate_space")
    if not isinstance(coordinate_space, dict):
        raise VisualObservationError("visual result has no action coordinate space")
    if coordinate_space.get("kind") == "screenshot_pixels":
        origin_x, origin_y, scale_x, scale_y = 0.0, 0.0, 1.0, 1.0
    elif coordinate_space.get("kind") == "scaled_top_left":
        values = (
            coordinate_space.get("action_origin_x"),
            coordinate_space.get("action_origin_y"),
            coordinate_space.get("action_units_per_pixel_x"),
            coordinate_space.get("action_units_per_pixel_y"),
        )
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
            raise VisualObservationError("visual result has malformed coordinate mapping")
        origin_x, origin_y, scale_x, scale_y = (float(value) for value in values)
        if not all(math.isfinite(value) for value in (origin_x, origin_y, scale_x, scale_y)):
            raise VisualObservationError("visual result has non-finite coordinate mapping")
        if scale_x <= 0 or scale_y <= 0:
            raise VisualObservationError("visual result has non-positive coordinate scale")
    else:
        raise VisualObservationError("visual result has unsupported coordinate mapping")

    raw_regions = payload.get("regions")
    if not isinstance(raw_regions, list):
        raise VisualObservationError("visual result has no region list")
    regions: list[VisualRegion] = []
    ids: set[str] = set()
    for raw in raw_regions:
        if not isinstance(raw, dict):
            raise VisualObservationError("visual result contains a malformed region")
        region_id = _nonempty(raw.get("id"))
        if region_id in ids:
            raise VisualObservationError("visual result contains duplicate region IDs")
        ids.add(region_id)
        kind = raw.get("kind")
        if kind not in {"text", "icon"}:
            raise VisualObservationError("visual result contains an unsupported region kind")
        bounds = raw.get("bounds")
        if not isinstance(bounds, dict):
            raise VisualObservationError("visual result contains malformed bounds")
        x = _pixel_int(bounds.get("x"))
        y = _pixel_int(bounds.get("y"))
        width = _positive_int(bounds.get("width"))
        height = _positive_int(bounds.get("height"))
        if x + width > screenshot_width or y + height > screenshot_height:
            raise VisualObservationError("visual region is outside its source screenshot")
        confidence = raw.get("confidence")
        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not math.isfinite(float(confidence))
            or not 0 <= float(confidence) <= 1
        ):
            raise VisualObservationError("visual result contains invalid confidence")
        text = raw.get("text")
        label = raw.get("label")
        if text is not None:
            text = _nonempty(text)
        if label is not None:
            label = _nonempty(label)
        if (kind == "text" and text is None) or (kind == "icon" and label is None):
            raise VisualObservationError("visual region is missing content required by its kind")
        if not isinstance(raw.get("interactive"), bool):
            raise VisualObservationError("visual region has malformed interactivity")
        regions.append(
            VisualRegion(
                id=region_id,
                kind=kind,
                text=text,
                label=label,
                confidence=float(confidence),
                interactive=raw["interactive"],
                x=x,
                y=y,
                width=width,
                height=height,
            )
        )

    return VisualObservation(
        capture_id=expected_capture_id,
        screenshot_reference=screenshot_reference,
        screenshot_width=screenshot_width,
        screenshot_height=screenshot_height,
        pid=expected_pid,
        window_id=expected_window_id,
        action_origin_x=origin_x,
        action_origin_y=origin_y,
        action_units_per_pixel_x=scale_x,
        action_units_per_pixel_y=scale_y,
        regions=tuple(regions),
    )


def _reserved_candidates() -> list[Candidate]:
    return [
        Candidate(
            "reobserve",
            "Discard this decision set and obtain a fresh Driver observation.",
            None,
            {},
        ),
        Candidate(
            "abstain",
            "Stop without acting if none of the proposed actions is safe for the observed state.",
            None,
            {},
        ),
    ]


def build_candidates(
    snapshot: dict[str, Any],
    token: str,
    visual: VisualObservation | None = None,
    *,
    capture_bound_click: bool = False,
) -> list[Candidate]:
    common = {
        "target_id": snapshot["target_id"],
        "tab_id": snapshot["tab_id"],
    }
    refs = snapshot.get("refs", [])
    field = next(
        (
            ref
            for ref in refs
            if ref.get("role") == "textbox" and ref.get("name") == "verification value"
        ),
        None,
    )
    button = next(
        (ref for ref in refs if ref.get("role") == "button" and ref.get("name") == "Submit"),
        None,
    )
    candidates: list[Candidate] = []
    if field and field.get("value") != token:
        candidates.append(
            Candidate(
                "type-verification-value",
                "Replace the verification field with the required token.",
                "browser_type",
                {**common, "ref": field["ref"], "text": token, "replace": True},
            )
        )
    elif field and field.get("value") == token and button:
        candidates.append(
            Candidate(
                "submit-form",
                "Submit the form now that the verification field contains the token.",
                "browser_click",
                {**common, "ref": button["ref"], "input_route": "dom_event"},
            )
        )
    elif (
        field
        and field.get("value") == token
        and visual
        and capture_bound_click
    ):
        matches = [
            region
            for region in visual.regions
            if region.interactive
            and region.confidence >= 0.8
            and _ascii_lower(region.text or region.label or "") == "submit"
        ]
        if len(matches) == 1:
            x, y = visual.screenshot_center(matches[0])
            candidates.append(
                Candidate(
                    "submit-form",
                    "Submit the form using the unique validated visual Submit region.",
                    "click",
                    {
                        "pid": visual.pid,
                        "window_id": visual.window_id,
                        "x": x,
                        "y": y,
                        "capture_id": visual.capture_id,
                        "delivery_mode": "background" if sys.platform == "darwin" else "foreground",
                    },
                    capture_id=visual.capture_id,
                    screenshot_reference=visual.screenshot_reference,
                )
            )
    return candidates + _reserved_candidates()


def _ascii_lower(value: str) -> str:
    return "".join(chr(ord(char) + 32) if "A" <= char <= "Z" else char for char in value)


def choose_mock(candidates: list[Candidate]) -> tuple[str | None, float, dict[str, float]]:
    ids = {candidate.id for candidate in candidates}
    selected = (
        "type-verification-value"
        if "type-verification-value" in ids
        else "submit-form" if "submit-form" in ids else "reobserve" if "reobserve" in ids else None
    )
    probabilities = {candidate.id: float(candidate.id == selected) for candidate in candidates}
    return selected, 1.0 if selected else 0.0, probabilities


def validate_choice(
    choice: str,
    candidates: list[Candidate],
    *,
    current_capture_id: str | None = None,
) -> Candidate:
    if not isinstance(choice, str) or not choice:
        raise ValueError("provider selected a malformed candidate ID")
    ids = [candidate.id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("candidate set contains duplicate IDs")
    candidate = next((item for item in candidates if item.id == choice), None)
    if candidate is None:
        raise ValueError(f"provider selected unknown candidate: {choice}")
    if candidate.capture_id is not None and candidate.capture_id != current_capture_id:
        raise ValueError("provider selected a stale or capture-mismatched candidate")
    return candidate


def classify(submitted: str | None, token: str, *, steps: int, max_steps: int) -> Outcome:
    if submitted == token:
        return "verified"
    if submitted is not None:
        return "refuted"
    if steps >= max_steps:
        return "budget_exhausted"
    return "unknown"


@dataclass(frozen=True)
class BrowserTask:
    """Declarative browser goal and inputs; legacy research fields are optional."""
    goal: str
    start_url: str
    allowed_hosts: tuple[str, ...]
    search_text: str
    navigation_terms: tuple[str, ...]
    observation_queries: tuple[str, ...]
    inputs: tuple[str, ...] = ()
    tool_options: tuple = ()

    @classmethod
    def parse(cls, raw):
        if (not isinstance(raw, dict) or not {"goal", "start_url", "allowed_hosts"} <= set(raw)
                or set(raw) - set(cls.__annotations__)):
            raise ValueError("invalid browser task fields")
        raw = {"search_text": "", "navigation_terms": [], "observation_queries": [],
               "inputs": [], "tool_options": [], **raw}
        for key in ("goal", "start_url"):
            if not isinstance(raw[key], str) or not raw[key].strip() or len(raw[key]) > 4000:
                raise ValueError("invalid browser task text")
        for key in ("allowed_hosts", "navigation_terms", "observation_queries"):
            if not isinstance(raw[key], list) or not (1 if key == "allowed_hosts" else 0) <= len(raw[key]) <= 12 or any(
                not isinstance(s, str) or not s.strip() or len(s) > 200 for s in raw[key]
            ):
                raise ValueError("invalid browser task terms")
        if not isinstance(raw["search_text"], str) or len(raw["search_text"]) > 4000:
            raise ValueError("invalid search text")
        if not isinstance(raw["inputs"], list) or any(not isinstance(v, str) or len(v) > 4000 for v in raw["inputs"]):
            raise ValueError("invalid browser inputs")
        from driver_candidates import ToolOption
        if not isinstance(raw["tool_options"], list):
            raise ValueError("invalid tool options")
        raw["tool_options"] = [ToolOption.parse(v) for v in raw["tool_options"]]
        task = cls(**{k: tuple(v) if isinstance(v, list) else v for k, v in raw.items()})
        task.check_url(task.start_url)
        return task

    def check_url(self, url):
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in self.allowed_hosts
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError("page outside approved HTTPS hosts")


def build_browser_candidates(snapshot: dict, task: BrowserTask, accepts=None, last_result=None) -> list[Candidate]:
    """Offer observed actions across web apps, not a research-name allowlist."""
    from driver_candidates import explicit_candidates
    task.check_url(snapshot["page"]["url"])
    common = {"target_id": snapshot["target_id"], "tab_id": snapshot["tab_id"]}
    generation = snapshot.get("snapshot", {}).get("id")
    if not isinstance(generation, str) or not generation:
        raise ValueError("missing browser snapshot identity")
    candidates = []
    seen = set()
    for row in snapshot.get("refs", []):
        ref = row.get("ref")
        if not isinstance(ref, str) or not ref.startswith(generation + ":") or ref in seen:
            raise ValueError("duplicate or stale browser reference")
        seen.add(ref)
        name = row.get("name") or ""
        if not isinstance(name, str):
            raise ValueError("invalid accessible name")
        role = row.get("role")
        actions = row.get("actions", [])
        if row.get("states", {}).get("disabled") or row.get("visibility") == "hidden":
            continue
        texts = task.inputs or ((task.search_text,) if task.search_text else ())
        if "type" in actions:
            for i, text in enumerate(texts):
                for replace in (True, False):
                    suffix = "" if i == 0 and replace else f"-{i}-{'replace' if replace else 'insert'}"
                    candidates.append(Candidate("type-" + ref + suffix,
                        f"{'Replace' if replace else 'Insert into'} {role} {name!r}: {text!r}.",
                        "browser_type", {**common, "ref": ref, "text": text, "replace": replace}))
        if "click" in actions:
            candidates.append(Candidate("click-" + ref, f"Click {role} {name!r}.", "browser_click",
                {**common, "ref": ref, "input_route": "dom_event"}))
        if accepts is not None:
            for action in ("hover", "right_click", "double_click"):
                args = {**common, "ref": ref, "action": action}
                if accepts("browser_pointer", args):
                    candidates.append(Candidate(f"pointer-{action}-{ref}", f"{action} {role} {name!r}.", "browser_pointer", args))
            for direction, delta in (("up", -500), ("down", 500)):
                args = {**common, "ref": ref, "action": "scroll", "delta_y": delta}
                if accepts("browser_pointer", args):
                    candidates.append(Candidate(f"pointer-scroll-{direction}-{ref}", f"Scroll {direction} at {role} {name!r}.", "browser_pointer", args))
    for row in snapshot.get("content_refs", []):
        ref, name = row.get("ref"), row.get("name") or ""
        if row.get("role") not in {"region", "article"} or not isinstance(name, str):
            continue
        if not isinstance(ref, str) or not ref.startswith(generation + ":") or ref in seen:
            raise ValueError("duplicate or stale content reference")
        seen.add(ref)
        candidates.append(Candidate("scope-" + ref, f"Read the full {row['role']} {name!r}, including surrounding source text.",
            "get_browser_state", {**common, "snapshot_format": "semantic_v2", "scope_ref": ref}))
    for i, query in enumerate(task.observation_queries):
        candidates.append(Candidate(f"read-{i}", f"Read page evidence matching {query!r}; does not search the website.",
            "get_browser_state", {**common, "snapshot_format": "semantic_v2", "query": query}))
    continuation = snapshot.get("snapshot", {}).get("continuation")
    if continuation:
        candidates.append(Candidate("read-more", "Read the next available page-evidence segment.",
            "get_browser_state", {**common, "snapshot_format": "semantic_v2", "continuation": continuation}))
    if accepts is not None:
        args = {**common, "action": "inspect"}
        if accepts("browser_dialog", args):
            candidates.append(Candidate("dialog-inspect", "Inspect the current browser dialog.", "browser_dialog", args))
        targets = [{"ref": row["ref"]} for row in snapshot.get("refs", [])
                   if not row.get("states", {}).get("disabled") and row.get("visibility") != "hidden"]
        candidates += explicit_candidates(task.tool_options, {**common, "snapshot_id": generation,
                                          "result": last_result or {}}, accepts, targets)
        candidates = [c for c in candidates if c.tool is None or accepts(c.tool, dict(c.arguments))]
    candidates.append(Candidate("finish", "Hand the relevant source passage to the calling assistant for review and answering. You navigate; do not answer the question yourself or claim verification.", None, {}))
    return candidates + _reserved_candidates()
