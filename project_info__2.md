# AutoGameOps — Codebase Overview (Brick QA Automation)

## Summary
This project is a **Streamlit web app** that turns a human QA command (Vietnamese/English) into a **JSON action plan** using **local LLMs (Ollama)**, then executes the plan against the web UI **“The Brick”** via **Playwright (CDP attach)**. It supports a normal “AI Run (theo lệnh)” mode and a “Smoke Brick Live (theo CSV)” mode that repeatedly generates commands from CSV test cases and executes them end-to-end. The key value for developers is the combination of: (1) strict AI→JSON orchestration, (2) deterministic post-processing (action fixer), and (3) large amounts of UI-specific heuristics for unreliable web widgets (Vue multiselect, select2, collapse panels, SweetAlert2/Bootstrap modals).

## Architecture
**Primary pattern:** pipeline + deterministic orchestration.
- **AI layer (`ai/`)**: converts free-form command → JSON plan (Fast/Careful pipelines).
- **Post-processing (`ai/action_fixer.py`)**: deterministic repair/merge of AI output into a safe executable plan.
- **Automation layer (`automation/`)**: executes JSON plan step-by-step with Playwright.
- **UI (`app.py`)**: Streamlit front-end, shows generated plans and execution logs.

**Technology stack**
- Python + Streamlit
- Local LLM calls to **Ollama** (`http://localhost:11434/api/generate`)
- Playwright sync API, connecting to an already-running Chromium via **CDP** (`http://localhost:9222`)
- Pandas/CSV for smoke runs and CSV fuzz/sanity testing

**Execution start**
1. User enters a command → `app.py` calls `ai.brain.parse_command_to_json()`.
2. AI returns plan → stored in `st.session_state.current_plan`.
3. On “execute”, `automation.core.BrickAutomation.execute_action()` runs the plan sequentially.

## Directory Structure (meaningful parts)
```text
project-root/
├── app.py                         — Streamlit UI (command input, run, smoke runs, logs)
├── ai/
│   ├── brain.py                   — AI pipelines (Fast/Careful) + JSON cleanup/parse
│   ├── prompts.py                 — Prompt templates for planning
│   └── action_fixer.py           — Deterministic post-processing/repair of AI plans
├── automation/
│   ├── core.py                    — Execution dispatcher (Playwright + safety nets)
│   ├── navigator.py              — Menu/panel navigation + click heuristics
│   ├── form_handler.py           — Field filling, dropdown handling, and save logic
│   ├── table_handler.py          — Table checkbox selection + edit/clone row + reorder
│   ├── data_handler.py           — CSV manipulation + upload/download wiring
│   └── smart_tester.py          — CSV fuzz campaign + “smart test cycle”
├── config/
│   └── scenarios.json (at runtime) — saved AI scenarios (not hardcoded)
├── downloads/                     — CSV fixtures & generated reports
└── scripts/                       — helper scripts (start browser debug, login setup)
```

## Key Abstractions

### `parse_command_to_json()` (AI Orchestrator)
- **File**: `ai/brain.py` (function `parse_command_to_json`)
- **Responsibility**: Converts `user_command` → JSON action plan using:
  - Fast Mode: single Qwen model
  - Careful Mode: DeepSeek reasoning → Qwen formatting
  - Complexity detection auto-escalates to Careful
- **Interface**:
  - `parse_command_to_json(user_command, use_fast_mode=True, context_plan=None, base_command=None)`
- **Lifecycle**: Stateless across runs except `last_actual_mode` and scenario reuse.
- **Used by**: `app.py` for both AI-run and smoke-run command planning.
- **Non-obvious design**:
  - Uses `clean_json_string()` to “salvage” malformed JSON from LLM output (removes comments, strips code fences, fixes brace/bracket counts).

### `fix_action_plan()` (Deterministic Plan Repair)
- **File**: `ai/action_fixer.py`
- **Responsibility**: Make LLM output executable by enforcing invariants:
  - Normalize invalid action names
  - Fix field names for certain actions
  - Merge consecutive `navigate` steps into one `navigate(path=[...])`
  - Merge deployment checkboxes into a single `process_deployment(options=[...])`
  - Inject missing `clone_row` when user command contains “Clone …”
  - Inject `save_form(mode="clone")` after clone modal fields
  - Merge consecutive `update_form → save_form(save)` pairs to avoid multi-phase validation errors
- **Interface**: `fix_action_plan(plan, user_command="")`
- **Lifecycle**: Pure transformation; no browser calls.
- **Used by**: `ai/brain.py` after parsing and by scenario patching.

