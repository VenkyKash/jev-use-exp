# Remaining queued tests

Runner implementation tested: 640562d; native cutoff 0.4, existing production
context unchanged. No implementation changes or substitute action planner were
introduced during these tests. Native probes use --read-only --max-steps 1 to
inspect prerequisites without editing existing content or changing settings.
These are blocked preflights, not completed task attempts or measurements of
full Jev navigation quality.

| Queued task | Result |
|---|---|
| Notes: new temporary note | Blocked: no snapshot ID and zero structured elements, reproduced in a separate read-only query. No note created. |
| Reminders: dedicated list and undated item | Blocked at onboarding/upgrade screen with Update Later / Update Now and a device-compatibility warning. No upgrade, list, or reminder created. |
| System Settings: inspect Appearance | Blocked: current panel is Accessibility. Appearance appears as AXStaticText with AXShowMenu, which the candidate builder does not turn into a navigation action. No setting changed. |
| Wikipedia: first Gutenberg Bible publication | Research/evidence review passed after one caller-requested targeted follow-up. First finished copies: 1454 or 1455. |

Notes preflight failed before any Jev request. Reminders and Settings read-only
preflights each called Jev once and rejected its choice below 0.4; those probes
offered only observation/review choices, not navigation, so the low scores should
not be described as failed attempts to create content or open Appearance.

Reminders explicitly warns that some devices cannot show upgraded reminders.
No automatic upgrade was authorized. Update Later was visible but not executed;
the full creation workflow remains untested behind that screen, not proven
impossible. Settings diagnostics confirmed that its normal candidate set includes
permission toggles/Add/Back/Search but no Appearance action. The runner was not
allowed to substitute permission changes for the requested navigation.

## Browser handoff review

The first run used a declarative task file containing public search/navigation
terms and no expected date. Jev typed Gutenberg Bible, submitted Search, and
selected finish. Its incomplete viewport handoff contained the lead, including
a broad printing period and a date marked on a surviving copy, but not the
printing-history passage needed to distinguish those dates.

Codex reviewed that handoff and requested the missing evidence in a follow-up
task, starting from the already observed article URL. This used a new Driver
session, not automatic same-session resume. Jev chose five further actions:
two link clicks, a printing-history query, a scoped section read, and finish.
No browser research action was chosen directly by Codex. Eight total browser
Jev decisions returned HTTP 200 across both runs.

The final handoff (p37, subtree scope, source_complete=true) contains Wikipedia's
statement that preparation probably began soon after 1450 and the first finished
copies were available in 1454 or 1455. Codex can now answer the date question
without confusing that with a surviving copy's marked date.
Source: https://en.wikipedia.org/wiki/Gutenberg_Bible#Printing_history .

This passes the research/answer evidence check, not every possible browser
requirement: the existing browser_prepare contract chooses the isolated Chromium
browser, and Chrome-specific identity was not independently certified. Browser
adapter confidence behavior is unchanged (unlike native, it has no 0.4 gate).

## Packaging decision and verification

The user made skill creation conditional on the remaining tests passing. Three
native tasks are blocked, so no SKILL.md was created or installed. A skill would
not supply the missing observation/navigation capabilities. Existing data and
settings were preserved; no test note, list, reminder, or document was created.

100 Python tests, 24 TypeScript tests, and TypeScript typechecking passed after
these runs. These checks do not override the blocked live results.

Local ignored artifacts: runs/remaining-notes-preflight.jsonl,
runs/remaining-reminders-preflight.jsonl, runs/remaining-settings-preflight.jsonl,
runs/remaining-gutenberg-01.jsonl, runs/remaining-gutenberg-followup.jsonl,
and runs/gutenberg-followup-task.json. They may contain user UI information.
