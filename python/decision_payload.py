"""Compact, descriptive Jev payloads; never a second action dispatcher."""

INSTRUCTIONS = {
    "question": "Which supplied choice should be selected next to advance the goal?",
    "consider": ["observation.before", "observation.current", "history"],
    "rules": [
        "A group expands choices without executing an action.",
        "When hierarchy inspection is active, the visible controls are only one branch/page, not the whole app. If they do not fit the goal, inspect more options: use supplied tree-next/tree-previous for sibling pages, tree-expand-* to go deeper, and tree-parent/tree-root to leave a branch and explore another. These are read-only inspection choices, not app navigation. Do not infer that an unseen control is absent or repeatedly click an unrelated visible control instead of exploring.",
        "Select an executable candidate or a supplied control; the tool catalog is capability information, not authorization.",
        "A changed observation or successful tool call does not establish task completion.",
        "Respect task.required_sequence and input purposes. Entered text does not prove navigation. Handoff requires observed evidence for task.success and task.relevance.",
        "Candidate inherit lists name exact argument values in state.bindings; remaining arguments are in args.",
        "Resolve $ref from state.shared_values. Resolve template from state.action_templates; merge args and overlay candidate fields. Description is description_prefix plus description_suffix. References describe choices, not extra actions.",
        "Element rows use columns; dictionary cells index dictionaries[column]. defaults apply to every row, overridden by overrides[row_index]. No controls are dropped. A before encoded as current_patch_v1 is reconstructed from current by applying set/remove operations at array-valued paths; these are serialization differences, not inferred UI identity matches.",
    ],
}


def compact_request(state, criteria):
    """Bound previews for transport; full schemas/candidates remain in the driver.

    This is a capability index, not a replacement validation schema. All group
    children remain reachable by selecting their group.
    """
    import copy
    state, criteria = copy.deepcopy(state), copy.deepcopy(criteria)
    for name in ("before", "current"):
        observation = state.get("observation", {}).get(name)
        if isinstance(observation, dict) and isinstance(observation.get("elements"), list):
            observation["elements"] = encode_elements(observation["elements"])
    if "tools" in state:
        state["tools"] = {name: {"required": schema.get("required", []),
                             "parameters": list(schema.get("properties", {}))}
                      for name, schema in state["tools"].items()}
    for value in criteria.values():
        if isinstance(value, dict) and value.get("kind") == "group":
            children = value.pop("children")
            value["tools"] = sorted({child["tool"] for child in children.values()})
            value["preview"] = dict(list(children.items())[:3])
            value["children_omitted"] = len(children) - len(value["preview"])
    for name in ("before", "current"):
        observation = state.get("observation", {}).get(name)
        if isinstance(observation, dict) and "readback_text" in observation:
            # Preserve non-actionable readback evidence, but explicitly bound it.
            text = observation["readback_text"]
            observation["readback_text"] = text[:2000]
            observation["readback_characters_omitted"] = observation.get("readback_characters_omitted", 0) + max(0, len(text)-2000)
    criteria, templates, shared = deduplicate_choices(criteria)
    if templates:
        state["action_templates"] = templates
    if shared:
        state["shared_values"] = shared
    pair = state.get("observation", {})
    if isinstance(pair.get("before"), dict) and isinstance(pair.get("current"), dict):
        pair["before"] = encode_before(pair["before"], pair["current"])
    # Byte bound is a conservative local transport policy, not a model token count.
    import json
    def size():
        return len(json.dumps({"state": state, "criteria": criteria}, ensure_ascii=True).encode())
    if size() > 22000:
        history = state.get("history", [])
        state["history_entries_omitted"] = max(0, len(history)-4)
        state["history"] = history[-4:]
        for step in state["history"]:
            if "probabilities" in step:
                distribution = step.pop("probabilities")
                step["probabilities_omitted"] = len(distribution)
        observation = state.get("observation", {})
        for key in ("last_tool_result",):
            if key in observation:
                observation[key + "_omitted"] = True
                observation.pop(key)
        for value in criteria.values():
            if isinstance(value, dict) and value.get("kind") == "group":
                preview = value.get("preview", {})
                value["preview"] = dict(list(preview.items())[:1])
                value["children_omitted"] += max(0, len(preview)-1)
    return state, criteria


