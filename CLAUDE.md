# AutoGameOps — Codebase Reference

## Overview
Streamlit + Ollama LLM + Playwright QA automation for "The Brick" game ops web UI.
- Converts Vietnamese/English QA commands → JSON action plan → Playwright execution
- Browser: CDP attach to existing Chromium at `http://localhost:9222`
- LLM: Ollama at `http://localhost:11434/api/generate`

---

## File Map & Line Counts
```
ai/brain.py           784  — LLM pipelines, JSON cleanup, ID injection
ai/prompts.py        1017  — Prompt templates, action-name instruction set
automation/core.py    853  — Playwright dispatcher, modal safety nets
automation/data_handler.py   187  — CSV manipulation, download/upload wiring
```

## REFACTOR (2026-06): monoliths split into backward-compatible packages
The 5 largest files were split into packages. Each package's `__init__.py`
re-exports the SAME mixin/symbol the old file did, so all imports in core.py /
brain.py are UNCHANGED. Method resolution via `self` still works across the
sub-mixins once composed into `BrickAutomation`.

```
ai/action_fixer/          (was action_fixer.py)  — fix_action_plan still in __init__.py
  _constants.py           DEPLOYMENT_KEYWORDS / NAVIGATION_PATH_MAP / ACTION_NAME_MAP / VALID_ACTIONS ...
  navigation_fixers.py    _resolve_navigation_paths, _merge_navigate_steps, _remove_invalid_navigate_to_tabs, _inject_missing_initial_navigate
  deployment_fixers.py    _auto_infer_deployment_options, _merge_process_deployment_steps, _strip_invalid_deploy_options, _inject_missing_checkbox_before_download
  clone_fixers.py         _inject_missing_clone_row, _extract_clone_modal_fields, _inject_clone_save, _fix_pve_clone_chapter, _fix_rbe_clone_field_name, _remove_click_after_clone_save, _remove_download_before_edit_row, _fix_id_only_update_to_edit_row
  form_fixers.py          _merge_consecutive_update_save, _merge_pve_css_update_steps
  __init__.py             fix_action_plan (orchestrator) + re-exports

automation/form_handler/  (was form_handler.py)  — FormHandlerMixin composed in __init__.py
  form_core.py            FormCoreMixin       — _smart_update_form (main fill loop; delegates RBE/PVE Contest-Superstar to special_panels), _main_form_scope, _safe_press_escape, _clean_key
  field_finder.py         FieldFinderMixin    — _find_input_element, _try_section_aware_search, _find_field_in_section
  field_filler.py         FieldFillerMixin    — _fill_element_smartly, toggle/radio/inline-edit
  dropdown_handler.py     DropdownHandlerMixin— _handle_js_dropdown, select2 + vue-multiselect helpers
  datetime_handler.py     DateTimeHandlerMixin— schedule/flatpickr datetime fill + format auto-fix
  special_panels.py       SpecialPanelsMixin  — SSGroup helpers + _handle_rbe_contest_superstar (RBE: Defining-Schedules Start/End clamp to parent RBE range) + _handle_pve_contest_superstar (PVE: toggle opens Normal/Hard/Hell panels, fill SS Node1/SoftCurrency/RBE). Both mutate `data` in place, called from _smart_update_form before the main loop.
  form_save.py            FormSaveMixin       — _save_form, _wait_after_save, error-popup + confirm dismissal, close_popup
  tab_scanner.py          TabScannerMixin     — scan_all_tabs, check_fields_in_tabs, _switch_to_tab, _get_field_current_value

automation/navigator/     (was navigator.py)  — NavigatorMixin composed in __init__.py
  navigator_core.py       NavigatorCoreMixin  — smart_navigate, _smart_navigate_path, sidebar nav, _wait_for_long_loading, _is_sidebar_item, _handle_locked_item_popup, _safe_compile
  click_handler.py        ClickHandlerMixin   — smart_click (multi-strategy)
  deployment.py           DeploymentMixin     — process_deployment
  pve_navigation.py       PveNavigationMixin  — _try_expand_pve_section

automation/table_handler/ (was table_handler.py) — TableHandlerMixin composed in __init__.py
  table_filter.py         TableFilterMixin    — _auto_filter_data, _perform_table_filter, _find_data_table, wait_for_table_data, _ensure_liveoptest_items_visible
  table_checkbox.py       TableCheckboxMixin  — handle_checkbox, _safe_check, _find_and_tick
  table_rows.py           TableRowsMixin      — _click_icon_in_row (edit/clone)
  table_reorder.py        TableReorderMixin   — drag_to_reorder

automation/smart_tester/  (was smart_tester.py) — SmartTesterMixin composed in __init__.py
  tester_core.py          SmartTesterCoreMixin— smart_test_cycle, _smart_test_rbe_csv, _generate_fuzzed_data, _run_rbe_fuzz_campaign, _test_generic_csv
  upload_handler.py       UploadHandlerMixin  — handle_upload, _upload_fast/_upload_fuzz_fast, overwrite confirm
  popup_classifier.py     PopupClassifierMixin— _scan_for_result_popup, _classify_popup_message, _ensure_popup_closed
  fuzz_generator.py       RBESmartTester / RBEFuzzGenerator / GenericCSVFuzzer (standalone classes, NOT mixins; re-exported)
```
**NOTE:** The per-method `Line` numbers in the detail tables below are LEGACY
(pre-refactor, relative to the old monolith). Method names/purposes are still
valid; find a method by name with grep across the package dir.

