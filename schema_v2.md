# Jev Payload v2 (Draft): Coarse-to-Fine Choice

Status: **design proposal, not implemented or tested.** The current payload is
documented in `schema.md` and stays the baseline until v2 is compared against it
on the same goals and candidate sets.

## Principles

- Every question uses Jev's native shape: `type: "choice"`, one plain-string
  `instructions`, and `criteria` mapping IDs to self-contained sentences.
- Criteria IDs map locally to immutable candidates. Tool names, arguments, AX IDs
  and coordinates never go to Jev, and the runner never rebuilds a call from text.
- Dual Observation (Accessibility + Vision): structural controls come from AX
  (`get_window_state`), complemented by optical screen detection (`parse_visual_regions`
  and display readouts). Jev is instructed to consult visual choices to verify values
  rendered inside custom canvases (e.g. spreadsheets, calculator displays).
- No transport encodings (column tables, patches, `$ref`, templates). Requests
  stay small because each question offers a bounded set of options.
- Jev selects every task mutation, including "back".
- Jev also selects the app and window (Step 0). The user supplies only the command.

## Step 0: App and window

Asked at the start of a run, and again whenever Jev picks `switch_app` in Step 1.
The runner only builds the option list; it never picks or ranks apps by task name.

```json
{
  "state": {
    "goal": "You're a computer-use agent that is making real-time decisions based on the UI tree that you receive to navigate the console to accomplish the user's request below. Sometimes you would have to look through different hierarchies in the UI tree to get to the right destination. When entering data in grids, forms, or documents, check your active position and align horizontally and vertically before typing. The goal is to be able to accomplish this task -- feel free to take liberty in exploring a console if you don't understand it at first. <caller's verbatim prompt>",
    "current_app": "GridCraft window 'Book1' (spreadsheet)",
    "worked": [], "did_not_work": []
  },
  "questions": {
    "app": {
      "type": "choice",
      "instructions": "Which application window should be used to accomplish the goal?",
      "criteria": {
        "current": "Continue working in GridCraft window 'Book1' (spreadsheet, running, frontmost)",
        "w_chrome_1": "Google Chrome window 'Inbox - Gmail' (web browser, running)",
        "w_notes_1": "Notes window 'Notes' (note editor, running)",
        "launch_filmcraft": "Launch FilmCraft (video editor, installed)",
        "launch_weather": "Launch Weather (utility, installed, not running)",
        "launch_calculator": "Launch Calculator (calculator, installed, not running)",
        "more_apps": "Show more installed applications",
        "cannot": "No listed application fits the goal; hand off to the user"
      }
    }
  }
}
```

### Option list

- **Current bound window:** when Jev is already working in a window, `"current"` provides immediate continuity so Jev does not need to re-evaluate the full application catalog unless an explicit switch is intended.
- **Running windows:** one option per on-screen window of each running regular
  app (from the window list, with title and small functional descriptor like `web browser`, `spreadsheet`, `video editor`). Selecting one binds that exact window.
- **Installed apps:** from /Applications, /System/Applications and
  ~/Applications, with small category descriptors. Pages of a bounded size, sorted
  alphabetically (not by guessed relevance); `more_apps` shows the next page.
- **Launch result:** after a launch, the runner observes the new app. If it
  opens exactly one window, that window is bound. If it opens none or several,
  Step 0 is asked again with only that app's windows.
- Background agents, helpers and menu-bar-only processes are not listed.

### Safety

- Launching changes the user's machine. It requires the run's task options
  to allow app launch; if they don't, `launch_*` options are omitted.
- First-run, login, update or migration prompts after launch are observations
  for Jev to handle or hand off. They do not permit migrating or changing
  user data.
- A launch or bind succeeding is not task progress. `last_action` judges it
  like any other action.
- Dry-run lists options but never launches or binds.

## Step 1: Region

```json
{
  "state": {
    "goal": "You're a computer-use agent that is making real-time decisions based on the UI tree that you receive to navigate the console to accomplish the user's request below. Sometimes you would have to look through different hierarchies in the UI tree to get to the right destination. When entering data in grids, forms, or documents, check your active position and align horizontally and vertically before typing. The goal is to be able to accomplish this task -- feel free to take liberty in exploring a console if you don't understand it at first. <caller's verbatim prompt>",
    "app": "Google Chrome, window 'Weather - Tokyo'",
    "screen": "One-paragraph summary: visible areas and their key labels.",
    "worked": [
      "Typed 'weather.com' into the address bar and pressed Return: weather.com loaded"
    ],
    "did_not_work": [
      "Clicked the 'Gmail' bookmark: opened Gmail, unrelated to the goal"
    ]
  },
  "questions": {
    "last_action": {
      "type": "choice",
      "instructions": "Judging only from the current screen, did the most recent action move toward the goal?",
      "criteria": {
        "advanced": "Yes: the screen now shows something closer to the goal",
        "no_effect": "Nothing relevant changed",
        "set_back": "It moved away from the goal or opened something unrelated",
        "unclear": "The screen does not show enough to tell"
      }
    },
    "region": {
      "type": "choice",
      "instructions": "Which area of the window should be examined for the next action?",
      "criteria": {
        "r_toolbar": "Browser toolbar: address bar, back/forward, reload",
        "r_search": "Page header with the 'Search city' field",
        "r_main": "Main content: current conditions and the 10-day forecast",
        "r_dialog": "Cookie consent dialog covering the page",
        "back": "Undo the last action by going one step back (see Back below)",
        "done": "The goal is visibly achieved; hand off for review",
        "reobserve": "Re-read the whole window before deciding",
        "switch_app": "This window cannot achieve the goal; choose a different app or window"
      }
    }
  }
}
```

