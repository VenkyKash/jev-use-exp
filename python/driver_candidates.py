"""Schema-backed Driver options and bounded, lossless Jev choice menus.

Finite UI options are automatic. Open-ended arguments (paths, rectangles, scripts,
settings, etc.) come from explicit task options, never fabricated from a schema.
"""
from dataclasses import dataclass, replace
from collections import defaultdict
import json
import math

from core import Candidate
from native_errors import DiagnosticError


def thaw(value):
    from collections.abc import Mapping
    if isinstance(value, Mapping):
        return {k: thaw(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(v) for v in value]
    return value


@dataclass(frozen=True)
class ToolOption:
    tool: str
    arguments: dict

    @classmethod
    def parse(cls, raw):
        if (not isinstance(raw, dict) or set(raw) != {"tool", "arguments"}
                or not isinstance(raw["tool"], str) or not raw["tool"]
                or not isinstance(raw["arguments"], dict)):
            raise ValueError("tool option requires tool and arguments")
        # JSON task data only; immutable when compiled to Candidate.
        json.dumps(raw, allow_nan=False)
        return cls(raw["tool"], raw["arguments"])


def bind(value, bindings):
    if isinstance(value, str) and value.startswith("$"):
        current = bindings
        for part in value[1:].split("."):
            if not isinstance(current, dict) or part not in current:
                raise ValueError("unavailable argument binding: " + value)
            current = current[part]
        return current
    if isinstance(value, dict):
        return {k: bind(v, bindings) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [bind(v, bindings) for v in value]
    return value


def explicit_candidates(options, bindings, accepts, elements=()):
    result = []
    for i, option in enumerate(options):
        def references(value):
            if isinstance(value, dict):
                return set().union(*(references(v) for v in value.values()))
            if isinstance(value, (list, tuple)):
                return set().union(*(references(v) for v in value))
            return {value} if isinstance(value, str) and value.startswith("$") else set()
        refs = references(option.arguments)
        element_bound = bool(refs & {"$element_index", "$element_token", "$ref"})
        targets = list(elements) if element_bound else [{}]
        if element_bound and not targets:
            continue  # A future observation may supply the required targets.
        for number, target in enumerate(targets):
            try:
                args = bind(option.arguments, {**bindings, **target})
            except ValueError as error:
                if str(error).startswith("unavailable argument binding: $result."):
                    continue
                raise
            if "session" in args:
                raise ValueError("session belongs to the runner, not task options")
            if not accepts(option.tool, args):
                raise DiagnosticError("invalid_tool_option", "task option not accepted by advertised Driver schema",
                                      tool=option.tool, option=i)
            result.append(Candidate(f"tool-option-{i}-{number}",
                f"{option.tool} with task-supplied arguments {json.dumps(args, sort_keys=True)}",
                option.tool, args))
    return result


def catalog(schemas, candidates):
    counts = defaultdict(int)
    for candidate in candidates:
        if candidate.tool:
            counts[candidate.tool] += 1
    return [{"tool": name, "candidate_count": counts[name],
             "status": "ready" if counts[name] else "needs_task_arguments_or_observed_target",
             "required": schema.get("required", []), "input_schema": schema}
            for name, schema in sorted(schemas.items())]


def normalize_candidates(candidates):
    """Snapshot-local exact-call deduplication, not semantic similarity matching.

    Preserve the first candidate's ID, subclass and immutable execution arguments.
    Capture guards remain part of identity; omitted arguments are not defaults.
    """
    if len({c.id for c in candidates}) != len(candidates):
        raise ValueError("duplicate candidate IDs")
    result, positions = [], {}
    for candidate in candidates:
        if candidate.tool is None:
            result.append(candidate)
            continue
        key = (candidate.tool, json.dumps(thaw(candidate.arguments), sort_keys=True,
                    separators=(",", ":"), allow_nan=False),
               candidate.capture_id, candidate.screenshot_reference)
        if key not in positions:
            positions[key] = len(result)
            result.append(candidate)
            continue
        index = positions[key]
        canonical = result[index]
        aliases = tuple(dict.fromkeys((*canonical.aliases,
            f"{candidate.id}: {candidate.description}", *candidate.aliases)))
        result[index] = replace(canonical, aliases=aliases)
    return result


def choice_menu(candidates, path=(), width=48):
    """Every candidate remains reachable; group selection never dispatches a tool."""
    candidates = normalize_candidates(candidates)
    controls = [c for c in candidates if c.tool is None]
    selected = [c for c in candidates if c.tool is not None]
    groups = {}
    for index in path:
        _, groups = _partition(selected, width)
        if index not in groups:
            raise ValueError("invalid candidate group")
        selected = groups[index]
    if len(selected) + len(controls) <= 64:
        return selected + controls, {}
    menu, groups = _partition(selected, width)
    return menu + controls, groups


def _partition(candidates, width):
    families = defaultdict(list)
    for candidate in candidates:
        families[candidate.tool].append(candidate)
    if 1 < len(families) <= width:
        chunks = list(families.values())
    else:
        size = max(1, math.ceil(len(candidates) / width))
        chunks = [candidates[i:i+size] for i in range(0, len(candidates), size)]
    groups = {f"group-{i}": chunk for i, chunk in enumerate(chunks)}
    menu = []
    for key, chunk in groups.items():
        tools = sorted({c.tool for c in chunk})
        # Boundary labels make all consecutive target ranges discoverable.
        description = (f"Inspect {len(chunk)} options for {', '.join(tools)}. "
                       f"First: {chunk[0].description[:180]} Last: {chunk[-1].description[:180]}")
        menu.append(Candidate(key, description, None, {}))
    return menu, groups


KEYS = ("return", "tab", "escape", "space", "backspace", "delete",
        "left", "right", "up", "down", "home", "end", "pageup", "pagedown")


def native_extras(task, observation, accepts, result=None):
    candidates = []
    base = dict(pid=observation.pid, window_id=observation.window_id)
    background = {**base, "delivery_mode": "background"}
    availability = observation.availability or {}
    unavailable = not observation.elements or availability.get("degraded") is True
    has_geometry = set()
    if not unavailable:
        from native_geometry import area_clicks, center
        candidates.extend(area_clicks(observation, accepts))
        has_geometry = {e.index for e in observation.elements if center(e, observation) is not None}
    if (unavailable or availability.get("on_current_space") is False
            or availability.get("is_on_screen") is False):
        if accepts("bring_to_front", base):
            candidates.append(Candidate("activate-window",
                "Bring this exact window to the foreground/current Space to recover visibility, then obtain fresh controls. Sends no keys or text; leaves the window foreground for the task.",
                "bring_to_front", base))
    def add(id, description, tool, args):
        if unavailable and tool in {"press_key", "hotkey", "type_text", "scroll"}:
            return
        if tool in {"press_key", "hotkey", "type_text"} and args.get("delivery_mode") == "background":
            routes = (observation.background_input or {}).get("routes", [])
            route = next((r for r in routes if isinstance(r, dict) and r.get("route") == "pid_keyboard"), {})
            foreground = {**args, "delivery_mode": "foreground"}
            if accepts(tool, foreground):
                candidates.append(Candidate(id + "-foreground",
                    description + " Briefly front this exact window for foreground delivery, then restore prior focus.",
                    tool, foreground))
            if route.get("status") == "refused":
                return
        if accepts(tool, args):
            candidates.append(Candidate(id, description, tool, args))
    for key in KEYS:
        add("key-" + key, f"Press {key} in the currently focused control.",
            "press_key", {**background, "key": key})
    # Typing requires an observed field target. No generic focused typing:
    # window activation alone does not establish the receiving control.
    for keys in (("cmd", "a"), ("cmd", "c"), ("cmd", "v"), ("cmd", "z"),
                 ("cmd", "shift", "z"), ("shift", "tab"), ("cmd", "t"),
                 ("cmd", "l"),
                 ("shift", "down"), ("shift", "up"), ("cmd", "d"),
                 ("cmd", "shift", "down"), ("cmd", "shift", "up"),
                 ("cmd", "shift", "right"), ("cmd", "shift", "left")):
        add("hotkey-" + "-".join(keys), f"Press hotkey {'+'.join(keys)} in the focused control.",
            "hotkey", {**background, "keys": list(keys)})
    for direction in ("up", "down", "left", "right"):
        add("scroll-" + direction, f"Scroll the current window {direction} one page.",
            "scroll", {**background, "direction": direction, "amount": 1, "by": "page"})
    result = result or {}
    for element in observation.elements:
        if not element.enabled:
            continue
        target = {**base, **({"element_token": element.token} if element.token else
                           {"element_index": element.index, "snapshot_id": observation.id})}
        context = f"{element.role} {element.label or element.value or '(unlabelled)'!r} (element {element.index})"
        actions = {a.removeprefix("AX").replace("_", "").lower() for a in element.actions}
        if element.actions or element.role in {"AXRow", "AXCell", "AXLink", "AXTextField", "AXTextArea"}:
            for tool in ("double_click", "right_click"):
                add(f"{tool}-{element.index}", f"{tool} {context}.", tool,
                    {**target, "delivery_mode": "background"})
        if element.index not in has_geometry:
            for action, advertised in (("show_menu", "showmenu"), ("pick", "pick"),
                                        ("confirm", "confirm"), ("cancel", "cancel"), ("open", "open")):
                if advertised in actions:
                    add(f"action-{element.index}-{action}", f"{action} on {context}.", "click",
                        {**target, "delivery_mode": "background", "action": action})
        if element.role in {"AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXPopUpButton", "AXSlider", "AXStepper"}:
            for i, text in enumerate(task.inputs):
                add(f"set-{element.index}-{i}", f"Replace value of {context} with {text!r}.",
                    "set_value", {**target, "value": text})
    for i, path in enumerate(observation.menu_paths):
        add(f"menu-{i}", f"Invoke observed application menu {' > '.join(path)}.",
            "invoke_menu", {**base, "path": list(path)})
    targets = [{"element_index": e.index, "element_token": e.token}
               for e in observation.elements if e.enabled and e.token]
    candidates += explicit_candidates(task.tool_options,
        {**base, "snapshot_id": observation.id, "result": result}, accepts, targets)
    return candidates
