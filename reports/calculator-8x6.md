# Calculator 8 × 6: live execution and readback gap

The live runner made six successful HTTP 200 Jev requests starting September 19,
2026 at 6:20:07 PM Pacific. Jev selected every mutation: launch Calculator, All
Clear, 8, Multiply, 6, Equals. Codex supplied no runtime action sequence. The
record is in ignored runs/calculator-8x6-01.jsonl.

The runner exited with repeated_state, not verified. Its structured accessibility
observations omitted the display. A subsequent read-only get_window_state call
for the same PID/window returned these non-actionable tree_markdown rows:

```text
    - AXStaticText = "‎8‎×‎6"
    - AXStaticText = "‎48"
```

This is independent diagnostic readback of the successful calculation, not an
automated verification by the runner. No extra click, app launch, foreground
switch, screenshot inference, or API call was used for that readback.

## Concrete cause

The raw response has elements_complete=false. Its 151 structured elements include
26 window-content elements and 125 menu elements, but neither static-text display
row. The native adapter consumes only structured elements and drops tree_markdown.
Consequently both progress detection and exact-value verification miss display
changes. The Driver did supply the result, but in a representation we do not use.

The initial task copied the example's unverified label "Display"; the actual text
rows have no label. The task manifest now records the observed empty label and
U+200E-prefixed value. This does not make it supported: that row is still absent
from the structured list and the incomplete-observation guard still applies.

## Boundary for the fix

Do not remove the incomplete-observation guard, fabricate structured rows or
element tokens, or infer completion from the action sequence. A narrowly scoped
next change is a separate read-only text-evidence channel from tree_markdown, with
explicit source-aware verification and coverage for incomplete/truncated trees,
duplicate values, Unicode formatting marks, and separation from clickable targets.
That is additional verification behavior, not merely a selector correction.

No production implementation was changed in this run. The app calculation worked;
fully automated readback remains blocked pending that evidence-channel change.
