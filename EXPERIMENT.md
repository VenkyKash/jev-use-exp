# Jev native v0

This is an independent experimental Git repository copied from `jev-use`.
The unchanged baseline is commit `667aca5`. The original browser runners and
their Python/TypeScript behavior are preserved. New native functionality is
Python-only and currently gated to macOS accessibility roles.

## What works in v0

- One persistent Driver MCP session with capability/schema checks. A unique
  titled window can be bound when the other windows are explicitly offscreen and
  untitled. Multiple named documents or visible untitled windows remain ambiguous.
- Explicit app launch is deterministic setup; Jev chooses subsequent mutations.
  No Codex API or fallback model.
- A generic builder offers supported labelled controls and supplied text inputs
  within window content. Application/system menu trees are excluded before
  context/candidate limits; scope and excluded counts are disclosed to Jev.
  It does not inspect the goal or verification checks.
- Snapshot-bound immutable actions; background delivery only.
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
0.5. SDK requests use a 10-second network timeout with retries disabled; thread
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

## Deliberate limits

The installed Driver 0.28.2 advertises no `parse_visual_regions`, so native v0
does not use pixels or introduce a perception service. The copied browser visual
adapter is preserved. Native v0 supports semantic clicks and insertion of supplied
text; not replacement, generated prose, keyboard shortcuts, scroll, drag, menus,
automatic window switching, or embedded web content. App-specific adapters have
not been added. A task may need unsupported actions and should then fail visibly.

There is no general classifier for destructive/external actions: run only scoped
test tasks in apps/windows you intend the agent to operate. Labelled enabled
controls may include cancel/reset/close. Accessibility readback is
evidence of UI state, not proof that an external service persisted a transaction.
The builder refuses over 62 executable choices; observation normalization refuses
over 200 content elements after explicit menu exclusion, over 2000 raw elements,
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
  read-only preflight; no manual launch or Codex action sequence was substituted.

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
