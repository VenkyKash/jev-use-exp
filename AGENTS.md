# Experimental Jev Runner

Keep changes inside this repository. Preserve the copied browser demo mode as the
regression baseline while extending its shared Python modules. The native runner is Python-only;
do not claim native TypeScript or cross-platform parity until tested. Do not modify Cua Driver to fit this agent.

Use `uv`. Run focused unit tests (`uv run python -m unittest discover python/tests`) before each commit.
Keep runtime logs untracked; they may contain user-supplied text and UI content. Prefer small, reversible commits.

---

## 1. Ownership & Architecture

- **The Assistant:** Prepares the structured task brief (objective, inputs, success criteria) upfront and reviews evidence after completion. The assistant translates intent; it never scripts app actions.
- **Jev:** Autonomously chooses every task action, region, and mutation in real time.
- **Cua Driver:** Executes the chosen tools via native OS accessibility and window APIs.
- **No Hidden Planners:** Strictly no external agent runtime, background planners, hard-coded app sequences, or model fallbacks during execution. User frustration is never permission to take over Jev navigation manually.
- **App Selection (Payload v2):** Jev autonomously selects the application and window from observed running windows and alphabetical installed apps; the runner never task-ranks apps.

---

## 2. General-Purpose Cross-App Design

- **App-Agnostic:** Cross-app behavior must work identically across the standard native suite (GridCraft, Calculator, SoundCraft) under identical inputs.
- **No Bespoke Heuristics:** Strictly no app-specific branching, keyword-scoring tricks, or hardcoded workflows. App names in prompts must not bias menu ranking, generic verbs must not match system tools, and active spreadsheet cells must not be conflated with persistent controls.
- **Metadata Provenance:** Preserve observed app name and window title even when AX controls are sparse or absent. Unknown apps remain unknown.

---

## 3. Decision Contract & Choice Schema

- **Discrete Choice Format:** Every decision presented to Jev uses its native shape: `type: "choice"`, a plain-string `instructions`, and a `criteria` dictionary mapping discrete IDs to self-contained descriptions.
- **Immutable Candidates:** Criteria IDs map locally to immutable candidate objects. Tool names, raw arguments, AX IDs, and coordinates never go to Jev. The runner executes the original immutable candidate and never reconstructs calls from model text.
- **Confidence Threshold:** Native default confidence cutoff is 0.1 (overridable).
- **Navigation Flow:** Coarse-to-fine choice hierarchy (Step 0: App, Step 1: Region, Step 2: Action). `back`, `reobserve`, and `done` are explicit choices selected by Jev, never runner heuristics.

---

## 4. Observation, Geometry & Execution Safety

- **Dual Observation:** Structural accessibility (`get_window_state`) is complemented by optical pixel detection (`parse_visual_regions` and display readouts) to verify rendered values on custom canvases (spreadsheets, calculator displays).
- **Geometric Targeting:** Coordinate clicks use observed AX screen bounds transformed through validated screenshot dimensions and window bounds, never raw AX x/y pixels. Recheck window visibility and bounds before dispatch.
- **Strict Single Action:** Each choice dispatches exactly one action. No random offsets, expanded hitboxes, or automatic retries.
- **Range Selection Primitives:** Multi-item or multi-row operations must provide native range selection options (such as Shift-click or range navigation hotkeys) to prevent step-budget exhaustion and latency inflation from repeated single-unit loops.
- **Perception Budget Completeness:** Optical perception options (`max_regions`, `max_lines`) must be scaled to encompass the entire active document canvas. Truncating optical regions blinds Jev to task completion conditions and causes boundary overshooting.
- **Failure Recovery:** Explicit refusals (`element_outside_target_window`, `tool_invocation_failed`) permit fresh observation and Jev reselection (up to 3 recoveries per run). Transport errors immediately stop the run.
- **Observation Limits:** Normalized window-content limit is 2,000 controls; local serialized-request guard is 40,000 bytes. Report budget failures explicitly instead of silently trimming.

---

## 5. Verification & Evidence Standards

- **Tool Success != Task Success:** Never treat a driver tool acknowledgement, action success, or `review_required` outcome as task completion.
- **Evidence-Based Verification:** Task success requires exact unique element values or visual readback observed from the UI state.
- **Evidence Handoff:** At run completion, the runner preserves complete structured evidence (AX state, visual readouts, action history) for the calling assistant to review and answer the user. Preserve failure evidence accurately; never assume unobserved progress.

---

## 6. Jules Environment & Context7 MCP Usage

- **Context7 MCP Server:** Jules has direct access to the Context7 MCP integration (`mcp__context7__*` or MCP tool registry) to query up-to-date documentation, API schemas, and platform behavior in real time.
- **When Jules Should Query Context7:**
  - **Linux Accessibility & AT-SPI:** Query current AT-SPI2, D-Bus, and GTK/Qt accessibility specs when debugging Linux window and role divergences (e.g. role name normalization from AT-SPI to standard action mappings).
  - **Cua Driver & MCP Protocol:** Check latest MCP specification details, tool definitions (`get_window_state`, `parse_visual_regions`), and JSON Schema Draft 2020-12 nuances.
  - **TypeSafe / Jev Protocol:** Fetch latest guidelines on choice payload structure, confidence cutoffs, and hierarchical navigation contracts.
- **Workflow Rule:** Before implementing speculative fixes or guessing external tool APIs in the Linux VM, use Context7 to retrieve authoritative documentation, then verify with unit tests (`uv run python -m unittest discover python/tests`).

---

## 7. Issue Tracking & Linear MCP Usage (Project 'mogami')

- **Linear MCP Integration:** Jules has access to Linear via the Linear MCP server integration (`mcp__linear__*` tools).
- **Project Target:** File all discovered task blockers, bugs, and performance bottlenecks under the **`mogami`** project in Linear.
- **When Jules Should File an Issue:**
  - **Reprehensible Driver or Platform Blocks:** When Cua Driver or AT-SPI encounters recurring, unrecoverable crashes, protocol violations, or missing role mappings on Linux.
  - **Semantic Hierarchy Hurdles:** When real-world apps conceal key controls behind misleading container titles that cause Jev step exhaustion.
  - **Failed Task Regressions:** If an autonomous test run reveals tasks that fail verification, log an actionable issue with:
    1. Title: Clear, concise summary prefixed with component (e.g. `[Linux AT-SPI] ...` or `[Jev Navigation] ...`).
    2. Description: Exact task goal, observed failure reason, reproduction steps (`./startup_jules.sh`), and the corresponding snippet from `reports/jules_autonomous_evaluation_report.md`.
    3. Project: Assign strictly to the `mogami` project.


