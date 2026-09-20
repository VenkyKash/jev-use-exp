# Evidence handoff and remaining desktop tests

## Contract

The shared evidence.py builder emits jev.evidence_handoff.v1. It includes task
goal, source identity, exact text, source completeness (or unknown), reason,
handoff time, and review instructions. Its status is review_required and it never
claims independent verification. The calling assistant consumes the event and
answers or reports insufficient evidence; Jev only selects navigation/actions.
Browser finish now emits this handoff rather than only evidence_collected.

Native window markdown is preserved separately from executable structured
elements, bounded at 64,000 characters, and cut before the root system menu tree.
No markdown node receives an invented clickable ref. Text participates in progress
detection and is available as readback context. Exact structured-value verification
and its incomplete-observation guard remain unchanged. Native review, abstention,
policy rejection, and progress/budget stops preserve available readback evidence.
Native text completeness is unknown, not inferred from structured completeness.

This is a caller-facing data contract, not an embedded Codex API client. It does
not autonomously wake another agent or implement an in-process multi-model loop.
The active Codex task reviews the returned/logged evidence. If more evidence is
needed, the caller must supply a new targeted observation request; automated
same-session resume is not implemented in this change.

## Live tests (September 19, 2026, about 7:05–7:08 PM Pacific)

| Task | Observed evidence | Assessment |
|---|---|---|
| 17 × 23 | Retry showed 17×17×23 and 6,647 | Failed, not 391 |
| (42 + 18) ÷ 5 | Stopped at 42+1 | Incomplete, not 12 |
| Clear then 93 − 47 | Stopped at 42+9 | Incomplete, not 46 |
| New unsaved TextEdit document | Four untitled offscreen strip windows; no document target | Blocked before typing |

The initial 17×23 attempt stopped because a reported probability total of 0.99
fell just outside abs_tol=0.01 due to floating-point representation. A focused
test and 1e-12 numerical allowance repair the inclusive boundary. Confidence
thresholds were not lowered. The retry was a fresh goal-directed run, not a retry
of an uncertain click.

The retry's first Clear removed only the current operand, leaving 17×. Jev then
entered 17×23 into that existing expression. The final selected review had
confidence 0.33 and was rejected. The wrong result is visible in the retained
decision request and was reviewed by Codex; this run preceded the addition of
automatic handoff on failure.

The next test correctly used All Clear and reached zero, then entered 42+1.
Jev selected 8 with confidence 0.29, so it was not dispatched. In the subtraction
test, Clear left 42+; after 9, the selected 3 had confidence 0.49 and was not
dispatched. Both failures emitted source-bound handoffs, allowing Codex to see
the actual partial expressions without taking over navigation.

TextEdit used --read-only for preflight, so it could not edit an existing document.
Only app launch/setup occurred; no note/document was typed, created, or saved.
The runner lacks a pre-document menu-action path. No guessed window, keyboard
shortcut, or app-specific workaround was introduced to force this test through.

## Artifacts and boundaries

Ignored logs: runs/calculator-handoff-17x23.jsonl,
runs/calculator-handoff-17x23-retry.jsonl, runs/calculator-handoff-03.jsonl,
runs/calculator-handoff-04.jsonl, and runs/textedit-handoff-preflight.jsonl.
They contain observed UI state; all mutation choices after setup came from Jev.
The session log counts and scores should not be confused with successful tasks.

These tests identify real remaining work: goal-relative reset recognition,
confidence-policy semantics, and pre-document navigation. They do not justify
lowering safeguards or adding a hard-coded Calculator/TextEdit action sequence.

Final regression checks passed: 92 Python tests, 24 TypeScript tests, and
TypeScript typechecking. These validate implementation behavior; they do not
convert the failed/incomplete live desktop cases into passes. Source text limits
and the total 64-choice ceiling remain enforced with the additional review option.
