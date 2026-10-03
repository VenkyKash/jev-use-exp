# Experimental Jev runner

Keep changes inside this repository. Preserve the copied browser demo mode as the
regression baseline while extending its shared Python modules. The native v0 is Python-only; do not claim native TypeScript
or cross-platform parity until tested. Do not modify Cua Driver to fit this agent.

Launching the explicitly named task app and binding its unambiguous window are
deterministic setup. Every subsequent task mutation must be selected by Jev.
No Codex runtime, hidden planner, hard-coded app sequence, or model fallback.
Mock providers prove mechanics only. Keep expected verification values out of
provider requests; never treat a tool success response as task completion.

Use uv. Run focused tests before each implementation commit and the complete
Python suite plus preserved TypeScript checks before final handoff. Keep runtime
logs untracked; they may contain user-supplied text and UI content.

## Notes to self.

- Hierarchy prompts must explain sibling paging, deeper expansion and returning
  to parent/root; first-page controls are not the entire app. The Weather run
  exposed Search through Cua but hid it on a later local page. Do not attribute
  that discovery failure to missing Cua controls.

- Normalize executable candidates once at the shared choice-menu boundary before
  grouping: exact tool/complete arguments and capture guards identify duplicates.
  Keep one executable ID with descriptive aliases, not competing probability slots.
  Never merge semantic/coordinate routes, distinct delivery modes or nearby points.
  This is separate from lossless payload text/template compression.

- Shared geometric targeting uses observed AX screen bounds converted through
  validated screenshot dimensions/window bounds, never raw AX x/y as pixels.
  Normal observations capture geometry; Jev chooses target plus observed self/
  child area in one compound choice. Missing geometry retains semantic choices.
  Each choice dispatches one click, never an implicit fallback retry. No random
  offsets, expanded hitboxes or automatic retries. Recheck window visibility
  and exact bounds before dispatch; log method, delivery, route and outcome.
  Coordinates do not guarantee raw mouse routing: Cua may hit-test internally.

- Keep native task context to the caller's verbatim prompt, not an added plan.
  Hierarchy Current retains a snapshot-local root overview during deeper
  inspection. Overview pagination is explicit, and overview controls do not
  silently add executable candidates. Refresh the overview with every snapshot.

- Current-only native payload trial: user requested omitting Before. Retain
  action history, hierarchy reset behavior and execution state unchanged so
  this trial does not conflate multiple behavioral modifications.

- Experimental --hierarchy keeps the full normalized tree local; Jev inspects
  parent/child branches and explicit sibling pages without Cua calls. Flat mode
  remains default. Fresh UI observations reset navigation and references; raw
  full evidence is retained for caller handoff. Orphans stay reachable at root.

- Activation recovery is a Jev-selected bring_to_front candidate, not hidden
  keyboard delivery. Preserve degraded reason and window/Space visibility;
  reobserve after activation, keep focus through the run, restore on exit.
  Empty/degraded views do not authorize generic keyboard input; task typing
  uses observed field targets rather than an unknown focused destination.

- Controlled Spotify focus/Space test (2026-09-24): identical get_window_state
  args, pid 98142/window 41672. On its active Space with Spotify foreground,
  repeated reads yielded 985 rows/984 web controls. Returning to ChatGPT on
  another Space yielded zero rows and degraded AX state; repeated twice.
  Activation was independently verified and original foreground restored.
  Foreground and Space changed together: do not claim focus alone is causal,
  or generalize this to every prior menu-only capture or all desktop apps.

- User raised the normalized window-control limit from 1000 to 2000 for the
  Spotify trial. Keep the separate raw 2000-element limit and 40 KB request
  guard unchanged; acceptance of controls does not prove API/task success.

- Replaying scoped-18's empty degraded response against committed normalization
  stops with missing_snapshot; current normalization accepts it and generic
  extras offer foreground typing without a known focused field. This is a
  reproduced runner regression, not proof of why Cua omitted web controls.
  Separate observation failures from recovery-selection defects; changing PIDs
  or window IDs alone is not a diagnosis. Preserve degraded reason in context.

- Jev-selected scoped inspection uses observed-label substring queries. Consume
  that returned snapshot directly; another read would replace its action map.
  Mark query views partial, never infer absence or completion from them, and
  retain reobserve as the full-window escape. Inspection is not task progress.
  The first live scoped trial reached Drive via URL and Return but received an
  empty degraded AX response (once with contradictory matched capability data).
  No inspection choice was executed; do not claim live inspection or Sheets passed.

