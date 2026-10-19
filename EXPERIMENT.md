# Jev native v0

This is an independent experimental Git repository copied from `jev-use`.
The unchanged baseline is commit `667aca5`. The original browser demo mode and
its Python/TypeScript behavior are preserved. The Python browser modules now also
support [task-driven research](reports/browser-research.md). New native functionality is
Python-only and currently gated to macOS accessibility roles.

## What works in v0

- One persistent Driver MCP session with capability/schema checks. A unique
  titled window can be bound when the other windows are explicitly offscreen and
  untitled. Multiple named documents or visible untitled windows remain ambiguous.
- Explicit app launch is deterministic setup; Jev chooses subsequent mutations.
  No external agent API or fallback model.
- A generic builder offers supported controls (including web and unlabelled
  controls), keyboard input, replacement, scrolling and supplied text. Application
  menu paths are preserved as invoke_menu choices while menu trees are kept out
  of the window-content context; scope and excluded counts are disclosed to Jev.
  It does not inspect the goal or verification checks.
- Snapshot-bound immutable actions; background delivery by default.
- Compact recent history, shuffled option order, confidence/distribution checks.
- Exact unique native element value checks, outside the provider request. An
  explicitly incomplete observation cannot establish completion.
- Step/time/no-progress limits. An uncertain action is observed, never retried
  automatically. A refused action ends the run rather than silently escalating.
- JSONL traces contain exact model inputs, provider answers even when rejected,
  executable alternatives, dispatch, and post-action observations. HTTP events
  retain UTC time, endpoint, status, provider request ID, and local correlation
  ID. Answer events include reported token usage. No Authorization headers or
  raw HTTP bodies are logged. Treat traces as potentially sensitive.

`native_core.py` contains models, `native_driver.py` the MCP adapter,
`native_candidates.py` the generic builder, `native_jev.py` the provider boundary,
and `native_run.py` the loop/CLI. Small new modules preserve the existing fixture
instead of mixing its assumptions into the native runner.

## Run and inspect

```sh
uv sync --frozen
uv run --frozen python python/native_run.py --doctor
uv run --frozen python python/native_run.py --inspect --pid PID --window-id WINDOW_ID
uv run --frozen python python/native_run.py --task tasks/calculator.example.json
```

Live runs require `TYPESAFE_API_KEY` in the environment. Do not place it in the
task file or command arguments. The sample uses the simulator's display selector;
**inspect the real Calculator window and update the check's role/label to the
observed stable result element before expecting a verified desktop run**. No live
Calculator selector or Jev success is claimed. A readback value must remain
separate from the label for v0's exact check to work.

Supply both `--pid` and `--window-id` to attach to an existing window. Otherwise
the runner launches the explicitly named app without a Jev decision. If launch returns
ambiguous windows, the runner reports `needs_window_selection` with their IDs;
restart with the intended pair. It does not guess the largest window.

`--dry-run` reports planned setup without launching or calling Jev when no target
is supplied. With an existing target it reads that window and makes one Jev
decision without a mutation. `--read-only` allows explicit app setup but offers
only reobserve/abstain afterward; it does not yet generate a free-text Jev report.
`--log` requires a new file
in an existing directory and never overwrites a previous trace. `--seed` controls
candidate-order permutations, not model randomness. Default limits are 24
decisions, 180 seconds, three consecutive unchanged observations, and confidence
0.1 (user-requested trial; not a calibrated safety guarantee). SDK requests use a 10-second network timeout with retries disabled; thread
cleanup may outlast the run deadline. A timeout is `timeout_unknown`, never proof
that the last action was not delivered.

## Evaluate Jev's contribution

```sh
mkdir -p runs
uv run --frozen python python/evaluate_native.py --provider first --log runs/first.jsonl
uv run --frozen python python/evaluate_native.py --provider live --log runs/jev.jsonl
```

Both commands run the same general loop against simulated Calculator and form
controls, varying task inputs, element order, and candidate order. Expected
answers remain in the verifier. The first-option baseline is available only in
this simulated evaluator; it cannot drive the native CLI. Evaluation compares
actual fixture backing state with the expected result. A scripted chooser exists
only in unit tests to prove mechanics, not reasoning quality.

Compare success, action count, decision latency, and traces. The examples are a
small regression suite, not a capability benchmark; future held-out tasks should
be chosen before evaluating Jev. Simulated success does not prove desktop success.

## Driver action coverage

`python/driver_candidates.py` compiles schema-validated choices. `native_run.py
--doctor` lists every advertised tool and its input schema (56 on the inspected
installation). Automatic UI choices cover press/secondary clicks, value
replacement/insertion, keyboard/hotkeys, scroll, menu paths and browser observation.
Browser candidates use advertised control actions, not research-specific labels.
Sets larger than 64 are presented through Jev-selected groups; no executable
options are dropped. The full state remains in traces; large provider contexts
are scoped with explicit omitted counts.

Both task formats accept optional `tool_options`: unordered, explicitly authorized
choices, **not an execution sequence**. Every advertised tool can be compiled this
way, including drag, pointer/zoom, clipboard, files, dialogs, window management,
recording, configuration and lifecycle tools. Arguments must match the discovered
schema. There is no catch-all permission to execute maintenance, security changes,
uploads or destructive operations during ordinary navigation.

