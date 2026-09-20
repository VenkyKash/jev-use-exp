# Task-driven browser research

Implemented in the existing core.py, jev_adapter.py, and run.py. The original
fixture mode and default adapter goal remain available. No Driver changes,
site-specific Python, selectors, or scripted research sequence were added.
The task JSON provides the goal, starting URL, public search text, navigation
terms, semantic observation queries, and permitted hosts.

## Behavior

Browser preparation and initial navigation reuse the original deterministic
setup. Jev chooses search-field typing, search submission, exact-name matching
links, semantic queries, scoped region reads, continuation, reobserve, abstain,
or finish. Candidate arguments remain immutable and use current snapshot refs.
Scoped-read results are consumed before requesting another snapshot. Driver
enforces reference freshness on dispatch. Uncertain actions are not retried.

Every observed source snapshot is retained in the JSONL log. A model-selected
finish produces evidence_collected, explicitly not independently verified.
Codex summarizes the retained evidence after the runner stops, not during its
navigation loop. This version has no autonomous prose-generation stage.

The original browser adapter's confidence behavior is preserved: scores are
logged, not subjected to the native runner's additional 0.5 threshold.
HTTP logging reuses the existing audited SDK client; no fallback provider.

## Live evidence

First run: Jev searched, opened the article, navigated to its death section,
queried death, then followed an external bibliographic reference. A subsequent
host check stopped the run. That exposed two gaps: keyword reads omit surrounding
text, and substring link matching included bibliography entries. Added scoped
region reads, exact-name link matching, and a clean host-boundary outcome.

Second run (September 19, 2026, 6:53 PM Pacific): five successful HTTP 200 Jev
requests selected search-field typing, Search, a death query, the full Death and
aftermath region, then finish. No research navigation was selected by Codex.
The final scoped snapshot p27 reported complete=true within its subtree scope.
Its URL was https://en.wikipedia.org/wiki/Genghis_Khan . The Driver's page title
remained about:blank, so the report relies on the URL and section text, not that
stale title. Traces: runs/wikipedia-genghis-01.jsonl and -02.jsonl (ignored).

The captured passage says the exact cause of death is uncertain: Genghis fell
from his horse during winter 1226–1227 and subsequently grew ill; he died on
18 or 25 August 1227. It distinguishes illness accounts from competing stories
and legends. This supports an uncertainty-preserving answer, not a claim that
he was definitively killed.

## Limits

This is a constrained public-reference-site mode, not a security sandbox for
arbitrary websites. It excludes arbitrary buttons, password fields, uploads,
and unrelated links, and uses a Driver-owned isolated browser profile. Accessible
names alone cannot prove that an action is read-only or where a link leads.
The host check occurs AFTER navigation; the first run demonstrates that limitation.
Do not use this mode for authenticated/admin workflows or describe its host list
as preventing all external requests. New sites may need different declarative
terms; unsupported controls must not acquire guessed actions.

No system-browser default was changed. Browser selection is delegated to the
original browser_prepare contract, which does not expose a browser-name argument.
This run does not certify that the prepared browser was specifically Chrome.

## Run

```sh
uv run --frozen python python/run.py --provider live \
  --task tasks/wikipedia-genghis-khan.json --max-steps 16 \
  --log runs/wikipedia-research-new.jsonl
```

Logs must be new files and may contain page text. Research dry-run does not open
a browser or call Jev. The 180-second deadline and 50-step CLI ceiling bound runs;
three repeated observations are permitted before the no-progress stop.

## Regression checks

87 Python tests, 24 TypeScript tests, and TypeScript typechecking pass. Coverage
includes the existing demo, generic action restrictions, stale/duplicate refs,
immutable arguments, scoped-read reuse, host-boundary stopping, no-progress,
uncertain-action handling, task goal propagation, and research dry-run safety.
The preserved Python browser demo also passed verify_setup.py with its mock
provider and independent fixture-state verification. This exercised real Cua
browser typing/clicking without Jev calls; evidence is in ignored
runs/browser-baseline-regression-01. The final subsequent executable changes
only restricted the new CLI step limit to task mode and protected pre-existing
logs in the task-mode exception handler; original demo execution was unchanged.