---

## ai/brain.py — Key Functions

| Function | Purpose |
|---|---|
| `parse_command_to_json(user_command, use_fast_mode, context_plan, base_command)` | Main entry: converts command → JSON action plan. Entry point for all AI calls. |
| `_inject_generated_ids(user_command)` | **Preprocessing**: replaces `hãy tự generate ... bắt đầu bằng <prefix>` with `<prefix>_<timestamp>`. Called at start of parse_command_to_json. |
| `single_model_pipeline(user_command)` | Fast mode: single Qwen call → plan |
| `dual_model_pipeline(user_command)` | Careful mode: DeepSeek reasoning → Qwen JSON formatting |
| `patch_model_pipeline(user_command, base_command, base_plan)` | Patches existing plan for modified scenario |
| `detect_complexity(user_command)` | Auto-escalates to Careful mode if command is complex |
| `call_ollama(model_name, prompt, ...)` | Low-level Ollama API call with num_predict=500 for reasoning phase |
| `clean_json_string(text)` | Salvages malformed LLM JSON (strips fences, fixes braces, removes comments) |
| `load_scenarios() / save_scenario() / delete_scenarios()` | Scenario persistence in scenarios.json |

**Critical**: No fast-path/hardcoded bypass functions exist. All commands go through AI.

---

## ai/action_fixer.py — Key Functions

| Function | Purpose |
|---|---|
| `fix_action_plan(plan, user_command)` | Main entry: applies all fixers in sequence |
| `_resolve_navigation_paths(plan)` | Resolves nav string → proper path list |
| `_merge_navigate_steps(plan)` | Merges consecutive navigate steps |
| `_auto_infer_deployment_options(plan)` | Detects what to deploy |
| `_merge_process_deployment_steps(plan)` | Merges checkbox + process steps |
| `_inject_missing_clone_row(plan, user_command)` | Ensures clone_row exists before modal fields |
| `_extract_clone_modal_fields(user_command)` | Parses which fields go in clone modal vs post-clone edit |
| `_merge_consecutive_update_save(plan)` | Merges update_form→save_form pairs |
| `_inject_clone_save(plan, user_command)` | Injects `save_form(mode="clone")` after clone modal fields |

---

## automation/core.py — BrickAutomation Class

`BrickAutomation` inherits from all Mixins:
```python
class BrickAutomation(
    NavigatorMixin, FormHandlerMixin, TableHandlerMixin,
    DataHandlerMixin, SmartTesterMixin
)
```

| Method | Purpose |
|---|---|
| `execute_action(action_plan)` | Main dispatcher — iterates plan steps |
| `_execute_with_playwright(action_plan)` | Inner loop: calls correct mixin per action type |
| `get_existing_page(p)` | CDP connect to existing browser page |
| `_ensure_swal2_clone_confirmation_yes(page)` | Auto-accepts SweetAlert2 clone confirm |
| `_ensure_rbe_are_you_sure_closed(page)` | Dismisses RBE "Are you sure" Bootstrap modal |
| `close_popup(page)` | Generic popup/toast closer |

**Valid action names** (from VALID_ACTIONS set in core.py):
`navigate, checkbox, download, upload, manipulate_csv, smart_test_cycle, clone_row, edit_row, update_form, save_form, scan_tabs, check_fields, click, select, wait, wait_for_page_load, process_deployment, reorder`

