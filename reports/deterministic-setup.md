# Deterministic app setup

The user clarified the ownership boundary: Codex translates intent into a task;
the runner performs explicitly authorized setup through Cua; Jev chooses task
actions from observations. Launch no longer consumes a Jev decision or depends
on model confidence. No automatic app navigation or click sequence was added.

The runner launches once, binds an unambiguous window using the existing rule,
and observes it before the first Jev request. Explicit target attachment skips
launch. An uncertain launch is never retried. Without a target, dry-run reports
planned setup without launch or inference. Attached dry-run still performs one
non-mutating Jev decision. Confidence checks for Jev decisions are unchanged.

Added --read-only: after app setup, only reobserve and abstain are available.
This is an execution constraint, not just a natural-language instruction. It
does not implement free-text reporting or fix incomplete accessibility readback.

## Live Obsidian smoke

On September 19, 2026 at 6:39 PM Pacific, the updated runner launched Obsidian
without a model call and bound PID 86064/window 35178. Then three Jev requests
returned HTTP 200. Jev selected reobserve with confidence 0.88, 0.79, and 0.79.
The no-progress guard stopped the run. No clicks, typing, vault selection, or
note edits were dispatched.

Jev received the current window title and three unlabeled AXButton controls.
The observation was explicitly incomplete; 143 menu elements were excluded.
The note body/editor was not present in the normalized observation. Therefore
startup works, but note-content inspection/reporting is not established.
The trace is in ignored runs/obsidian-deterministic-setup-01.jsonl.

Regression checks: 76 Python tests, 24 TypeScript tests, and TypeScript typecheck
passed, including deterministic setup, no startup chooser call in dry-run,
uncertain-launch safety, and read-only action exclusion.