### `BrickAutomation.execute_action()` (Playwright Dispatcher)
- **File**: `automation/core.py` (`BrickAutomation.execute_action`)
- **Responsibility**: Executes each plan step sequentially using mixins:
  - `NavigatorMixin`, `TableHandlerMixin`, `FormHandlerMixin`, `DataHandlerMixin`, `SmartTesterMixin`
- **Interface**:
  - `execute_action(action_plan)` where `action_plan` is list/dict/str JSON
- **Lifecycle**:
  - Connects to existing browser via `connect_over_cdp`
  - Runs inside Playwright `sync_playwright()`
  - Returns `report_logs` list of `{step, status, details}`
- **Non-obvious design**:
  - Before executing `click/select/update_form/save_form`, it tries to close/ack modals:
    - SweetAlert2 clone confirmations (`_ensure_swal2_clone_confirmation_yes`)
    - Bootstrap/RBE “Are you sure” confirmations (`_ensure_rbe_are_you_sure_closed`)
  - After each step: sleeps `time.sleep(1)` (simple throttling).

### `smart_click()` / navigation expansion
- **File**: `automation/navigator.py`
- **Responsibility**: Clicks the right menu/tab/panel item across different UI structures and timing behaviors.
- **Interface**:
  - `smart_navigate(page, target)` handles list paths vs single target strings
  - `smart_click(page, target_text)` attempts multiple strategies to locate clickable UI elements
- **Used by**: `BrickAutomation.execute_action()` for `navigate` and `click` steps.
- **Non-obvious design**:
  - Special expansion logic for PVE accordion panels:
    - `_try_expand_pve_section()` uses `aria-controls` + `aria-expanded` to decide whether to click.
  - Special handling for “Contest Superstars” sidebar accordion expansion.

### `_smart_update_form()` (Major Form Filling Engine)
- **File**: `automation/form_handler.py` (`FormHandlerMixin._smart_update_form`)
- **Responsibility**: Fills all fields mentioned in `data: dict` using a priority-ordered workflow:
  - Custom “Contest Superstar” PVE v2 special-case
  - Datetime/schedule handling
  - Radio and inline edit detection
  - Generic input/select/toggle fill with widget-specific dispatch
- **Non-obvious behavior**:
  - Has an explicit **special-case for PVE v2 “Contest Superstar”**:
    - toggles the main checkbox
    - opens each Normal/Hard/Hell tab header
    - uses visible-input probes to avoid collapsing/hidden-panel misfills
    - sets SS multiselect + soft currency multiselect + numeric amount per panel
    - sets top-level RBE multiselect outside panels
    - finally removes Contest Superstar-related keys from `data` so generic filler does not misfill
- **Used by**: `execute_action()` on `update_form` steps.

### `_handle_js_dropdown()` (Widget-Specific Dropdown Selection)
- **File**: `automation/form_handler.py` (`FormHandlerMixin._handle_js_dropdown`)
- **Responsibility**: Opens Vue multiselect / chosen / select2-like dropdowns and selects an option using:
  1. Direct JS option matching/click (fast, avoids thousands of element round-trips)
  2. Search-box typing if the widget has a search input
- **Lifecycle**: Repeated per field.
- **Non-obvious design**:
  - Uses short polling loops with JS `evaluate` to count visible options rather than `locator.all()` which is too slow.

### `_save_form()` + network interception for reliable error detection
- **File**: `automation/form_handler.py` (`FormHandlerMixin._save_form`)
- **Responsibility**: Click the correct Save button and detect success/failure:
  - Detect modal scope (`.modal.show`, `.modal.in`, etc.)
  - Prefer correct button in PVE Match page (green “Save” at bottom)
  - Inject JS monkey-patch for `XMLHttpRequest` and `fetch` to capture API responses
  - Still detects SweetAlert2 and Bootstrap toast errors as backup
  - If error includes datetime parsing failure, auto-fixes and retries save
- **Used by**: `execute_action()` on `save_form` steps.

### `smart_test_cycle()` (CSV fuzzing + sanity check)
- **File**: `automation/smart_tester.py` (`SmartTesterMixin.smart_test_cycle`)
- **Responsibility**: Runs a two-phase cycle for CSV:
  1. Negative fuzz tests where “upload FAIL” is expected
  2. Valid import sanity test that should succeed
- **Non-obvious design**:
  - For RBE CSVs: uses specialized `RBESmartTester` and RBE-specific fuzz generator.
  - Injects a fast JS popup/result capture script during uploads (MutationObserver + polling) to classify PASS/FAIL rapidly.

## Data Flow

1. **User input**
   - Streamlit `app.py` captures text command or smoke CSV testcase.
