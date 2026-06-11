# ai/action_fixer/__init__.py
# Backward-compatible: fix_action_plan orchestrator + re-exported fixers.
from ._constants import (
    DEPLOYMENT_KEYWORDS,
    PAGE_TAB_NAMES,
    NAVIGATION_PATH_MAP,
    ACTION_NAME_MAP,
    VALID_ACTIONS,
    _VALID_DEPLOY_OPTIONS,
)
from .navigation_fixers import (
    _inject_missing_initial_navigate,
    _resolve_navigation_paths,
    _remove_invalid_navigate_to_tabs,
    _merge_navigate_steps,
)
from .deployment_fixers import (
    _strip_invalid_deploy_options,
    _inject_missing_checkbox_before_download,
    _auto_infer_deployment_options,
    _merge_process_deployment_steps,
    _inject_missing_final_deployment,
)
from .clone_fixers import (
    _remove_download_before_edit_row,
    _remove_edit_row_before_checkbox,
    _fix_pve_clone_chapter,
    _fix_rbe_clone_field_name,
    _fix_clone_modal_new_prefix_fields,
    _fix_id_only_update_to_edit_row,
    _remove_click_after_clone_save,
    _inject_missing_clone_row,
    _extract_clone_modal_fields,
    _inject_clone_save,
)
from .form_fixers import (
    _merge_consecutive_update_save,
    _merge_pve_css_update_steps,
    _fix_rbe_type_modal_continue,
    _fix_offer_filter_field,
)


