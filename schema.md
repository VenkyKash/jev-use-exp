# Jev Payload & API Schema Specification

This document details the exact JSON schema and data structures sent to **Jev** via the TypeSafe API (`client.system_one(...)`).

---

## 1. Top-Level RPC Request Format

Jev is invoked via `TypeSafeClient.system_one(...)`. The HTTP request body sent to the API follows this structure:

```json
{
  "state": { ... },
  "questions": {
    "<question_key>": {
      "type": "choice",
      "instructions": { ... },
      "criteria": { ... }
    }
  }
}
```

- **`question_key`**:
  - `"driver_action"` (when history exists or in native runner tasks)
  - `"candidate"` (when called without history in baseline bounded adapter)
- **Request payload size bound**: Strict guard at **40,000 bytes** (`len(msgspec.json.encode({"state": state, "questions": questions})) <= 40000`).

---

## 2. `questions.<key>` (Choice Specification)

Each question in `questions` is an instance of `typesafe_sdk.Choice`:

```json
{
  "type": "choice",
  "instructions": {
    "question": "Which supplied choice should be selected next to advance the goal?",
    "consider": ["observation.current", "history"],
    "rules": [
      "A group expands choices without executing an action.",
      "When hierarchy inspection is active, the visible controls are only one branch/page, not the whole app. If they do not fit the goal, inspect more options: use supplied tree-next/tree-previous for sibling pages, tree-expand-* to go deeper, and tree-parent/tree-root to leave a branch and explore another. These are read-only inspection choices, not app navigation. Do not infer that an unseen control is absent or repeatedly click an unrelated visible control instead of exploring.",
      "Select an executable candidate or a supplied control; the tool catalog is capability information, not authorization.",
      "A changed observation or successful tool call does not establish task completion.",
      "Respect task.required_sequence and input purposes. Entered text does not prove navigation. Handoff requires observed evidence for task.success and task.relevance.",
      "Candidate inherit lists name exact argument values in state.bindings; remaining arguments are in args.",
      "Resolve $ref from state.shared_values. Resolve template from state.action_templates; merge args and overlay candidate fields. Description is description_prefix plus description_suffix. References describe choices, not extra actions.",
      "Element rows use columns; dictionary cells index dictionaries[column]. defaults apply to every row, overridden by overrides[row_index]. No controls are dropped."
    ]
  },
  "criteria": {
    "<candidate_id>": "<candidate_description_or_structured_action>"
  }
}
```

*(Note: When `observation.before` is present, `"observation.before"` is included in `instructions.consider`, and a rule describing `current_patch_v1` delta decoding is appended).*

### `criteria` Formats

Depending on runner mode, criteria map choice IDs to descriptions or structured action objects:

#### A. Flat String Form (Standard Native Runner)
```json
{
  "click_12": "Click 'Search'",
  "type_search": "Type 'Tokyo' into Address and search bar",
  "reobserve": "Reobserve window state"
}
```

#### B. Structured Tool Candidates
```json
{
  "click_12": {
    "tool": "click",
    "description": "Click 'Search'",
    "args": { "target_id": "12" },
    "aliases": ["search_button"],
    "inherit": ["pid", "window_id"]
  }
}
```

#### C. Group Choice (Hierarchical / Multi-Action Branching)
```json
{
  "group_menu": {
    "kind": "group",
    "count": 14,
    "tools": ["click"],
    "preview": {
      "item_1": { "tool": "click", "args": { "target_id": "5" }, "description": "Menu item 1" },
      "item_2": { "tool": "click", "args": { "target_id": "6" }, "description": "Menu item 2" },
      "item_3": { "tool": "click", "args": { "target_id": "7" }, "description": "Menu item 3" }
    },
    "children_omitted": 11
  }
}
```

#### D. Factored / Deduplicated Action Templates
When identical tools/arguments repeat across choices, they are factored out into `state.action_templates`:
```json
{
  "click_12": {
    "template": "t0",
    "args": { "target_id": "12" },
    "description_suffix": "'Search'"
  }
}
```
And shared large strings are replaced with `{"$ref": "v0"}` referencing `state.shared_values`.

---

## 3. `state` Object Schema

The `state` object provides Jev with the full task environment, UI observations, and execution history.

```json
{
  "goal": "Search for weather in Tokyo",
  "application": {
    "name": "Google Chrome",
    "name_source": "observed",
    "type": "web_browser",
    "type_source": "inferred_from_app_name",
    "window_title": "New Tab"
  },
  "task": {
    "goal": "Search for weather in Tokyo",
    "app": "Google Chrome",
    "inputs": ["https://weather.com", "Tokyo"],
    "checks": [],
    "brief": {
      "required_sequence": ["navigate", "type_query", "press_enter"],
      "success": ["forecast displayed"],
      "relevance": ["Tokyo weather summary"],
      "input_purposes": ["weather service URL", "search query"]
    }
  },
  "interface": {
    "kind": "computer_use",
    "execution": "Select one discrete action, execute, then observe. Group selection only expands choices."
  },
  "tools": {
    "<tool_name>": {
      "required": ["target_id"],
      "parameters": ["target_id", "button", "click_count"]
    }
  },
  "bindings": {
    "pid": 12345,
    "window_id": 67890
  },
  "shared_values": {
    "v0": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  },
  "action_templates": {
    "t0": {
      "tool": "click",
      "inherit": ["pid", "window_id"],
      "args": { "button": "left" },
      "description_prefix": "Click button: "
    }
  },
  "observation": {
    "current": { ... },
    "before": { ... },
    "inputs": ["https://weather.com", "Tokyo"],
    "remaining_decisions": 10
  },
  "history": [ ... ],
  "history_entries_omitted": 0
}
```