**Action dispatch** (line ~501):
- `update_form` → `_smart_update_form(page, popup_data)` where `popup_data = step.get("data", {})`
- `clone_row` / `edit_row` → `_click_icon_in_row(page, tgt, action_type)`
- Before click/select/update_form/save_form: auto-dismiss SweetAlert2 + RBE confirm modals

---

## automation/form_handler.py — FormHandlerMixin (~8075 lines)

### Top-Level Entry
| Method | Line | Purpose |
|---|---|---|
| `_smart_update_form(page, data)` | 39 | **Main field filler** — iterates `data.items()`, fills each field |

### Special Cases in `_smart_update_form`
1. **Defining Schedules clamp** (~line 101): Clamps CSS start/end time to parent RBE schedule range when Defining Schedules modal is open
2. **Contest Superstar** (~line 186): PVE-only special case. **Trigger**: `any("contest superstar" in str(k).lower() for k in data.keys())`. Handles toggle + Normal/Hard/Hell panels. Only triggers when data has explicit "Contest Superstar" key.
3. **Main fill loop** (~line 1543): iterates remaining keys, calls `_find_input_element` → `_fill_element_smartly`

### Field Finders
| Method | Line | Purpose |
|---|---|---|
| `_find_input_element(page, label_text)` | 5097 | Main field locator — label text → element. Multi-strategy |
| `_try_section_aware_search(page, label_text)` | 6093 | Section-scoped field search |
| `_find_field_in_section(page, section_name, field_name)` | 6121 | Find field within named section |
| `_main_form_scope(page)` | 5013 | Returns main form scope (excludes modals) |

### Field Fillers
| Method | Line | Purpose |
|---|---|---|
| `_fill_element_smartly(page, element, value)` | 6726 | Routes to correct fill strategy by element type |
| `_handle_js_dropdown(page, container, value, lib_type)` | 7225 | Fills chosen/multiselect/select2 dropdowns |
| `_fill_vue_multiselect(page, combobox_scope, search_value, ...)` | 7878 | Fills Vue multiselect |
| `_open_vue_multiselect(page, wrapper_or_input, timeout_ms)` | 7775 | Opens Vue multiselect reliably |
| `_fill_schedule_datetime_smart(page, label_text, values)` | 2880 | Smart datetime fill |
| `_fill_multiple_datetime_fields(page, label_text, values)` | 2592 | Fills Start+End datetime pair |
| `_fill_single_datetime_input(page, inp, val, idx)` | 3648 | Fills a single flatpickr input |
| `_try_set_form_toggle_by_label(page, label_text, value)` | 5031 | Flips boolean toggle/checkbox |
| `_try_click_radio_by_label(page, label_text, value)` | 3745 | Selects radio button |
| `_handle_inline_edit_field(page, label_text, value)` | 6351 | Handles fields with an Edit button |
| `_try_select_radio_by_value(page, label_text, target_value)` | 3400 | Radio by value attribute |

### Select2 Special Helpers
| Method | Line | Purpose |
|---|---|---|
| `_try_set_select2_option_by_option_text(page, option_text)` | 1985 | Sets any select2 by text |
| `_try_set_select2_multiselect_by_placeholder(page, placeholder, value)` | 7167 | Multiselect select2 by placeholder |
| `_find_custom_dropdown_wrapper(hidden_select)` | 6627 | Finds select2/chosen/multiselect wrapper for a hidden `<select>` |

### SSGroup Helpers
| Method | Line | Purpose |
|---|---|---|
| `_try_set_ssgroup_id_by_multiselect_search_input(page, ssgroup_id)` | 2090 | SSGroup via `#searchSSGroupId` input |
| `_try_set_ssgroup_id_by_ssdb_search_placeholder(page, ssgroup_id)` | 2321 | SSGroup via SSDB search placeholder |

### Save & Validation
| Method | Line | Purpose |
|---|---|---|
| `_save_form(page, mode)` | 3831 | Clicks save, captures XHR/fetch response, auto-fixes errors |
| `_wait_after_save(page, network_error)` | 4277 | Post-save wait + error handling |
| `_detect_ui_error_popup(page)` | 4447 | Detects error toast/popup after save |
| `_dismiss_are_you_sure_confirmations(page)` | 4490 | Bootstrap confirm dismissal |
| `_auto_fix_datetime_on_page(page, error_msg)` | 4580 | Auto-fixes datetime format errors |

