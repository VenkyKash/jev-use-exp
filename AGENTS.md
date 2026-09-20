# Experimental Jev runner

Keep changes inside this repository. Preserve the copied browser demos as the
regression baseline. The native v0 is Python-only; do not claim native TypeScript
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