- Before may be a lossless reverse patch against Current, selected only when
  smaller. This is byte-structure sharing, never a claim that element indices
  retain UI identity. Preserve missing versus null, control ordering and all IDs.
  Control tables factor common defaults with explicit exceptions and repeated
  label/value dictionaries only when profitable.

- User raised the local serialized-request guard to 40,000 bytes. This supersedes
  the earlier 28 KB policy; it is not a claim about Jev's token capacity.

- Observation elements use lossless column-table encoding with role/action
  dictionaries at the provider boundary. Preserve every control, explicit null,
  and original ID. Full structured observations remain unchanged locally.

- User requested removing first-N element trimming. Preserve all normalized
  window-content controls through payload construction and compaction, including
  controls outside the selected candidate group. Keep deduplication and report
  budget failures explicitly instead of silently restoring trimming.

- Driver tool_invocation_failed may return to Jev only after successful fresh
  observation, preserving uncertain effect and error details. Share the existing
  three-recovery budget; transport failures still stop. Never auto-replay a call.

- Factor repeated candidate tool/argument/description data into provider-visible
  templates and references before context trimming. Compression must round-trip
  exactly; execution continues to use immutable original candidates, not references.

- Preserve observed app name and window title even when AX controls are absent.
  Tell Jev the inferred application type, with provenance; unknown apps stay
  unknown. App classification supplies context, never a hardcoded action plan.

- off_space_or_ax_unresolved with effect=refused also permits bounded refresh
  and Jev reselection. Empty degraded exact-window observations need not have
  Driver snapshot IDs: assign a local unindexed identity, retain incomplete
  coverage, and never invent element handles. Foreground remains Jev-selected.

- User observed the Casablanca native-only test reach the relevant search-summary
  section, "In what country is Casablanca", but the browser appeared not to
  respond. Retain this as user-observed progress; do not reduce that run to
  irrelevant navigation or claim the cause of the apparent unresponsiveness.

- User requested removing automatic get_browser_state choices from native runs.
  Keep native observation on get_window_state; standalone browser runner remains
  separate. Do not reintroduce implicit existing-profile attachment.

- Large valid tree_markdown is not an invalid observation: retain raw snapshots
  locally and bound the provider projection separately. Preserve executable
  arguments and task intent; disclose context omissions. The 28 KB serialized
  request guard is a local byte policy, not a measured Jev token limit.

- Preserve user-required flow and input purposes in a structured task brief;
  do not treat a website URL and a query as interchangeable task inputs. Single
  action tests change context, not the executable sequence or expected answer.

- An explicit element_outside_target_window refusal with effect=refused permits
  fresh observation and Jev reselection (at most three recoveries per run).
  Never treat transport errors or unverifiable execution as safe automatic retries.

- Retain bounded Driver error text and structured refusal details. Schema-valid
  keyboard arguments do not prove background delivery is available. Preserve
  observed background_input routes; suppress refused keyboard routes and offer
  explicit exact-window foreground candidates for Jev selection, never an
  automatic foreground retry. Missing capability reports mean unknown support.

- Full nested candidate trees plus schemas exceeded Jev's token limit (HTTP 400).
  Transport now uses all-tool parameter indexes and three-child group previews
  with omission counts; complete schemas stay local for validation. Local SDK
  serialization tests do not establish live API acceptance or task success.

- Task runners send all advertised Driver input schemas as a compact catalog,
  structured executable choices, shared exact bindings, and group children.
  Catalog visibility is not authorization or argument generation. Always execute
  the original immutable candidate, never reconstruct a call from provider text.

- Preserve the original Jev state contract: goal, observation, and top-level
  decision history. Use Before/Current terminology, retain probabilities and
  execution results, and never equate observed change with task progress.
  Candidate-group selection is not a UI action and must not advance Before.

- Expose Driver actions from schemas and observed capabilities, not task-name or
  research-only allowlists. Keep all candidates reachable through Jev-selected
  groups. Open-ended or sensitive tools require explicitly authorized task options;
  schema coverage is not live-platform verification or blanket execution consent.
- Empty native checks mean evidence review, never automatic success. Do not use
  an address-bar milestone as the completion check for a document-creation task.

