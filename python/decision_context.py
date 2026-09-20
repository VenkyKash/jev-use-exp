"""Experimental factual context projection. Not wired into production runners."""
import copy
import json
import re


def readable_state(observation):
    """Keep source facts; unsupported markdown shapes remain explicitly unknown."""
    values = []
    for element in observation.get("elements", []):
        value = element.get("value")
        if isinstance(value, str) and value:
            values.append(dict(role=element.get("role"), label=element.get("label"),
                               text=value, source="structured_value"))
    unsupported = 0
    for line in observation.get("readback_text", "").splitlines():
        if "AXStaticText" not in line:
            continue
        match = re.fullmatch(r'\s*- (?:\[\d+\] )?AXStaticText = ("(?:[^"\\]|\\.)*")\s*', line)
        if not match:
            unsupported += 1
            continue
        try:
            text = json.loads(match.group(1))
        except ValueError:
            unsupported += 1
            continue
        # Presentation only; original evidence stays unchanged in the source log.
        text = text.replace("\u200e", "").replace("\u200f", "")
        if not any(v["text"] == text for v in values):
            values.append(dict(role="AXStaticText", label=None, text=text,
                               source="window_markdown"))
    return values, unsupported


def format_context(request, previous_observation=None):
    """Same goal and ordered choices, factual current state, optional prior state.

    This does not interpret the task, rank controls, infer success, or prescribe
    a correction. Choice descriptions already contain the actionable controls.
    """
    observation = request["observation"]
    values, unsupported = readable_state(observation)
    windows = [e.get("label") for e in observation.get("elements", []) if e.get("role") == "AXWindow"]
    history = copy.deepcopy(observation.get("history", []))
    last = history[-1] if history else None
    if last is not None:
        last = dict(action=last.get("description"), action_id=last.get("selected_id"),
                    reported_outcome=last.get("outcome"), task_completion="not_evaluated",
                    before=readable_state(previous_observation)[0] if previous_observation else None,
                    after=values)
    context = dict(schema="jev.decision_context.experimental.v1",
        location=dict(window_titles=windows),
        current_state=dict(readable_values=values, focused_control=None, dialogs=None),
        last_action=last, recent_history=history[:-1],
        supplied_inputs=copy.deepcopy(observation.get("inputs", [])),
        remaining_decisions=observation.get("remaining_decisions"),
        observation_quality=dict(snapshot_id=observation.get("snapshot_id"),
            structured_elements_complete=observation.get("complete"),
            readable_values_complete=None, unsupported_text_rows=unsupported,
            scope=observation.get("scope"),
            excluded_menu_elements=observation.get("excluded_menu_elements"),
            action_controls="see supplied choice descriptions; not duplicated here",
            omitted_context="raw roles/actions and toolbar metadata not repeated; focus/dialog detection unsupported",
            text_display_normalization="LRM/RLM formatting marks removed; original text retained in source trace"))
    return dict(goal=request["goal"], observation=context, criteria=copy.deepcopy(request["criteria"]))
