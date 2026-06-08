# Memory snapshot: automation/ + ai/ + app.py (Brick AI Automation)
Generated: 2026-06-01

## High-level architecture
- `app.py` (Streamlit UI)
  - Provides two run modes:
    1) **AI Run**: user text -> `ai.brain.parse_command_to_json()` -> `automation.core.BrickAutomation.execute_action()`
    2) **Smoke Brick Live**: user CSV -> per-row command -> parse -> execute.
  - Shows generated JSON plan and execution logs.
  - For Smoke: tracks `st.session_state.smoke_last_created_id_by_feature` to replace “Sửa/Filter ID bất kỳ” with the concrete created/cloned ID for the same Feature.

- `ai/brain.py`
  - Detects command complexity; may switch between **Fast** and **Careful** pipelines.
  - Uses `ai/prompts.py` templates and `ai/action_fixer.py.fix_action_plan()` to deterministically normalize action names/fields.
  - JSON output is cleaned by `clean_json_string()` then parsed.
  - Post-fix guarantees: navigation merging, deployment option inference/merge, clone/save injection, update_form/save_form merging.

- `automation/core.py`
  - `BrickAutomation` composes mixins:
    - `NavigatorMixin`, `TableHandlerMixin`, `FormHandlerMixin`, `DataHandlerMixin`, `SmartTesterMixin`
  - Core executor: `execute_action(action_plan)`
    - Validates action names against an allowlist.
    - Safety maps invalid AI action synonyms -> canonical actions (checkbox/click/download/upload/etc).
    - Special popup pre-handling for certain actions: handles SweetAlert2 clone prompt “Yes”, and “Are you sure” modal related to RBE schedule.
    - Implements each action:
      - `navigate` -> `smart_navigate`
      - `checkbox` -> `handle_checkbox` (table selection) or `_smart_update_form` for toggles; may redirect sidebar item to `smart_click`
      - `click/select` -> `smart_click`
      - `wait` -> `_wait_for_long_loading`
      - `download` -> `_find_download_trigger` + special “Export Chapter” logic
      - `smart_test_cycle` -> `smart_test_cycle`
      - `upload` -> `handle_upload` + `close_popup`
      - `manipulate_csv` -> `_process_csv_manipulation`
      - `scan_tabs` -> `scan_all_tabs`
      - `check_fields` -> `check_fields_in_tabs`
      - `reorder` -> `drag_to_reorder`
      - `process_deployment` -> `process_deployment`
      - `edit_row/clone_row` -> `_click_icon_in_row`
      - `update_form/save_form` -> `_smart_update_form/_save_form`
  - After finishing: reloads page unless `process_deployment` ran (already on Home).

## Key state/memory rules in automation
- `BrickAutomation.__init__`: `self.memory = {}` used as short-term robot memory.
- `form_handler._smart_update_form`:
  - During “Contest Superstar” special-case, stores `LAST_CLONED_NEW_ID` when it sees keys containing “new” & “id”.
- `smart_tester` + `app.py`:
  - Smoke run: persists last created/cloned ID per Feature to rewrite later commands.

## automation constants
- `automation/constants.py`: `DOWNLOAD_DIR` is `os.path.join(os.getcwd(), "downloads")`, ensures directory exists.

## automation/core.py: popup/confirm handling
- `close_popup(page)` in core:
  - Detects modal warning containing “warning” and clicks “Continue/Proceed” when present.
  - If mixin provides `_ensure_popup_closed`, it delegates.
  - Fallback: Escape, then click OK/Close/Confirm buttons.
- `execute_action`:
  - For actions in `{click, select, update_form, save_form}` it may:
    - `_ensure_swal2_clone_confirmation_yes(page)`
    - `_ensure_rbe_are_you_sure_closed(page)` to only dismiss the specific RBE schedule confirm modal.
- Save/Clone lock behavior:
  - When `save_form` is called with `mode == "clone"`, it calls `_handle_locked_item_popup` to acquire lock before further updates.

## automation/form_handler.py: major capabilities
### `_smart_update_form(page, data)`
- Waits for loaders to disappear:
  - `.vld-icon:visible`, `.b-skeleton:visible`, `[aria-busy='true']:visible`
- Special-case “Defining Schedules”:
  - When the modal text indicates CSS schedule is restricted within RBE schedule range, it clamps Start/End values accordingly.
- Special-case “Contest Superstar”:
  - Handles toggle + Normal/Hard/Hell panel multiselects with scoped locators.
  - Fills:
    - SS multiselect (“Type to search” placeholder)
    - Soft Currency multiselect (“Select option” placeholder)
    - Soft Currency amount (number input)
    - RBE multiselect (top fieldset “legend:has-text('RBE')”)
  - Removes contest-superstar related keys from `data` after processing to avoid generic fill mis-targeting.
