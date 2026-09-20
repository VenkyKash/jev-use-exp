# Experimental decision-context comparison

No production defaults changed. decision_context.py is an experimental factual
projection; compare_context.py runs recorded states through the existing Jev
chooser and audited SDK client. It never constructs a Driver or executes choices.

## Format and scope

The projection supplies location, readable current values, last action, optional
before/after values, earlier history, inputs, budget, and observation-quality
metadata. Existing ordered choice IDs/descriptions are preserved verbatim and
serve as the control inventory; duplicated button metadata is omitted. Goal text
is unchanged. No task-specific reset rule, preferred action, answer, or success
inference is added.

This initial observation adapter handles recorded native structured values and
simple AXStaticText markdown rows. It is app-independent within those shapes,
not yet a complete adapter for every native or browser representation. Unsupported
text rows are counted; text completeness, dialog state, and focus remain unknown.
LRM/RLM marks are removed for display; original evidence is preserved in logs.
Raw toolbar metadata and non-actionable roles are intentionally not repeated.

## Method

Compared three variants: original, compact current state, compact with prior-state
readback. The latter adds information not present verbatim in the original last
action summary, so it is a separate intervention—not a pure formatting comparison.
Calculator used decision-2 in runs/calculator-handoff-04.jsonl: after Clear,
the display was 42+ and All Clear was available. Obsidian used decision-2 in
runs/obsidian-deterministic-setup-01.jsonl: only a window title and unlabeled
controls were available, with reobserve/abstain choices.

Two repetitions per variant/app, reversing variant order on the second repetition:
12 HTTP 200 responses on September 19, 2026 at 7:22 PM Pacific. The same process,
key, model label (jev-1.13.0), SDK call, goal and ordered choices were used. Model
randomness/caching is not controlled; repetitions are not independent statistical
evidence. No fresh app state was collected and no choice was dispatched.

## Results

| App / format | Selected actions (two trials) | Confidence | Input tokens per call |
|---|---|---|---:|
| Calculator / original | 9; 9 | .76; .65 | 3,363 |
| Calculator / compact current | All Clear; All Clear | .49; .49 | 1,456 |
| Calculator / compact before-after | 9; 9 | .38; .41 | 1,497 |
| Obsidian / original | reobserve; reobserve | .85; .87 | 747 |
| Obsidian / compact current | reobserve; reobserve | .58; .61 | 696 |
| Obsidian / compact before-after | reobserve; reobserve | .57; .61 | 697 |

Compact current context reduces reported Calculator input tokens by approximately
57%. It selects a plausible corrective action in this recorded state, but neither
trial passes the unchanged 0.5 confidence threshold. Before/after did not improve
the action choice. Obsidian preserves the action choice but has only two read-only
options and little content; this is a missing-information smoke test, not proof of
generalization to complex app navigation.

Therefore this is NOT a fix for Calculator and NOT sufficient evidence to make
the compact format the default. Next evaluation should include diverse states,
more meaningful second-app choices, and a separately justified confidence policy.
Do not add task-specific instructions to force All Clear or selectively rerun until
a desired response appears.

## Reproduce

```sh
uv run --frozen python python/compare_context.py --live --repeats 2 \
  --case calculator runs/calculator-handoff-04.jsonl decision-2 \
  --case obsidian runs/obsidian-deterministic-setup-01.jsonl decision-2 \
  --log runs/context-comparison-new.jsonl
```

Omit --live to emit formatted inputs without API calls. Inputs and HTTP receipts
for this run are in ignored runs/context-comparison-01.jsonl. Runtime log files
are local artifacts, not checked-in fixtures. Five new unit tests cover goal and
choice preservation, input immutability, factual deltas, unknown fields,
unsupported text, and a second native text shape. Full checks passed: 97 Python
tests, 24 TypeScript tests, and TypeScript typechecking.