def encode_elements(elements):
    """Losslessly factor repeated field names, roles and action lists."""
    import json
    if not elements:
        return elements
    columns = list(dict.fromkeys(key for element in elements for key in element))
    # Missing properties must remain distinct from explicit null values.
    if any(set(element) != set(columns) for element in elements):
        return elements
    from collections import Counter
    defaults, overrides = {}, {}
    for column in list(columns):
        if column not in columns:
            continue
        counts = Counter(json.dumps(e[column], sort_keys=True) for e in elements)
        common, count = counts.most_common(1)[0]
        if count >= len(elements)*.8:
            defaults[column] = json.loads(common)
            columns.remove(column)
            for i, element in enumerate(elements):
                if json.dumps(element[column], sort_keys=True) != common:
                    overrides.setdefault(str(i), {})[column] = element[column]
    dictionaries, indices = {}, {}
    for column in list(columns):
        if column not in columns:
            continue
        values, lookup = [], {}
        for element in elements:
            key = json.dumps(element[column], sort_keys=True)
            if key not in lookup:
                lookup[key] = len(values)
                values.append(element[column])
        encoded_cost = len(json.dumps(values)) + sum(len(str(lookup[json.dumps(e[column], sort_keys=True)])) for e in elements)
        if encoded_cost < sum(len(json.dumps(e[column])) for e in elements):
            dictionaries[column], indices[column] = values, lookup
    rows = [[indices[column][json.dumps(element[column], sort_keys=True)]
             if column in indices else element[column] for column in columns] for element in elements]
    return {"encoding": "column_table_v2", "columns": columns, "dictionaries": dictionaries, "rows": rows,
            "defaults": defaults, "overrides": overrides}


def decode_elements(table):
    import copy
    if isinstance(table, list): return copy.deepcopy(table)
    return [{**table.get("defaults", {}),
             **{column: table["dictionaries"][column][cell] if column in table["dictionaries"] else cell
                for column, cell in zip(table["columns"], row)},
             **table.get("overrides", {}).get(str(i), {})} for i, row in enumerate(table["rows"])]


def encode_before(before, current):
    """Lossless reverse delta; prefer full Before when a patch would be larger."""
    import json
    operations = []
    def diff(old, new, path):
        if type(old) is type(new) and old == new: return
        if isinstance(old, dict) and isinstance(new, dict):
            for key in old.keys() - new.keys(): operations.append({"remove": path+[key]})
            for key in new:
                if key not in old: operations.append({"set": path+[key], "value": new[key]})
                else: diff(old[key], new[key], path+[key])
        elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
            for i, (a,b) in enumerate(zip(old,new)): diff(a,b,path+[i])
        else: operations.append({"set": path, "value": new})
    diff(current, before, [])
    patch = {"encoding": "current_patch_v1", "operations": operations}
    return patch if len(json.dumps(patch)) < len(json.dumps(before)) else before


def decode_before(before, current):
    import copy
    if before.get("encoding") != "current_patch_v1": return copy.deepcopy(before)
    result = copy.deepcopy(current)
    for operation in before["operations"]:
        path = operation.get("set", operation.get("remove"))
        if not path:
            result = copy.deepcopy(operation["value"])
            continue
        target = result
        for key in path[:-1]: target = target[key]
        if "remove" in operation: del target[path[-1]]
        else: target[path[-1]] = copy.deepcopy(operation["value"])
    return result


