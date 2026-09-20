# Live application pass 01

Implementation tested: `95515aa` (unchanged during testing).
Driver: `0.28.2`. Observed provider model: `jev-1.13.0`.

**Audit correction:** the user subsequently reported no matching requests in the
Jev dashboard. This pass retained SDK-level traces, not HTTP receipts or provider
request IDs. The counts below establish local SDK invocations and local dispatches,
not dashboard-confirmed service usage. Account attribution remains unresolved;
see `api-audit-and-repairs.md` for the later instrumented probe.

## Outcome

**0 of 10 tasks verified.** Most cases were blocked at initialization or
observation before a task-specific decision could reach Jev. This is not a
10-task measure of Jev's reasoning success: its observed executable choices
were app launches, each offered alongside reobserve and abstain.

The key was available in the runner environment. There were **12 local SDK
invocations**: eight runner invocations and four provider-only diagnostic invocations.
SDK retries were disabled. Six accepted runner decisions dispatched `launch_app`
(Calculator, TextEdit, Obsidian, Notes, Reminders, System Settings). Two Chrome
runner decisions failed validation. All four separate Chrome diagnostic responses
passed validation; none were dispatched. These are local request counts, not a
token usage or billing audit.

No `click`, `type_text`, browser navigation, save, or submission was dispatched.
No test notes, reminders, or documents were created. Existing apps were left
running; there was no cleanup that closed user windows. No Codex-selected task
actions or substitute model were used.

## Cases

| # | Task | Observed outcome |
|---|---|---|
| 1 | Calculator: clear, calculate 8 × 6 | Blocked. Initial Jev-selected launch returned five windows, including four untitled strips and the titled Calculator window. Operator-attached run subsequently failed observation before a provider request. |
| 2 | Calculator: calculate 17 × 23 | Blocked before a provider request on the same observed target. No digits entered. |
| 3 | Calculator: calculate (42 + 18) ÷ 5 | Blocked before a provider request. No arithmetic attempted. |
| 4 | Calculator: clear existing result, calculate 93 − 47 | Blocked before a provider request. No result was cleared or entered. |
| 5 | TextEdit: supplied sentence in a new unsaved document | Jev selected launch; runner stopped for window selection. Later inventory contained four untitled windows and no uniquely identified document. |
| 6 | Obsidian: startup and report visible state | Partial startup only. Jev selected launch. Driver later exposed a window titled `07 - ZML Overview - Obsidian Vault - Obsidian 1.12.7`; 213 structured elements exceeded v0's 200-element limit. No note edited. |
| 7 | Notes: labelled temporary note | Jev selected launch; stopped for window selection. Read-only inspection returned 155 elements and candidate construction exceeded 62 executable options. No note created. |
| 8 | Reminders: undated reminder in a dedicated list | Jev selected launch; stopped for window selection. Inspection returned 130 elements and exceeded 62 executable options. No list or reminder created. |
| 9 | System Settings: inspect Appearance | Jev selected launch; stopped for window selection. Later inspected window was titled Accessibility, with no usable normalized observation. Did not navigate to Appearance or change a setting. |
| 10 | Chrome: Wikipedia research on first Gutenberg Bible publication | Two runner decisions failed validation before dispatch. A separate 24-decision-budget probe and three further provider-only probes all returned valid launch choices. No Wikipedia page was visited and no research answer is claimed. |

Obsidian's raw diagnostic contained its window title, window buttons, and menu
items. It had no editable fields or nonempty values in the returned indexed
elements. The payload said `elements_complete: false`. This is Driver-observed
metadata, not proof that Jev read or summarized the note. The initial launch
request contained the task and launch options, not vault contents.

## Specific implementation gaps exposed

1. **Window binding is too strict.** `run_loop` requires exactly one returned
   window. macOS commonly returns auxiliary windows alongside the actual app
   window. This blocks the loop even when one target is clearly titled.
2. **Candidate construction includes the complete menu hierarchy.** The initial
   Calculator inspection contained 173 indexed elements, of which 158 had
   AXPress or a supported button role. System menu entries and nested menu items
   inflate the set past the 62-option limit. Notes and Reminders reproduced the
   overflow through the actual builder. Raising the cap alone would preserve
   the irrelevant choices and context cost.
3. **The result evidence is incomplete.** That Calculator observation had zero
   non-null element values; there was no stable display value for the existing
   exact-value verifier. A synthetic `Display` label is not a real-app contract.
4. **Observation failures need better diagnostics and a supported fallback.**
   Subsequent reads sometimes returned no usable snapshot/elements or a Driver
   failure. MCP context managers wrapped errors in `ExceptionGroup`, while the
   CLI recorded only the top-level type. No foreground/pixel fallback was used.
5. **Provider rejection evidence is discarded.** The Chrome runner logs retain
   `ValueError` but not the rejected response or validation reason. Separate
   valid probes do not establish why the two original calls failed. The reason
   remains unresolved; do not describe this as a Jev service outage.
6. **Read-only reports and browser research are not implemented task types.**
   v0 selects action IDs and verifies exact native values. It has no reporting
   completion mode, and its native builder excludes embedded web content.

Potential next changes, not made in this pass: deterministic window metadata
resolution with ambiguity preserved; candidates scoped to the active UI level
with explicit menu navigation; read-only evidence/completion support; and
sanitized logging of rejected provider responses and underlying Driver errors.
These should be tested separately against this recorded baseline, not folded
into a claim that the current version passed.

## Method and limitations

- The first Calculator launch used the unmodified native CLI with a one-decision
  initialization budget. Read-only inspection selected the explicitly titled
  Calculator window. The four task attempts used its observed pid/window pair;
  no action sequence was supplied. They failed before decisions, independently
  of the one-decision cap.
- Other apps initially used one-decision startup probes because the existing
  completion checks had not yet been grounded in real UI state. They stopped
  for window selection or provider validation rather than consuming that budget.
  No full task continuation was attempted after these blocks. Placeholder
  checks in the probe manifests are not validated app selectors or success proof.
- Chrome also received a normal 24-decision-budget runner attempt. It failed
  validation before dispatch. Four later/separate provider-only requests must
  not be counted as task progress.
- Diagnostics were read-only, did not front apps, and sometimes could not resolve
  hidden/untitled targets. They did not alter runner policies or prune candidates.
- The implementation files, dependencies, and lockfile remain identical to
  `95515aa`. Only this report is tracked; runtime artifacts remain ignored.

## Local evidence

All paths below are relative to the experimental repository. Raw traces and
inspections may contain personal app/window/menu information; keep them local.

- `runs/live-suite-01/calculator-preflight.jsonl`
- `runs/live-suite-01/calculator-inspection.jsonl`
- `runs/live-suite-01/suite-summary.json`
- `runs/live-suite-01/01-calculator-startup.jsonl` through the numbered app logs
- `runs/live-suite-01/06-obsidian-raw-inspection.json`
- `runs/live-suite-01/07-notes-raw-inspection.json`
- `runs/live-suite-01/08-reminders-raw-inspection.json`
- `runs/live-suite-01/read-only-diagnoses.json`
- `runs/live-suite-01/10-chrome-normal-budget.jsonl`
- `runs/live-suite-01/chrome-provider-probe.json`
- `runs/live-suite-01/chrome-validation-probes.json`

`run_suite.py`, `diagnose_suite.py`, and `probe_chrome_validation.py` in that
directory are evaluation-only harnesses. They import the frozen implementation;
none provide a planner, alternate candidate builder, or substitute chooser.
