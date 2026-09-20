# Native confidence cutoff 0.4 trial

User-requested change: native_run.py CLI and run_loop defaults now use 0.4,
with --minimum-confidence available for overrides. No context-format change,
candidate change, or browser policy change was made. Historical comparison
scripts with explicit thresholds retain their original evaluation settings.

Live retry: clear the existing result and calculate 93−47. Jev selected Clear,
9, 3, Subtract, 4, 7, Equals, then review. The digit 3 had confidence 0.48 and
review had confidence 0.43; both are accepted under 0.4 and would be rejected
under 0.5. No manual correction or reset sequence was supplied.

The handoff at September 19, 2026, 7:35:43 PM Pacific showed 42+93−47 and 88.
Codex review therefore marks the task FAILED: the requested result is 46.
The run completed with review_required, not verified. Clear removed only the
current operand and left 42+; the lower cutoff did not repair that decision.

Trace: ignored runs/calculator-cutoff-04.jsonl. The compact context experiment
is still not the production default; this run isolates the threshold change in
the existing native path, not the combination of compact context and 0.4.

Tests passed: 100 Python tests, 24 TypeScript tests, and TypeScript typechecking.
New coverage checks CLI/default parity, overrides, acceptance at 0.4 and 0.49,
and rejection below 0.4. This trial does not establish a calibrated confidence
policy or improved action correctness.