- Generic field filling:
  - `_find_input_element` locates inputs based on label/id/name with heavy heuristics and section-aware search.
  - Radio/toggle/date/schedule specific handling and fallback for custom dropdown wrappers.
- Vue multiselect helpers:
  - `_open_vue_multiselect()`: clicks `.multiselect__select` arrow and checks content wrapper display.
  - `_fill_vue_multiselect()`: uses `page.keyboard.type()` to generate trusted InputEvents; waits for non-sentinel options; selects best match.

### Inline edit support
- `_handle_inline_edit_field()`:
  - Finds nearby “Edit” button next to readonly text inputs (Lock Time Offset etc).
  - Clicks Edit -> fills input -> clicks inline Save/OK/Confirm.

### `save_form(page, mode=...)`
- Detects modal scope vs page scope.
- Chooses correct save button:
  - For PVE Match 1 page it prioritizes the bottom green “Save” (not “Save Book Info”).
  - For clone mode prioritizes Clone/Submit/Confirm/OK.
- Injects JS-level network interceptor before clicking save:
  - Captures POST/PUT/PATCH responses with error statuses and extracts response bodies for up to 2000 chars.
- After click:
  - Calls `_wait_after_save(page, network_error=...)` if present else fallback.
- `_wait_after_save` checks:
  - network error first,
  - SweetAlert2 popup `.swal2-popup`,
  - Bootstrap toast errors `.toast-error/.alert-danger`,
  - then success indicators.

## automation/table_handler.py: selection and row operations
- `handle_checkbox(page, target_col, value)`:
  - Finds data table (prefers one with tbody tr + checkbox).
  - Supports:
    - `random_N` or `random`
    - `all`
    - specific text match with optional filtering:
      - `_perform_table_filter` fills filter input and presses filter.
  - Random mode special: when target_col contains “id”, it tries row-by-row selecting ID cell text and uses filter/search instead of pure random checkbox tick.
- `_click_icon_in_row(page, target_text, action_type)`:
  - For `action_type in {"edit","clone"}`:
    - If target_text is RANDOM/any/bất kỳ: picks random rows matching icon availability.
    - Deterministic safeguard: if editing after cloning, uses memory `LAST_CLONED_NEW_ID` to select the correct row.
    - For edit: performs additional loader wait & then `_handle_locked_item_popup`.
- `drag_to_reorder(page, target, position/before/after)`:
  - Finds draggable handles; clusters/scopes by X coordinate.
  - Performs mouse drag-and-drop and waits for networkidle.

## automation/navigator.py: navigation and click behavior
- `smart_navigate(page, target)`:
  - If `target` is list -> `_smart_navigate_path`.
  - If string -> `smart_click` unless it looks like URL.
- `_smart_navigate_path(page, path_list)`:
  - Smart selection: exact match first, else best approximate (longest/shortest heuristics).
  - Handles singular/plural mismatches.
  - Avoids misclick for items already visible.
- `smart_click(page, target_text)`:
  - Includes special expansions:
    - “Classic PVE” fast path
    - PVE accordion sections (Chapter Info / Normal Matches)
    - Targeted “Contest Superstars” accordion expansion.
  - Prioritizes dropdown option clicks if selector matches common dropdown option containers.
  - Fallback: dialog button click, then generic text match.

## automation/data_handler.py: CSV edits
- `_process_csv_manipulation(filename, operation, data_instruction)`:
  - operations: add/edit/set/delete
  - Uses first row as headers, rewrites file.
  - `edit` uses `find_col()` and safe parsing via `safe_split`:
    - supports `col=val` or `col:val`
  - Cleans values with `clean_val()`.

## automation/smart_tester.py: fuzzing and upload verification
- `smart_test_cycle(page, file_name)`:
  - Dispatches:
    - If filename/content includes `rbe`: `_run_rbe_fuzz_campaign` and RBE offline structure checks via `RBESmartTester`.
    - Else: `_test_generic_csv` uses `GenericCSVFuzzer` and fuzz loop with JS popup monitor.
- Upload/popup handling:
  - `handle_upload(page, target_btn_name, file_name)`:
    - clears stale `window.__popupResult` and history,
    - calls `_upload_single_attempt` which uses JS-level popup capture + fallback scanning,
    - classifies popup text to PASS/FAIL using keyword heuristics.
- Popup cleanup:
  - `_ensure_popup_closed(page)` uses JS to:
    - click Continue/Proceed if warning,
    - click OK/confirm/close buttons,
    - remove overlays/backdrops as last resort.

## Known allowed action names (core)
- `navigate, checkbox, download, upload, manipulate_csv, smart_test_cycle,
  clone_row, edit_row, update_form, save_form, scan_tabs, check_fields,
  click, select, wait, wait_for_page_load, process_deployment, reorder`

This snapshot intentionally focuses on behavior contracts and “where logic lives”.
When troubleshooting issues: search in the relevant file/mixin listed above.