def fix_action_plan(plan, user_command=""):
    """
    Post-process AI output: Fix invalid action names and field names.
    This is deterministic and 100% reliable regardless of what AI generates.

    Args:
        plan: The AI-generated action plan (list of dicts)
        user_command: The original user command string (used for clone detection)
    """
    if not plan or not isinstance(plan, list):
        return plan

    fixed_plan = []
    last_filename = None  # Track filename for reuse

    # Pre-parse user command for uncheck patterns
    # e.g. "Bỏ chọn checkbox Excel" → uncheck_targets = ["excel"]
    import re as _re

    uncheck_targets = set()
    uncheck_patterns = [
        r"bỏ\s*chọn\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"bo\s*chon\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"uncheck\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"untick\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"deselect\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
        r"bỏ\s*tick\s*(?:checkbox\s*)?(\w[\w\s]*?)(?:\s*(?:->|,)|(?:\s+(?:rồi|và|then|and|process|save)\b)|\s*$)",
    ]
    cmd_lower = user_command.lower()
    for pattern in uncheck_patterns:
        for m in _re.finditer(pattern, cmd_lower, _re.IGNORECASE):
            uncheck_targets.add(m.group(1).strip().lower())

    # PVE special: "contain LTPVE bất kỳ" / "chứa LTPVE bất kỳ"
    # Want edit_row target = "LTPVE" (substring match), not RANDOM.
    contain_token = None
    try:
        m_contain = _re.search(
            r"(?:contain|chứa)\s+([A-Za-z0-9_]+)\s+(?:bất\s*kỳ|bat\s*ky|any)",
            cmd_lower,
            _re.IGNORECASE,
        )
        if m_contain:
            contain_token = m_contain.group(1).strip()
            print(f"   🔍 Detected contain-token from command: {contain_token}")
    except Exception:
        contain_token = None

    if uncheck_targets:
        print(f"   🔍 Detected uncheck targets from command: {uncheck_targets}")

    for step in plan:
        if not isinstance(step, dict):
            continue

        action = step.get("action", "")

        # ============================================================
        # STEP 1: Fix action name (save original for uncheck detection)
        # ============================================================
        step["_original_action"] = action  # Save for uncheck detection
        if action in ACTION_NAME_MAP:
            old_action = action
            action = ACTION_NAME_MAP[action]
            step["action"] = action
            print(f"   🔧 AUTO-FIX: '{old_action}' → '{action}'")

        # ============================================================
        # STEP 2: Fix field names based on action type
        # ============================================================

        if action == "checkbox":
            # ============================================================
            # DETECT UI FILTER/TOGGLE CHECKBOXES (not table row selection)
            # If target looks like a UI label ("Hide X", "Show X") or matches
            # an uncheck target from the command, convert to update_form.
            # ============================================================
            _cb_target_raw = str(step.get("target", step.get("label", step.get("field", ""))))
            _cb_target_lower = _cb_target_raw.lower().strip()
            _is_ui_filter = False

            # Signal 1: target starts with hide/show/enable/disable (UI toggle labels)
            _ui_filter_prefixes = ("hide ", "show ", "enable ", "disable ", "hiển thị ", "ẩn ")
            if any(_cb_target_lower.startswith(p) for p in _ui_filter_prefixes):
                _is_ui_filter = True

            # Signal 2: target matches any uncheck_target from the parsed command
            if not _is_ui_filter and uncheck_targets:
                for _ut in uncheck_targets:
                    if _ut in _cb_target_lower or _cb_target_lower in _ut:
                        _is_ui_filter = True
                        break

            if _is_ui_filter:
                # Convert to update_form with "{Label} checkbox": "false"/"true"
                _uncheck_intent = (
                    any(kw in cmd_lower for kw in ["bỏ chọn", "bo chon", "uncheck", "untick", "bỏ tick", "deselect"])
                    and any(_ut in _cb_target_lower or _cb_target_lower in _ut for _ut in uncheck_targets)
                ) or any(kw in str(step.get("value", "")).lower() for kw in ["false", "off", "uncheck"])
                _toggle_value = "false" if _uncheck_intent else "true"
                _label_key = f"{_cb_target_raw} checkbox"
                new_step = {"action": "update_form", "data": {_label_key: _toggle_value}}
                print(f"   🔧 AUTO-FIX: checkbox('{_cb_target_raw}') → update_form({{'{_label_key}': '{_toggle_value}'}})")
                fixed_plan.append(new_step)
                continue

            # ============================================================
            # DETECT DEPLOYMENT-CONTEXT CHECKBOXES
            # If the checkbox target/value/field matches a deployment keyword,
            # keep it as-is (don't default to random_1) so the merge step
            # can pick it up later for process_deployment.
            # ============================================================
            target_val = str(step.get("target", "")).lower().strip()
            value_val = str(step.get("value", "")).lower().strip()
            field_val = str(step.get("field", "")).lower().strip()
            label_val = str(step.get("label", "")).lower().strip()
            checkbox_val = str(step.get("checkbox", "")).lower().strip()

            # Check if any field matches deployment keywords
            is_deployment_checkbox = False
            deployment_opt_name = None
            for check_val, check_key in [
                (checkbox_val, "checkbox"),
                (field_val, "field"),
                (label_val, "label"),
                (target_val, "target"),
                (value_val, "value"),
            ]:
                if check_val:
                    for keyword in DEPLOYMENT_KEYWORDS:
                        if keyword in check_val or check_val in keyword:
                            is_deployment_checkbox = True
                            deployment_opt_name = step.get(check_key, check_val)
                            break
                    if is_deployment_checkbox:
                        break

            # Detect uncheck intent from original action name, value, target, or any field
            original_action = step.get("_original_action", "")
            all_text = " ".join(
                [
                    original_action,
                    value_val,
                    label_val,
                    target_val,
                    field_val,
                    checkbox_val,
                    str(step.get("mode", "")),
                ]
            ).lower()
            is_uncheck = any(
                kw in all_text
                for kw in [
                    "uncheck",
                    "bỏ chọn",
                    "bo chon",
                    "unselect",
                    "deselect",
                    "untick",
                    "bỏ tick",
                    "remove",
                ]
            )

            # Also check if this target matches user command's uncheck targets
            if not is_uncheck and uncheck_targets and deployment_opt_name:
                opt_lower = str(deployment_opt_name).lower().strip()
                if opt_lower in uncheck_targets or any(
                    t in opt_lower or opt_lower in t for t in uncheck_targets
                ):
                    is_uncheck = True
                    print(
                        f"   🔍 Detected uncheck from command context: '{deployment_opt_name}'"
                    )

            if is_deployment_checkbox:
                # Keep deployment checkbox info intact for merge step
                if not step.get("_deployment_opt"):
                    step["_deployment_opt"] = (
                        deployment_opt_name or target_val or value_val
                    )
                if is_uncheck:
                    step["_uncheck"] = True
                # Don't apply random_1 defaults
            else:
                # Normal table checkbox: apply defaults
                # Fix: {count: 2} or {number: 2} → {target: "ID", value: "random_2"}
                if "count" in step:
                    step["value"] = f"random_{step.pop('count')}"
                elif "number" in step:
                    step["value"] = f"random_{step.pop('number')}"
                if "target" not in step:
                    step["target"] = "ID"
                if "value" not in step and "label" in step:
                    step["value"] = step.pop("label")
                # Fix: value rỗng → default random_1
                if not step.get("value") or str(step.get("value")).strip() == "":
                    step["value"] = "random_1"
                    print("   🔧 AUTO-FIX: checkbox value rỗng → random_1")

        elif action == "download":
            # Fix: {filename: "x.csv"} → {target: "Export CSV", value: "x.csv"}
            if "filename" in step:
                step["value"] = step.pop("filename")
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "target" not in step:
                step["target"] = "Export CSV"
            # Track filename for reuse
            if step.get("value"):
                last_filename = step["value"]

        elif action == "upload":
            # Fix: {filename: "x.csv"} → {target: "Import CSV", value: "x.csv"}
            if "filename" in step:
                step["value"] = step.pop("filename")
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "target" not in step:
                step["target"] = "Import CSV"
            # Reuse filename if empty
            if not step.get("value") and last_filename:
                step["value"] = last_filename
                print(f"   🔧 AUTO-FIX: Reused filename '{last_filename}' for upload")
            # Drop/fix spurious upload steps where value is not a real .csv filename.
            # AI often treats the testcase phrase as a filename:
            # e.g. "Import the Gacha Weight CSV" → value="Gacha Weight CSV" (no extension).
            # Real filenames always end with ".csv".
            _upload_val = str(step.get("value", "")).strip()
            if _upload_val and not _upload_val.lower().endswith(".csv"):
                if last_filename:
                    # For download→upload patterns (e.g. RBE tasks), reuse the
                    # preceding download filename instead of the AI-invented name.
                    print(f"   🔧 AUTO-FIX: upload value '{_upload_val}' not a .csv → reused last filename '{last_filename}'")
                    step["value"] = last_filename
                else:
                    # No prior download to reuse — this is a fully spurious step, drop it.
                    print(f"   🔧 FILTER: Dropping spurious upload — value '{_upload_val}' is not a .csv filename")
                    continue

        elif action == "smart_test_cycle":
            # Fix: {file: "x.csv"} → {value: "x.csv"}
            if "file" in step and "value" not in step:
                step["value"] = step.pop("file")
            if "filename" in step and "value" not in step:
                step["value"] = step.pop("filename")
            # Reuse filename if empty
            if not step.get("value") and last_filename:
                step["value"] = last_filename
                print(
                    f"   🔧 AUTO-FIX: Reused filename '{last_filename}' for smart_test_cycle"
                )
            # Track for next step
            if step.get("value"):
                last_filename = step["value"]

        elif action == "process_deployment":
            # Fix: {target: "The Brick"} → just process_deployment
            if "target" in step and step["target"] in (
                "The Brick",
                "logo The Brick",
                "logo",
            ):
                step.pop("target")
            if "options" not in step:
                step["options"] = []
            if "label" in step:
                # click_button label="Process" → already handled by process_deployment
                step.pop("label", None)

        elif action == "click":
            # Fix: {label: "X"} → {target: "X"}
            if "label" in step and "target" not in step:
                step["target"] = step.pop("label")

            # 🆕 Validate: Skip click actions with no target
            if not step.get("target") or not str(step.get("target")).strip():
                print(f"   🔧 FILTER: Skipping click action with empty target")
                continue

            # 🆕 DETECT: click("Save") / click("Save & Continue") → save_form
            target_lower = str(step.get("target", "")).lower().strip()
            if target_lower in ("save", "save button", "nút save", "bấm save", "lưu"):
                step["action"] = "save_form"
                step["mode"] = "save"
                step.pop("target", None)
                action = "save_form"
                print(f"   🔧 AUTO-FIX: click('Save') → save_form(mode=save)")
            elif target_lower in (
                "save & continue",
                "save and continue",
                "save continue",
            ):
                step["action"] = "save_form"
                step["mode"] = "continue"
                step.pop("target", None)
                action = "save_form"
                print(
                    f"   🔧 AUTO-FIX: click('Save & Continue') → save_form(mode=continue)"
                )

            # 🆕 DETECT: click("The Brick"/"logo") → process_deployment
            elif any(
                keyword in target_lower
                for keyword in [
                    "brick",
                    "logo",
                    "the brick",
                    "brick logo",
                    "logo the brick",
                ]
            ):
                # Convert to process_deployment
                old_target = step.get("target")
                step["action"] = "process_deployment"
                step.pop("target", None)  # Remove target field
                step["options"] = step.get("options", [])  # Ensure options field exists
                print(f"   🔧 AUTO-FIX: click('{old_target}') → process_deployment")
                action = "process_deployment"  # Update action variable for subsequent processing

        elif action in ("edit_row", "clone_row"):
            # Normalize random/any/bất kỳ targets to RANDOM sentinel
            _RANDOM_TARGETS = {
                "random",
                "any",
                "bất kỳ",
                "bat ky",
                "any row",
                "first",
                "một dòng bất kỳ",
                "bất kỳ dòng",
                "random_1",
                "random row",
                "any id",
                "bất kỳ id",
                "id bất kỳ",
                # AI-generated placeholders when "vừa clone/tạo" appears without a concrete ID
                "cloned_item_id",
                "last_clone_id",
                "last_cloned_id",
                "recently_cloned_id",
                "cloned_id",
                "last_created_id",
                "vua_clone_id",
                "new_item_id",
            }
            tgt = str(step.get("target", "")).lower().strip()

            # [CRITICAL FIX] EventID dropdown vs table row confusion after PVP:
            # Sometimes AI generates: click('PVP') -> edit_row('VS_Tournament_...')
            # But VS_Tournament_* is an Event ID (belongs to update_form), not a table row ID.
            # Turning this step into a no-op prevents crash: "Không tìm thấy dòng 'VS_Tournament...'"
            pvp_in_cmd = "pvp" in str(user_command).lower()
            event_id_like_vs_tournament = bool(
                _re.match(r"^vs_tournament_", tgt, _re.IGNORECASE)
            )
            if pvp_in_cmd and event_id_like_vs_tournament:
                old_target = step.get("target")
                step["action"] = "wait"
                step.pop("target", None)
                print(
                    f"   🔧 AUTO-FIX: Converted edit_row('{old_target}') → wait() because it's an Event ID after PVP"
                )
                # If command also has "vừa clone/tạo", AI confused the table-row edit with the Event ID.
                # Inject edit_row("RANDOM") so the cloned row gets opened before this wait.
                _vua_re = _re.compile(r"v[uưừữ]a\s+(clone|tạo)", _re.IGNORECASE)
                if _vua_re.search(str(user_command)):
                    fixed_plan.append({"action": "edit_row", "target": "RANDOM"})
                    print(
                        f"   🔧 AUTO-FIX: Injected edit_row('RANDOM') — 'vừa clone' in command but AI confused target with Event ID"
                    )
            # Exact match OR contains "bất kỳ"/"random" pattern
            # Handles cases like "một Superstar bất kỳ", "Superstar bất kỳ", "random superstar"
            is_random_target = (
                tgt in _RANDOM_TARGETS
                or tgt == ""
                or "bất kỳ" in tgt
                or "bat ky" in tgt
                or ("random" in tgt and tgt != "random_1")
            )
            if is_random_target:
                # If user asked: "contain <TOKEN> bất kỳ/chứa <TOKEN> bất kỳ"
                # we DON'T want to pick RANDOM row; we want deterministic substring match.
                if contain_token:
                    step["target"] = contain_token
                    print(
                        f"   🔧 AUTO-FIX: {action}('{tgt or 'empty'}') → {action}('{contain_token}') (contain-token mode)"
                    )
                else:
                    step["target"] = "RANDOM"
                    print(
                        f"   🔧 AUTO-FIX: {action}('{tgt or 'empty'}') → {action}('RANDOM') (random row mode)"
                    )

            # AI sometimes uses navigation page name as the clone/edit target
            # (e.g. clone_row(target="Offer Section") when it should be RANDOM).
            # Row IDs are never plain page-nav names → safe to normalize.
            elif tgt and step.get("target") not in ("RANDOM", ""):
                _nav_page_names: set = set()
                for _prev in fixed_plan:
                    if _prev.get("action") == "navigate":
                        _path = _prev.get("path", [])
                        if isinstance(_path, list):
                            _nav_page_names.update(s.lower().strip() for s in _path)
                        elif isinstance(_path, str):
                            _nav_page_names.add(_path.lower().strip())
                if tgt in _nav_page_names:
                    old_tgt = step.get("target")
                    step["target"] = contain_token if contain_token else "RANDOM"
                    print(
                        f"   🔧 AUTO-FIX: {action}('{old_tgt}') target is navigation page name → {step['target']}"
                    )

        elif action == "navigate":
            # Fix: {menu: [...]} → {path: [...]}
            if "menu" in step and "path" not in step:
                step["path"] = step.pop("menu")

        elif action == "update_form":
            # ============================================================
            # FIX RADIO FIELDS: AI sometimes generates {"radio": "Label text"}
            # or {"radio option": "Use another currency"} instead of
            # {"Use another currency": "select"}
            # Detect these patterns and flip key/value so form_handler
            # can find the radio by its label text.
            # ============================================================
            data = step.get("data", {})
            if data and isinstance(data, dict):
                RADIO_KEY_PATTERNS = {
                    "radio",
                    "radio option",
                    "radio button",
                    "radio btn",
                    "radiobutton",
                    "radio_option",
                    "radio_button",
                    "select radio",
                    "choose radio",
                    "radio selection",
                    "radio_selection",
                }
                new_data = {}
                for k, v in data.items():
                    if k.lower().strip() in RADIO_KEY_PATTERNS and isinstance(v, str):
                        # Flip: use label text as key, "select" as value
                        new_data[v] = "select"
                        print(f"   🔧 AUTO-FIX radio: '{k}': '{v}' → '{v}': 'select'")
                    else:
                        new_data[k] = v
                step["data"] = new_data

            # ============================================================
            # FIX PYTHON LIST STRINGS: AI sometimes wraps multi-value fields
            # in Python list syntax, e.g. "['2026-02-23 00:00:00', '2026-02-23 11:00:00']"
            # Convert these to plain comma-separated strings so form_handler
            # can split them correctly.
            # ============================================================
            data = step.get("data", {})
            if data and isinstance(data, dict):
                import re as _re

                cleaned_data = {}
                for k, v in data.items():
                    if isinstance(v, str):
                        stripped = v.strip()
                        # Matches both ['...', '...'] and ["...", "..."] list literals
                        if stripped.startswith("[") and stripped.endswith("]"):
                            inner = stripped[1:-1]
                            # Remove surrounding quotes from each element and rejoin
                            parts = _re.split(r",\s*", inner)
                            clean_parts = [
                                p.strip().strip("'\"")
                                for p in parts
                                if p.strip().strip("'\"")
                            ]
                            if clean_parts:
                                new_val = ", ".join(clean_parts)
                                print(
                                    f"   🔧 AUTO-FIX list string: '{k}': {stripped!r} → {new_val!r}"
                                )
                                cleaned_data[k] = new_val
                                continue
                    cleaned_data[k] = v
                step["data"] = cleaned_data

        # Track download filenames
        if action == "download" and step.get("value"):
            last_filename = step["value"]

        # Clean up internal keys before adding to plan
        step.pop("_original_action", None)

        # Skip unknown actions that can't be mapped
        if step.get("action") not in VALID_ACTIONS:
            print(
                f"   ⚠️ SKIP unknown action: '{step.get('action')}' (no mapping found)"
            )
            continue

        fixed_plan.append(step)

    # ============================================================
    # STEP 3: Resolve partial/shorthand navigation paths
    # e.g. ["Faction Feud Event"] → ["Live Events", "Faction Feud", "Faction Feud Event"]
    # ============================================================
    fixed_plan = _resolve_navigation_paths(fixed_plan)

    # ============================================================
    # STEP 3a': Remove spurious download before edit_row
    # AI sometimes hallucinates an early "Export CSV" step before the
    # edit_row + tab navigation, then generates the correct download later.
    # Also removes the duplicate navigate that follows the spurious download.
    # Must run after path resolution so paths can be compared.
    # ============================================================
    fixed_plan = _remove_download_before_edit_row(fixed_plan, user_command)

    # ============================================================
    # STEP 3b: Remove/convert navigate steps targeting in-page tabs
    # e.g. navigate(["Contest Superstars"]) → removed (if click exists later)
    #      or → click("Contest Superstars")
    # Prevents navigator from deep-scanning sidebar for tab names and crashing.
    # ============================================================
    fixed_plan = _remove_invalid_navigate_to_tabs(fixed_plan)

    # ============================================================
    # STEP 3c: Merge consecutive NAVIGATE steps into path array
    # Pattern: navigate(A) → navigate(B) → navigate(C)
    # Should become: navigate(path=[A, B, C])
    # ============================================================
    fixed_plan = _merge_navigate_steps(fixed_plan)

    # ============================================================
    # STEP 3d: INJECT missing initial navigate
    # If AI skipped "Vào X" and plan doesn't start with navigate,
    # deterministically prepend it from NAVIGATION_PATH_MAP.
    # ============================================================
    fixed_plan = _inject_missing_initial_navigate(fixed_plan, user_command)

    # ============================================================
    # STEP 3e: INJECT missing checkbox before download
    # If command says "Chọn N ID bất kỳ -> Export CSV" but AI skipped
    # the checkbox step, inject checkbox(random_N) before download.
    # ============================================================
    fixed_plan = _inject_missing_checkbox_before_download(fixed_plan, user_command)

    # ============================================================
    # STEP 3f: Remove spurious edit_row(RANDOM) before checkbox
    # Must run AFTER 3e so checkbox exists regardless of whether AI or
    # the injector added it. AI confuses "Chọn N ID bất kỳ" (→ checkbox)
    # with "Sửa bất kỳ" (→ edit_row).
    # ============================================================
    fixed_plan = _remove_edit_row_before_checkbox(fixed_plan)

    # ============================================================
    # STEP 4: Merge consecutive process_deployment-related actions
    # Pattern: click_logo → select_checkbox(Offers) → click_button(Process)
    # Should become: process_deployment(options=["Offers"])
    # ============================================================
    merged_plan = _merge_process_deployment_steps(
        fixed_plan, uncheck_targets=uncheck_targets
    )

    # ============================================================
    # STEP 5: AUTO-INFER deployment options if empty
    # If process_deployment has no options, infer from context
    # ============================================================
    merged_plan = _auto_infer_deployment_options(merged_plan, user_command)

    # ============================================================
    # STEP 5b: STRIP invalid deployment options
    # Remove tab names (e.g. "Contest Superstars") that AI wrongly
    # puts in process_deployment options because they appear near
    # the logo-click in the command.
    # ============================================================
    merged_plan = _strip_invalid_deploy_options(merged_plan)

    # ============================================================
    # STEP 6: AUTO-INJECT missing clone_row from user command
    # If user said "Clone ID: X" but AI skipped clone_row entirely,
    # inject it deterministically based on the original command.
    # ============================================================
    merged_plan = _inject_missing_clone_row(merged_plan, user_command)

    # ============================================================
    # STEP 7: AUTO-INJECT save_form(mode=clone) after clone_row
    # Pattern: clone_row → update_form → ???
    # If ??? is not save_form(mode=clone), inject it automatically.
    # Also splits update_form if it mixes modal fields + post-clone fields.
    # Also injects modal update_form from user_command if AI skipped it.
    # ============================================================
    merged_plan = _inject_clone_save(merged_plan, user_command)

    # ============================================================
    # STEP 7b: RENAME RBE clone modal field name
    # AI uses generic "New ID" but RBE modal uses
    # "Cloned Rules Based Tournament ID".
    # ============================================================
    merged_plan = _fix_rbe_clone_field_name(merged_plan, user_command)

    # ============================================================
    # STEP 7b2: NORMALIZE "New X" → "X" in clone modal fields
    # AI uses "New Section ID" (matching test-case text) but the
    # Offer Section clone modal's DOM label is just "Section ID".
    # ============================================================
    merged_plan = _fix_clone_modal_new_prefix_fields(merged_plan, user_command)

    # ============================================================
    # STEP 7c: CONVERT single-ID update_form → edit_row
    # When AI generates update_form({*ID: value}) on a list page
    # (no preceding edit_row/clone_row), it means "filter & edit
    # the row whose ID = value", not "fill a form field".
    # ============================================================
    merged_plan = _fix_id_only_update_to_edit_row(merged_plan)

    # ============================================================
    # STEP 7d: FIX PVE "Clone Chapter" button confused with clone_row
    # AI generates: clone_row(bookID) → update_form(New ID) → save_form(clone)
    # Correct:      click("Clone Chapter") → click("Chapter N") → save_form(save)
    # ============================================================
    merged_plan = _fix_pve_clone_chapter(merged_plan, user_command)

    # ============================================================
    # STEP 8: Merge consecutive update_form → save_form(save) sequences
    # Pattern: update_form(A) → save_form(save) → update_form(B) → save_form(save)
    # Becomes: update_form(A ∪ B) → save_form(save)
    # Prevents validation errors when interdependent fields (e.g. PreEvent
    # dates + Active Phase dates) are split across separate save operations.
    # ============================================================
    merged_plan = _merge_consecutive_update_save(merged_plan)

    # ============================================================
    # STEP 8b: Merge PVE CSS update_form steps
    # Pattern: update_form({'Contest Superstar': 'on'}) → update_form({panel fields})
    # Becomes: update_form({'Contest Superstar': 'on', ...panel fields})
    # Ensures the special-case handler sees toggle + panel data together.
    # ============================================================
    merged_plan = _merge_pve_css_update_steps(merged_plan)

    # ============================================================
    # STEP 8c: Fix RBE type-selection modal: save_form → click("Continue")
    # Pattern: update_form({"Radio: Solo": "select"}) → save_form
    # The modal has a "Continue" button, not Save. AI always generates save_form here.
    # ============================================================
    merged_plan = _fix_rbe_type_modal_continue(merged_plan)

    # ============================================================
    # STEP 8d: Normalize page-filter field name → canonical "ID contains"
    # Every filter page (Offer, Offer Section, PVE, RBE, Gacha, ...) uses the
    # SAME "ID contains" search box. AI sometimes emits per-page labels like
    # "Offer Name". Value-based (RANDOM sentinel) so real multi-value filters
    # (e.g. Boost Result Value2 = "Red") are untouched.
    # ============================================================
    merged_plan = _fix_offer_filter_field(merged_plan)

    # ============================================================
    # STEP 9: Remove redundant click step after save_form(mode=clone)
    # Pattern: save_form(clone) → click("Create book and Open in V2")
    # _save_form(mode="clone") already clicks the clone submit button,
    # so the extra click is a duplicate that can cause unexpected navigation.
    # ============================================================
    merged_plan = _remove_click_after_clone_save(merged_plan)

    # ============================================================
    # STEP 10: INJECT missing final process_deployment
    # Every test case ends with "Bấm vào logo The Brick". If the AI dropped it
    # and the plan doesn't already end with process_deployment, append
    # process_deployment(options=[]) so the run navigates home / closes cleanly.
    # Runs LAST so it sees the fully merged plan shape.
    # ============================================================
    merged_plan = _inject_missing_final_deployment(merged_plan, user_command)

    if len(merged_plan) != len(plan):
        print(
            f"   🔧 AUTO-FIX: Plan {len(plan)} steps → {len(merged_plan)} steps after fix"
        )

    return merged_plan




__all__ = [
    "fix_action_plan",
    "_inject_missing_initial_navigate",
    "_resolve_navigation_paths",
    "_remove_invalid_navigate_to_tabs",
    "_merge_navigate_steps",
    "_strip_invalid_deploy_options",
    "_inject_missing_checkbox_before_download",
    "_auto_infer_deployment_options",
    "_merge_process_deployment_steps",
    "_inject_missing_final_deployment",
    "_remove_download_before_edit_row",
    "_remove_edit_row_before_checkbox",
    "_fix_pve_clone_chapter",
    "_fix_rbe_clone_field_name",
    "_fix_clone_modal_new_prefix_fields",
    "_fix_id_only_update_to_edit_row",
    "_remove_click_after_clone_save",
    "_inject_missing_clone_row",
    "_extract_clone_modal_fields",
    "_inject_clone_save",
    "_merge_consecutive_update_save",
    "_merge_pve_css_update_steps",
]