Each option has `tool` and `arguments`. Supported bindings are `$pid`, `$window_id`,
`$snapshot_id` for native tasks; `$target_id`, `$tab_id`, `$snapshot_id` for browser
tasks; and `$result.<field>` for fields in the preceding tool result. Native
`$element_token`/`$element_index` and browser `$ref` expand into separate choices
for observed enabled targets. Missing result-dependent values wait for observation.
Open-ended values such as file paths, coordinates, settings and scripts must come
from authorized task inputs, not invented schema defaults. The runner owns session
identity. A schema-valid choice is not proof a platform supports its native effect.

Native `checks: []` requests evidence review rather than inventing a result selector.
Browser tasks require only `goal`, `start_url`, and `allowed_hosts`; `inputs` carries
content without a mandatory search query. Existing research fields remain compatible.
Use browser `--pid PID --window-id ID` to attach without launching an isolated
profile; `--tab-url URL` resolves ambiguous tabs. Driver must permit the connection;
the runner does not bypass preparation/permission requirements.

## Remaining limits

The inspected Driver advertises no `parse_visual_regions`. The copied browser
visual adapter is preserved; this change does not add an image-perception service.
Pixel/drag arguments therefore need grounded, explicitly supplied coordinates.
Foreground delivery and other escalations are not automatically substituted.

There is no general classifier for destructive/external actions: run only scoped
test tasks in apps/windows you intend the agent to operate. Labelled enabled
controls may include cancel/reset/close. Accessibility readback is
evidence of UI state, not proof that an external service persisted a transaction.
Observation normalization still refuses
over 1000 content elements after explicit menu exclusion, over 2000 raw elements,
or explicit truncation rather than silently choosing a goal-dependent subset.

The provider must return probabilities for all candidates summing to one within
0.01. Failure does not trigger a substitute chooser. Rejected answers and policy
codes are retained for diagnosis; see the audit report for the unresolved
dashboard/account attribution issue.

## Tests and rollback

```sh
uv run --frozen python -m unittest discover -s python/tests
npm ci --cache .npm-cache
npm test
npm run typecheck
git log --oneline
```

For a local comparison without disturbing your current branch, create a worktree
at a prior commit under `/Users/Venky/Codex/`. Revert individual experiment commits
with `git revert <commit>` after reviewing dependent commits. Nothing in the
parent repository needs to be reverted. The parent sees this folder as untracked;
do not add it there unless you deliberately want to manage a nested repository.

The copied workflow test still reads the parent monorepo's CI file. That test is
not portable outside this checkout; native v0's tests do not need the parent.

## Validation recorded for v0

- Baseline copy: 36 Python tests; 24 TypeScript tests and typechecking.
- Final implementation: 56 Python tests (including 20 native tests), 24
  preserved TypeScript tests, typechecking, and `git diff --check` pass.
- Installed Driver `0.28.2`: MCP initialization and native tool schema discovery
  succeed. `parse_visual_regions` is absent.
- Preserved browser integration: `verify_setup.py --output-dir proof-v0-baseline`
  completed with independent HTTP readback matching the submitted token. This
  uses the deterministic mock provider and proves the existing browser path only.
- Native mechanics: simulated multiplication `17 × 23 = 391` and two-field
  submission succeed with scripted test choices. Dry-run, stale choices,
  uncertainty, full distribution validation, cyclic states, and no-progress
  bounds are covered. These are not live Jev results.
- The shuffled first-option baseline passed 0 of 10 simulated evaluation cases;
  it stopped through cycle detection or the decision budget.
- No `TYPESAFE_API_KEY` was available. Live Jev evaluation and native desktop
  mutation were not run. The existing Calculator app was not running during the
  read-only preflight; no manual launch or assistant action sequence was substituted.

The initial dependency diff added an explicit declaration for already-locked
`jsonschema`; HTTP auditing subsequently declared already-locked `httpx2`.
Existing resolved dependency versions are unchanged.

## HTTP audit and subsequent repairs

See [api-audit-and-repairs.md](reports/api-audit-and-repairs.md). To make a single
identifiable diagnostic request without any desktop action:

```sh
uv run --frozen python python/probe_jev.py --log runs/new-probe.jsonl
```

The log includes an opaque probe marker and a truncated SHA-256 fingerprint of
the configured key for local comparison; never share the key itself. HTTP receipts
are client-side evidence, not confirmation of which dashboard workspace billed
the request. A missing request ID remains null rather than being invented.
# Test-drive gap capture

An experimental repository-local [Jev skill](.agents/skills/jev-computer-use/SKILL.md)
now documents test drives and gap capture. It is not installed globally; when
working outside this nested repository, read that file explicitly.
This packaging is for iterative testing, not certification that all apps pass.

Native runs emit `candidate_coverage` diagnostic events without changing candidate
selection or confidence policy. They identify omitted controls by index, role,
advertised actions and parent, with reasons such as unsupported action, missing
label, schema rejection or read-only policy. Labels and values remain in the
existing observation trace, not duplicated in the coverage event. Coverage is
limited to normalized elements reaching the builder; early observation/setup
failures and candidate-limit exceptions still require their existing error traces.

Use `uv run --frozen python python/gap_log.py summary runs/<run>.jsonl` for
diagnostic counts. Use `python/gap_log.py add --help` for manual reports, including
browser gaps. Reports default to suspected and stay in ignored `runs/gaps/`.
Existing/browser traces without coverage are explicitly marked unavailable,
not treated as having no gaps. Reports are immutable separate JSON files;
follow-ups reference the original ID. Resolution requires retest evidence, not
just passing unit tests. No automatic remediation or background monitoring runs.