## Step 2: Action within the chosen region

```json
{
  "state": {
    "goal": "...", "app": "...",
    "region": "Page header with the 'Search city' field",
    "region_detail": "Controls in this region with their labels, values and enabled state.",
    "worked": ["..."], "did_not_work": ["..."]
  },
  "questions": {
    "next_action": {
      "type": "choice",
      "instructions": "Pick the single next action in this area that best advances the goal.",
      "criteria": {
        "a1": "Type 'Tokyo' into the 'Search city' field",
        "a2": "Click the 'Search' button next to the field",
        "a3": "Click the 'Use my location' link",
        "regions": "None of these fit; go back to the region list"
      }
    }
  }
}
```

`regions` is read-only navigation between the two steps. It does not touch the app.

## Worked / did-not-work lists

- **Who decides:** Jev's `last_action` answer from the next call. `advanced` goes
  to `worked`. `no_effect` and `set_back` go to `did_not_work`. `unclear` goes to
  `did_not_work` with an "(unclear)" suffix. The runner does not decide this from
  tool success or from the screen merely changing.
- **Entry format:** one sentence: the action's description, then a colon, then a
  short observed result. Most recent last, bounded to N entries per list (N to be
  chosen experimentally).
- **Not completion:** `worked` means Jev judged a step as progress. Only reviewed
  evidence at handoff establishes that the goal succeeded.
- Region selections and `regions` returns are not actions and are never listed.

## Back (one step)

Offered as `back` only when the runner has a concrete route for the last action.
The route depends on the context:

| Last action context | Back route | Offered when |
|---|---|---|
| Browser navigation | Browser Back (exact window) | Navigation happened and Back is enabled |
| Text entry | Undo (Cmd+Z) in the observed field | Typing was delivered to a known field |
| Opened menu/dialog/popover | Escape or its Close/Cancel control | The menu/dialog is observed |
| Anything else | not offered | — |

- "Back" is a real app mutation chosen by Jev. It runs once and is never an automatic retry.
- Undo is not guaranteed. After Back, a fresh observation and the next
  `last_action` answer decide whether it worked. The step being undone stays in
  `did_not_work`. The Back step itself is also recorded in the history.
- Irreversible actions (send, delete, purchase, submit) cannot be undone by
  Back, and the option text must not suggest otherwise.

## Dual Observation (Accessibility + Vision)

For desktop and custom canvas surfaces (spreadsheets, calculators, media editors), accessibility trees frequently omit rendered text values or canvas contents. Payload v2 combines:

1. **Accessibility tree (`get_window_state`):** Provides the interactive control hierarchy, native element roles, actions, and bounds.
2. **Optical pixel analysis (`parse_visual_regions`):** When the `cua-perception` extension is installed, the driver performs OCR and icon detection directly on the composited window screenshot (`capture_id`).
3. **Display readback extraction:** Unindexed display static text values (e.g. calculator readout `"1,024"` or formula bar entries) from the driver snapshot are surfaced in `visual_readouts`.
4. **Prompt instructions:** Jev is explicitly instructed to consult visual readouts to confirm values rendered inside custom canvases and verify progress before selecting the next action.

## State Memory & Cursor Ledger

To prevent repetitive inputs and accidental overwrites during data entry:
- **`entered` ledger:** Successfully typed inputs are recorded alongside their grid location/purpose and annotated with `[already entered]` in candidate options.
- **`current_position` awareness:** The runner resolves the active cursor cell (e.g. `Column A, Row 3`) and warns if the target already contains previously entered text (`(already contains '2')`).

## Open questions

- History bound N, and whether `did_not_work` should keep only the most recent
  repeats of the same action.
- Whether `last_action` and `region` belong in one call (as shown) or `last_action`
  should be asked separately.
- How regions are derived from the AX tree (top-level groups, landmarks, window
  areas) for apps without clear structure.
- API budget: two calls per step versus one.
