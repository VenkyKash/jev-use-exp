# Experimental Jev runner

Keep changes inside this repository. Preserve the copied browser demos as the
regression baseline. The native v0 is Python-only; do not claim native TypeScript
or cross-platform parity until tested. Do not modify Cua Driver to fit this agent.

Every task mutation, including app launch, must be selected by Jev in live mode.
No Codex runtime, hidden planner, hard-coded app sequence, or model fallback.
Mock providers prove mechanics only. Keep expected verification values out of
provider requests; never treat a tool success response as task completion.

Use uv. Run focused tests before each implementation commit and the complete
Python suite plus preserved TypeScript checks before final handoff. Keep runtime
logs untracked; they may contain user-supplied text and UI content.

## Notes to self.

- User prefers small reversible commits and a separate Git repository.
- Locate source files before content searches; avoid scanning generated runs,
  virtual environments, or the entire monorepo for common terms.
- Unsupported Driver behavior is a limitation to report, not a reason to widen
  scope or silently switch to foreground/pixel input.
- The installed uv 0.6.17 rewrites newer lockfile metadata when adding a dependency.
  Preserve baseline lockfile formatting and resolved versions; review for churn.