def deduplicate_choices(criteria):
    """Lossless provider-view factoring. Execution still uses original candidates."""
    import copy
    import json
    from collections import Counter
    criteria = copy.deepcopy(criteria)
    actions = []
    def collect(value):
        if isinstance(value, dict):
            if "tool" in value and "args" in value:
                actions.append(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
    collect(criteria)
    templates = {}
    for tool in sorted({a["tool"] for a in actions}):
        rows = [a for a in actions if a.get("tool") == tool]
        if len(rows) < 2:
            continue
        template = {"tool": tool}
        for key in ("inherit",):
            if key in rows[0] and all(row.get(key) == rows[0][key] for row in rows):
                template[key] = rows[0][key]
        common_args = {k: v for k, v in rows[0]["args"].items()
                       if all(k in row["args"] and row["args"][k] == v for row in rows)}
        template["args"] = common_args
        import os
        prefix = os.path.commonprefix([row.get("description", "") for row in rows])
        if len(prefix) >= 12:
            template["description_prefix"] = prefix
        name = "t" + str(len(templates))
        templates[name] = template
        for row in rows:
            row.pop("tool")
            if "inherit" in template:
                row.pop("inherit")
            row["args"] = {k: v for k, v in row["args"].items() if k not in common_args}
            row["template"] = name
            if "description_prefix" in template:
                row["description_suffix"] = row.pop("description")[len(prefix):]
    # Factor repeated text, including menu path strings and supplied content.
    counts = Counter()
    def strings(value):
        if isinstance(value, str) and len(value) > 24:
            counts[value] += 1
        elif isinstance(value, dict):
            for child in value.values(): strings(child)
        elif isinstance(value, list):
            for child in value: strings(child)
    strings(criteria)
    strings(templates)
    shared = {"v"+str(i): value for i, (value, count) in enumerate(counts.items())
              if count > 1 and (count-1)*len(json.dumps(value)) > count*20}
    refs = {value: key for key, value in shared.items()}
    def substitute(value):
        if isinstance(value, str) and value in refs:
            return {"$ref": refs[value]}
        if isinstance(value, dict): return {k: substitute(v) for k, v in value.items()}
        if isinstance(value, list): return [substitute(v) for v in value]
        return value
    return substitute(criteria), substitute(templates), shared


def validate_request_budget(state, questions):
    """Check SDK-serialized payload, without changing executable options or task."""
    import msgspec
    from native_errors import DiagnosticError
    size = len(msgspec.json.encode({"state": state, "questions": questions}))
    if size > 40000:
        raise DiagnosticError("request_budget_exceeded", "Request requires narrower observation or choices",
                              serialized_bytes=size, limit_bytes=40000)


def compact_catalog(schemas):
    """Keep validation constraints and semantic descriptions; remove display metadata.

    Property names are data, so do not strip a property named 'title' or 'examples'.
    """
    def compact(value, names=False):
        if isinstance(value, dict):
            return {key: compact(item, key in {"properties", "$defs", "definitions", "patternProperties"})
                    for key, item in value.items()
                    if names or key not in {"title", "examples", "$schema"}}
        if isinstance(value, list):
            return [compact(item) for item in value]
        return value
    return {name: compact(schema) for name, schema in sorted(schemas.items())}


def structured_choices(candidates, groups=None):
    from driver_candidates import thaw
    groups = groups or {}
    leaves = [leaf for candidate in candidates for leaf in groups.get(candidate.id, [candidate])]
    # Hoist only exact shared addressing/delivery values, never task content.
    common = {}
    for key in ("pid", "window_id", "target_id", "tab_id", "delivery_mode"):
        values = [c.arguments[key] for c in leaves if key in c.arguments]
        if len(values) > 1 and all(value == values[0] for value in values):
            common[key] = values[0]

    def action(candidate):
        if candidate.tool is None:
            return {"control": candidate.id, "description": candidate.description}
        args = thaw(candidate.arguments)
        inherited = [key for key, value in common.items() if key in args and args[key] == value]
        return {"tool": candidate.tool,
                "description": candidate.description,
                **({"aliases": list(candidate.aliases)} if candidate.aliases else {}),
                "args": {key: value for key, value in args.items() if key not in inherited},
                **({"inherit": inherited} if inherited else {})}

    criteria = {}
    for candidate in candidates:
        if candidate.id not in groups:
            criteria[candidate.id] = action(candidate)
            continue
        children = groups[candidate.id]
        # All children are visible: no first/last-only summary or hidden sampling.
        criteria[candidate.id] = {"kind": "group", "count": len(children),
                                  "children": {child.id: action(child) for child in children}}
    return criteria, common