- Keep the Jev skill short and self-contained; no mandatory Markdown reading chain.
  Do not add task-specific examples or expand it into a runner manual after the
  user requests generalization. Keep script pointers and the decision loop concise.
  Operational means naming real entry points, task schemas, commands and result
  handling—not vaguely referring to helpers. Do not claim docs add capabilities.
  Organize the skill around reusable components and the shared interaction loop,
  with Codex preparing intent/content first and reviewing evidence last; do not
  make historical test scenarios or runner schemas define the skill's purpose.
  Example-runner restrictions must not redefine the user's general computer-use
  goal. User frustration is not permission to replace Jev with Codex navigation.

- The user subsequently approved experimental skill packaging for test drives
  and iterative gap capture; this supersedes the earlier all-tests-pass gate.
  Do not treat successful unit tests or a blocked preflight as a passed app task.
  An upgrade/device-compatibility prompt is not permission to migrate user data.
- Missing candidates are not evidence of a Cua Driver limitation. Log observation,
  candidate, decision, execution, environment and handoff gaps separately. Keep
  diagnostics observational; Codex must not silently take over Jev navigation.

- The user explicitly requested a native default confidence cutoff trial of 0.1
  (previously 0.4, originally 0.5). Keep it overridable, and distinguish accepting more actions
  from improving their correctness. Context comparisons retain their explicit
  historical 0.5 evaluation threshold unless separately changed.

- Context-format experiments must keep goal, ordered choice IDs/descriptions,
  and SDK path fixed. Separate compact-current from before/after variants because
  prior-state text adds information. A better selected action at low confidence
  is not an executable success; do not promote a format based on two repetitions.

- Jev navigates; an evidence_handoff asks the calling assistant to review or
  answer. Neither finish nor review proves success. Preserve failure evidence.
  Calculator Clear may remove only the current operand; All Clear resets the
  expression. Judge reset from readback, not the requested click or tool success.
  Probability totals at 0.99/1.01 require a tiny floating-point boundary allowance
  to honor the intended inclusive 1% tolerance, not a broader policy relaxation.

- Reuse original browser setup/adapter for task-driven research. Keyword queries
  can return fragments; offer scoped region reads before treating evidence as
  sufficient. Link labels do not prove destination: host checks happen after
  navigation and must not be described as a pre-navigation security boundary.

- Codex translates intent; the runner executes explicit setup, Cua executes tools,
  and Jev chooses task actions. Do not require Jev to reconsider an explicit app
  launch or offer reobserve before a target exists. Dry-run must never launch.

- Calculator's non-actionable display rows were present in tree_markdown but
  absent from structured elements (elements_complete=false). Do not equate an
  unchanged actionable-element list with an unchanged UI, invent a Display label,
  or claim automated verification from a separate diagnostic text readback.

- Distinguish shared SDK transport from shared adapter behavior: the browser and
  native paths call different adapter functions. Compare retained responses
  offline before attributing failures to stricter validation; synthetic failures
  demonstrate a possibility, not the cause of a historical failure.

- User prefers small reversible commits and a separate Git repository.
- Locate source files before content searches; avoid scanning generated runs,
  virtual environments, or the entire monorepo for common terms.
- Unsupported Driver behavior is a limitation to report, not a reason to widen
  scope or silently switch to foreground/pixel input.
- The installed uv 0.6.17 rewrites newer lockfile metadata when adding a dependency.
  Preserve baseline lockfile formatting and resolved versions; review for churn.
- SDK invocations and model-shaped responses are not dashboard-confirmed API
  usage. Retain HTTP status, endpoint, UTC time, provider request ID and reported
  token counts; distinguish local evidence from account/dashboard attribution.
- Real macOS snapshots may include entire system menus and auxiliary windows.
  Test their shapes; do not assume fixture-sized trees or exactly one window.
- User requested raising the window-content observation limit from 200 to 1000.
  Keep the separate raw-element and candidate limits unchanged for this change.
- Google Drive/Sheets in Chrome exceeded native v0's former 200-element observation
  limit immediately after focusing the address bar or exposing web content.
  Record this as an observation gap; a Jev-selected focus click is not evidence
  that navigation or sheet editing occurred, and Codex must not silently finish
  the browser task manually.
- For Drive/Sheets editing tasks, native v0 may observe many web elements but
  exclude them from executable candidates; a provider-side 400 before dispatch is
  a decision/request gap, not a completed browser action. Preserve the trace and
  log the gap instead of manually creating or editing the sheet outside Jev.