### Tab Scanning
| Method | Line | Purpose |
|---|---|---|
| `scan_all_tabs(page, data_dict)` | 4696 | Iterates sidebar tabs to find and fill fields |
| `check_fields_in_tabs(page, tabs_dict)` | 4804 | Verifies field values across tabs |
| `_switch_to_tab(page, tab_name)` | 8045 | Switches to named tab |
| `_get_field_current_value(page, field_name)` | 4919 | Reads current value of a field |

---

## `_handle_js_dropdown` — Critical Implementation Details

**Flow for select2 (line 7226+)**:
1. `container.click(force=True)` — opens dropdown (safe: container is inside modal-dialog)
2. Wait loop (JS evaluate): counts `.select2-results__option` with `offsetParent !== null`
3. If not loaded: tries `jQuery('.modal.in select, .modal.show select').each(... select2('open') ...)`
4. **Direct-match JS** (line 7454): finds option, calls `selectOpt()`:
   - **Clone modal detected** (`/Clone/i.test(modal.innerText)`): uses jQuery programmatic — `jQuery(opt).data('data').id` → append option → `$sel.val(optId).trigger('change')` — NO DOM click to avoid Bootstrap dismiss
   - **Regular form**: `opt.click()` — Select2 handles numeric ID internally
5. If not matched: opens search box, types value, waits 3.5s, presses Enter
6. If `clicked_exact`: `page.keyboard.press("Tab")` + return True
7. Else: `page.keyboard.press("Tab")` + return True

**Clone modal detection JS pattern**:
```javascript
const modalEl = document.querySelector('.modal.show, .modal.in');
const inCloneModal = !!(modalEl && /Clone/i.test(modalEl.innerText || modalEl.textContent || ''));
```

**Why programmatic in clone modal**: `opt.click()` fires a body-level click event. Bootstrap's modal dismiss handler sees this as "click outside `.modal-dialog`" → dismisses modal before Gate value is saved.

**Why NO Python-side select2('close')**: Both JS paths handle close themselves (click path: Select2 auto-closes; programmatic path: `$sel.select2('close')` in JS). Python calling close() races against Select2's own event handler.

---

## automation/navigator.py — NavigatorMixin (~2132 lines)

| Method | Line | Purpose |
|---|---|---|
| `smart_navigate(page, target)` | 16 | Main nav: handles string/list targets |
| `_smart_navigate_path(page, path_list)` | 50 | Navigates a path list step by step |
| `smart_click(page, target_text)` | 1015 | Multi-strategy element click |
| `_try_expand_pve_section(page, target_text)` | 705 | Expands PVE accordion via aria-controls |
| `process_deployment(page, options)` | 495 | Clicks logo + checkboxes + Process |
| `_is_sidebar_item(page, text)` | 2116 | Detects if text is a sidebar nav item |
| `_wait_for_long_loading(page)` | 1999 | Waits for spinner/skeleton to disappear |
| `_click_sidebar_nav_by_id(page, nav_id, label)` | 684 | Clicks sidebar nav by DOM ID |

---

## automation/table_handler.py — TableHandlerMixin (~1384 lines)

| Method | Line | Purpose |
|---|---|---|
| `handle_checkbox(page, target_col, value)` | 50 | Select rows by col/value, supports random_N |
| `_click_icon_in_row(page, target_text, action_type)` | 365 | Clicks edit/clone icon in matching row. Handles `edit_row`/`clone_row` actions |
| `_auto_filter_data(page, keyword)` | 925 | Filters table by keyword in search input |
| `wait_for_table_data(page, timeout)` | 948 | Waits for table rows to appear |
| `_perform_table_filter(page, col_name, value)` | 979 | Filters table by column header |
| `drag_to_reorder(page, target, position, before, after)` | 1027 | Drag-and-drop row reorder |

---

## automation/smart_tester.py — SmartTesterMixin (~2410 lines)

| Method | Line | Purpose |
|---|---|---|
| `smart_test_cycle(page, file_name)` | 18 | Main: negative fuzz → valid import |
| `_smart_test_rbe_csv(page, file_name)` | 59 | RBE-specific fuzz campaign |
| `_generate_fuzzed_data(original_df)` | 116 | Creates invalid CSV mutations |
| `handle_upload(page, target_btn_name, file_name)` | 1833 | Uploads CSV file |
| `_scan_for_result_popup(page)` | 1067 | Detects success/error popup after upload |
| `_classify_popup_message(text)` | 449 | Classifies popup as success/error/warning |

