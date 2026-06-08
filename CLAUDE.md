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
ai/action_fixer.py   2298  — Deterministic post-processing/repair of AI plans
automation/core.py    853  — Playwright dispatcher, modal safety nets
automation/navigator.py 2132 — Menu/tab navigation, PVE accordion expansion
automation/form_handler.py 8075 — Main field filler (LARGEST FILE)
automation/table_handler.py 1384 — Table checkbox/edit/clone/reorder
automation/smart_tester.py  2410 — CSV fuzz campaign, popup classification
automation/data_handler.py   187  — CSV manipulation, download/upload wiring
```

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

---

## CSV Test Cases: downloads/Testcasesmokelive.csv
Features covered: RBE, Offer, PVE, Gacha, Currency, Fight Card, Fight Card Slots, Localization, Showdown, Faction Feud, Grabbag, SuperStar, Faction Boss, Moment Poster, Perk/Perk Slot, Boost

All create/clone cases contain `hãy tự generate một ID duy nhất bắt đầu bằng <prefix>` — handled by `_inject_generated_ids`.