2. **AI planning**
   - `ai/brain.parse_command_to_json()` runs Fast or Careful pipeline.
   - `clean_json_string()` makes LLM JSON parseable.
3. **Deterministic repair**
   - `ai/action_fixer.fix_action_plan()` merges navigation steps, injects clone/save ordering, and normalizes action names.
4. **Execution**
   - `automation/core.BrickAutomation.execute_action()` iterates the plan list.
   - For each step:
     - `navigate`: uses `NavigatorMixin.smart_navigate()`
     - `click`: uses `smart_click()`
     - `update_form`: uses `FormHandlerMixin._smart_update_form()`
     - `save_form`: uses `FormHandlerMixin._save_form()` including JS network capture
5. **Result reporting**
   - Each step produces a log record; Streamlit updates UI with logs and success/failure summaries.

## Non-Obvious Behaviors & Design Decisions

### 1) “AI plan is not trusted” → action fixer makes it executable
Rather than relying on LLM correctness, the codebase assumes LLM output will violate invariants (wrong action names, missing clone/save ordering, incorrect save mode). `fix_action_plan()` encodes domain invariants (especially clone/save ordering and multi-phase form save grouping).

### 2) Multi-phase form validation is handled by *merging saves*, not by “waiting”
For tournament/multi-phase forms, splitting fields across separate saves triggers UI validation constraints. The fixer merges consecutive `update_form → save_form(save)` sequences into a single combined update+save so the UI validates coherently.

### 3) Save correctness uses both UI popup and HTTP interception
`_save_form()` injects JS to capture HTTP POST/PUT/PATCH responses. This makes the system more robust when UI popups are inconsistent or delayed. It still keeps UI detection as a fallback.

### 4) Dropdown selection avoids Playwright element enumeration at large scale
Widget options can be huge (thousands). `_handle_js_dropdown()` avoids iterating all options in Python; it uses `page.evaluate()` to match and click options directly.

### 5) PVE v2 “Contest Superstar” is a dedicated state-machine-like workflow
The special-case in `_smart_update_form()` exists because the UI uses:
- a toggle that can collapse panel sub-sections,
- collapsible tab headers (Normal/Hard/Hell),
- multiselects and placeholders that are easy to mis-target.
The code mitigates this by:
- probing for **visible** inputs rather than DOM existence,
- re-opening the panel header only when expected inputs are missing,
- scoping selectors to the correct panel_root,
- removing special-case keys after the workflow to prevent generic filler from misfilling “Gate” or other similarly named controls.

### 6) Execution-level modal handling happens *before* risky actions
In `core.execute_action()`, before `click/select/update_form/save_form`, it attempts to dismiss:
- SweetAlert clone confirmations
- RBE “Are you sure” confirmations
This is important because an open confirm modal can cause the action to target the wrong DOM or throw.

### 7) Smoke mode uses strict “CREATE/CLONE → freeze IDs per feature” guard
`app.py` tracks `smoke_last_created_id_by_feature[feature]`. For later testcases in the same feature, it rewrites prompts like “Sửa ID bất kỳ” into the concrete created ID, preventing “random edit” drift.

## Module Reference (one-liners)
| File | Purpose |
|---|---|
| `app.py` | Streamlit UI + smoke runner + plan display + execution trigger |
| `ai/brain.py` | LLM planning orchestration (Fast/Careful) + JSON cleaning |
| `ai/prompts.py` | Prompt templates & strict action-name instruction set |
| `ai/action_fixer.py` | Deterministic repair/merge/injection of the plan |
| `automation/core.py` | Playwright execution dispatcher + modal safety nets |
| `automation/navigator.py` | Smart menu/tab navigation + PVE accordion expansion |
| `automation/form_handler.py` | Main UI field filler + widget dropdown logic + save validation |
| `automation/table_handler.py` | Table checkbox/edit/clone/random selection + reorder by drag handles |
| `automation/data_handler.py` | CSV manipulation offline + download/upload triggers |
| `automation/smart_tester.py` | Upload fuzzing + popup classification + RBE specialized testing |

## Suggested Reading Order
1. **`app.py`** — see how commands become plans and how plans become executions.
2. **`ai/brain.py`** — understand Fast/Careful pipelines and JSON cleanup.
3. **`ai/action_fixer.py`** — understand the invariants and why the system fixes AI mistakes.
4. **`automation/core.py`** — understand the step dispatcher and modal handling.
5. **`automation/form_handler.py`** — focus on `_smart_update_form()` and `_save_form()` (contains most UI-specific logic, including Contest Superstar special-case).
6. **`automation/navigator.py`** — understand how it expands accordions and finds clickable elements.
7. **`automation/smart_tester.py`** — understand how CSV fuzzing and popup capture works.