Classes: `RBESmartTester` (line 2121), `RBEFuzzGenerator` (line 2248), `GenericCSVFuzzer` (line 2325)

---

## automation/data_handler.py — DataHandlerMixin (~187 lines)

| Method | Line | Purpose |
|---|---|---|
| `_process_csv_manipulation(filename, operation, data_instruction)` | 11 | Main CSV manipulate dispatcher |
| `_modify_csv(fp, col, val)` | 140 | Modifies a CSV column value |
| `_find_download_trigger(page, specific_name)` | 158 | Finds download button by name |

---

## Known Patterns & Gotchas

### Select2 AJAX in Clone Modal
- **Problem**: `opt.click()` in JS body → Bootstrap dismiss handler fires → modal closes
- **Fix**: Detect `inCloneModal` via `/Clone/i.test(modal.innerText)` → jQuery programmatic assignment
- **For numeric IDs** (e.g. Point Currency): `jQuery(opt).data('data').id` gives numeric value; fall back to parsing `select2-*-result-*-{id}` from option's `id` attribute

### Contest Superstar Special Case
- **Trigger**: `any("contest superstar" in str(k).lower() for k in data.keys())`
- Only triggers for PVE CSS test case where AI generates `"Contest Superstar": "on"` key
- RBE data has no such key → NOT triggered
- Original broken condition also checked `"node 1" in str(k).lower()` — caused false triggers

### ID Generation for Test Cases
- Pattern in CSV: `hãy tự generate một ID duy nhất bắt đầu bằng <prefix>`
- `_inject_generated_ids(user_command)` in brain.py preprocesses this → `<prefix>_<timestamp>` before AI sees it
- Called at start of `parse_command_to_json`

### `_smart_update_form` does NOT return a count
- Signature: `def _smart_update_form(self, page, data):`
- Calls in `scan_all_tabs` with `strict_mode=True` kwarg will fail silently (kwargs ignored by Python)

### Smoke Test ID Memory
- `smoke_last_created_id_by_feature[feature]` in app.py tracks last created ID per feature
- Prevents "random edit" drift when CSV test cases reference the previously created row

### Upload Confirm Buttons Must Be Dialog-Scoped
- In `smart_tester/upload_handler.py` `_upload_fuzz_fast`, the post-upload "confirm" loop MUST scope selectors to `.modal.show/.modal.in/.swal2-popup` — a bare `button:has-text('Import')` also matches the PAGE-LEVEL Import CSV trigger and re-clicking it reopens the OS file chooser → native dialog BLOCKS the run (gacha pool bug)
- A `page.on("filechooser", lambda fc: fc.set_files([]))` guard (removed in `finally`) swallows any stray chooser. Never leave the listener registered — it conflicts with the next `expect_file_chooser`

### Golden Plan Cache (ai/plan_cache.py)
- Smoke runner caches a case's action plan after a full-PASS run and replays it next time, **skipping the LLM** (kills ~30-40% non-determinism). Store: `config/golden_plans.json`
- Key = `golden_key(feature, RAW testcase cell)` (whitespace-normalized; stable since CSV is fixed). Use the RAW `testcase`, NOT `case_command` (which has concrete IDs injected)
- Only dynamic IDs are tokenized: `generated_unique_id`→`{{UNIQUE_ID}}`, `last_created_id`→`{{LAST_ID}}` (JSON-string replace, longest-first). Static data cached verbatim
- `get_golden_plan` returns None if a needed placeholder lacks a value → forces AI fallback. Self-heal: golden replay FAIL/CRASH → `invalidate` + AI retry in same run (app.py smoke loop). WARNING keeps golden
- UI: `smoke_use_golden` checkbox (default on) near the Smoke run button; new dynamic value types need a new placeholder or golden will pin a stale value

---

## CSV Test Cases: downloads/Testcasesmokelive.csv
Features covered: RBE, Offer, PVE, Gacha, Currency, Fight Card, Fight Card Slots, Localization, Showdown, Faction Feud, Grabbag, SuperStar, Faction Boss, Moment Poster, Perk/Perk Slot, Boost

All create/clone cases contain `hãy tự generate một ID duy nhất bắt đầu bằng <prefix>` — handled by `_inject_generated_ids`.

---

## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root (created lazily, not yet present). See `docs/agents/domain.md`.