---

## 4. `state.observation.current` Schema

```json
{
  "snapshot_id": "snap_1042",
  "pid": 12345,
  "window_id": 67890,
  "application": {
    "name": "Google Chrome",
    "name_source": "observed",
    "type": "web_browser",
    "type_source": "inferred_from_app_name",
    "window_title": "New Tab"
  },
  "background_input": null,
  "scope": "window_content; application and system menu trees excluded",
  "excluded_menu_elements": 0,
  "complete": true,
  "inspection": null,
  "availability": null,
  "geometry": null,
  "click_targets": {
    "click_btn": {
      "target": 0,
      "area": 0,
      "method": "coordinates"
    }
  },
  "root": null,
  "element_count": 142,
  "context_elements_omitted": 0,
  "readback_text": "...",
  "readback_characters_omitted": 0,
  "context_scope": "All normalized window-content elements; no first-N or candidate-target filtering. Readback text may be bounded separately.",
  "elements": {
    "encoding": "column_table_v2",
    "columns": ["id", "role", "label", "value", "actions", "enabled", "parent", "frame"],
    "defaults": {
      "enabled": true,
      "value": null,
      "parent": null
    },
    "dictionaries": {
      "role": ["AXButton", "AXTextField", "AXStaticText", "AXGroup"],
      "actions": [["AXPress"], ["AXShowMenu"]]
    },
    "rows": [
      [1, 0, "Submit", null, 0, true, null, [100.0, 200.0, 80.0, 32.0]],
      [2, 1, "Address and search", "https://google.com", 0, true, null, [10.0, 40.0, 400.0, 28.0]]
    ],
    "overrides": {
      "0": { "enabled": false }
    }
  }
}
```

### Observation Elements Compression (`column_table_v2`)
UI elements are represented in `column_table_v2` encoding to fit within the transport budget:
- **`columns`**: List of remaining column names.
- **`defaults`**: Key-value pairs representing values shared across $\ge 80\%$ of elements (removed from column lists).
- **`overrides`**: Row index $\to$ dictionary of overrides for default values.
- **`dictionaries`**: Categorical lookup tables for repeated values (e.g. `role`, `actions`).
- **`rows`**: 2D matrix of values or dictionary index pointers.

---

## 5. `state.observation.before` Schema

When `before` observation is sent, it is either a full observation dict or compressed as a lossless reverse delta patch against `current` (`current_patch_v1`):

```json
{
  "encoding": "current_patch_v1",
  "operations": [
    {
      "set": ["elements", "rows", 0, 3],
      "value": "Old input value"
    },
    {
      "remove": ["click_targets", "new_popup"]
    }
  ]
}
```

---

## 6. `state.history` Item Schema

```json
[
  {
    "action": "click_search_input",
    "tool": "click",
    "arguments": { "target_id": "2" },
    "confidence": 0.95,
    "effect": "changed",
    "reobserved": true,
    "duration_ms": 124.5,
    "error": null,
    "probabilities": {
      "click_search_input": 0.95,
      "click_cancel": 0.05
    }
  }
]
```

When payload size exceeds limits, `probabilities` are trimmed to `probabilities_omitted: <count>`, and history is truncated to the most recent 4 steps.

---

## 7. Expected Jev Response Schema

Jev responds to `system_one` with a `SystemOneResponse`:

```json
{
  "model": "jev-system-one-v1",
  "usage": {
    "input_tokens": 1420,
    "output_tokens": 85
  },
  "answers": {
    "driver_action": {
      "choice": "click_search_input",
      "confidence": 0.95,
      "probabilities": {
        "click_search_input": 0.95,
        "click_cancel": 0.05
      }
    }
  }
}
```

### Validation Invariants (`validate_decision`)
1. **Selected ID**: `choice` must exist in `criteria`.
2. **Confidence**: Finite float, $0.1 \le \text{confidence} \le 1.0$ (or configured minimum threshold).
3. **Probability keys**: `set(probabilities.keys()) == set(criteria.keys())`.
4. **Probability bounds**: Each probability must satisfy $0.0 \le p \le 1.0$.
5. **Probability sum**: $\sum p_i \approx 1.0$ with a strict inclusive 1% tolerance ($0.99 \le \sum p \le 1.01$).
