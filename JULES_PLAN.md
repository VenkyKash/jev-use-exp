# Handoff Plan for Jules: Cross-Platform GUI Testing & Semantic AX Navigation

## 1. Context & Architecture
- **Jev** is a decision model we leverage to make computer-use decisions and drive action selection based on GUI / Accessibility tree observations provided by Cua Driver.
- **Jules** is an autonomous coding agent from Google operating in a cloud Linux VM. Jules has full authority to install system packages, build cross-platform capabilities, configure virtual displays, and run GUI test tasks autonomously.
- **Payload Solution:** We previously hit a 40KB payload limit sending large AX trees to Jev. We successfully deployed `--hierarchy` mode, which presents the tree as expandable parent/child branches. This keeps the payload small by requiring Jev to iteratively drill down into menus.
- **The Core Navigation Challenge:** While `--hierarchy` solved the payload issue, it exposed a fundamental semantic hurdle: GUI containers often have misleading or generic labels (e.g., an entire dropdown menu container being labeled `"Folder menu"`, while holding items like `"Google Sheets"`). Jev relies on semantic text to choose what to expand, so it avoids digging into misnamed containers.

## 2. Setting Up Jules (GitHub & Environment Variables)
Per the [Jules Documentation](https://jules.google/docs/):
1. **GitHub Connection:**
   - Sign in at [jules.google.com](https://jules.google.com).
   - Click **Connect to GitHub account** and grant access to this repository.
   - Select the target branch for Jules to work on.
2. **Environment Variable Configuration (`TYPESAFE_API_KEY`):**
   - Go to the **Repository Settings** page in the Jules UI (`jules.google.com`).
   - Add `TYPESAFE_API_KEY` under the repository environment variables.
   - When launching the task in Jules, check/enable the environment variable for the task.
3. **AGENTS.md Support:**
   - Jules automatically detects and reads [AGENTS.md](file:///Users/Venky/Codex/misc/cua-jev-use/libs/cua-driver/examples/jev-use-exp/AGENTS.md) in the root of the repository to guide its behavior and adhere to all design constraints.
4. **API Call Budget:**
   - Jules is strictly budgeted to a maximum of **500 API calls** to Jev across its testing iterations.

## 3. Mission for Jules: Linux GUI Testing & Cross-Platform Execution
You are encouraged to leverage the Linux VM environment to build, run, and validate real GUI tests:
1. **Set Up Linux GUI Environment:**
   - You can install GUI libraries and virtual display utilities (e.g. `xvfb`, `x11-utils`, GTK/Qt/Tk test apps, system browsers like Chromium/Firefox, AT-SPI accessibility packages).
   - Configure a headless X11 / virtual display session (`DISPLAY=:99 Xvfb :99 -screen 0 1280x1024x24 &`).
2. **Cross-Platform Runner Evolution:**
   - The native runner currently has a macOS platform guard (`sys.platform != "darwin"`). Evolve the runner to support Linux GUI accessibility and desktop element tree structures (AT-SPI / browser accessibility).
   - As stated in `AGENTS.md`: *"do not claim native TypeScript or cross-platform parity until tested."* Your testing in the VM is what enables and verifies this cross-platform capability!
3. **Run Simple to Compound GUI Tasks:**
   - Run simple tasks (button clicks, form filling, basic menu navigation) up to compound tasks (multi-step workflow navigation, dropdown menus, complex subtrees).
   - Verify the decision loop end-to-end against Jev in Linux.

## 4. The Core Problem to Solve: Semantic Container Discovery
When navigating hierarchical trees, containers often hide their contents behind unhelpful or generic names:
- **Observed Case:** In Google Drive, clicking `+New` opened a menu container labeled `"Folder menu"`. Inside were `"New folder"`, `"File upload"`, and `"Google Sheets"`. Because the branch was only labeled `"Folder menu"`, Jev gave it low probability when asked to *"create a new google sheet"*, and retreated back to root without ever seeing `"Google Sheets"`.
- **The Architectural Fix:**
  - **Child / Keyword Previews:** Enhance the hierarchy compaction/summarization logic to preview child element labels or keywords inside collapsed container branches:
    > e.g.: `tree-expand-38: "Folder menu [contains: New folder, File upload, Google Docs, Google Sheets, ...]"`
  - **Container Role Hinting:** Surface interactive container roles (menus, popups, dropdowns) so Jev recognizes them as exploratory branches rather than static objects.
  - **Exploration Prompting:** Ensure Jev's decision prompt encourages inspecting relevant container types when the specific target is not directly present at the root level.

## 5. Strict Constraints (per `AGENTS.md`)
You must strictly adhere to the project rules:
- **No Cua Driver Hacks:** Do not modify Cua Driver to fit this integration. Keep changes in this example/runner repository.
- **No Silent Takeovers:** Diagnostics must be observational. The assistant must not silently take over Jev navigation, use manual fallback logic, or script the app sequence.
- **No Fudging Coordinates:** Each choice dispatches one click. No random offsets, expanded hitboxes, or automatic retries.
- **No Merging:** Keep one executable ID with descriptive aliases, not competing probability slots.
- **Preserve Context:** The native task context is the caller's verbatim prompt, not an added plan.
- **Regression Safety:** Ensure existing unit tests (`uv run python -m unittest discover -s python/tests`) continue to pass.

## 6. Distractions to Avoid
- **Payload Limits:** The 40KB limit is solved via `--hierarchy`. Do not revert to patching token limits or truncating the tree manually.
- **Cua Driver Bugs:** Mislabeled containers are a universal GUI reality, not a driver bug. Do not try to "fix" the driver.
- **Forcing a Pass:** Do not hardcode tasks to pass. Focus on robust, generalizable observation formatting, container discovery, and cross-platform GUI execution.
