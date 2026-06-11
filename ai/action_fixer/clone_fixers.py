# ai/action_fixer/clone_fixers.py - split from action_fixer.py
# Clone & row-action fixers: clone_row inject, modal fields, edit_row
from ._constants import (
    DEPLOYMENT_KEYWORDS,
    PAGE_TAB_NAMES,
    NAVIGATION_PATH_MAP,
    ACTION_NAME_MAP,
    VALID_ACTIONS,
    _VALID_DEPLOY_OPTIONS,
)


def _remove_download_before_edit_row(plan, user_command=""):
    """
    Remove spurious download steps that appear before the first edit_row/clone_row,
    when a legitimate download already exists after edit_row.

    Also removes a duplicate navigate immediately following the spurious download.
    AI pattern: navigate(X) → download [spurious] → navigate(X) [dup] → edit_row → ... → download [real]
    """
    edit_row_positions = [
        i for i, s in enumerate(plan) if s.get("action") in ("edit_row", "clone_row")
    ]
    download_positions = [i for i, s in enumerate(plan) if s.get("action") == "download"]

    if not edit_row_positions or not download_positions:
        return plan

    first_edit = min(edit_row_positions)
    downloads_before = [i for i in download_positions if i < first_edit]
    downloads_after = [i for i in download_positions if i > first_edit]

    if not downloads_before or not downloads_after:
        return plan

    # No guard needed: there is no legitimate test case where a download appears
    # before edit_row AND another download appears after edit_row.
    # The only time this pattern occurs is when the AI hallucinates an early export.
    print(
        f"   🔧 DETECT: download before edit_row at positions {downloads_before}, "
        f"real download after at {downloads_after} — removing spurious early download(s)"
    )

    positions_to_remove = set(downloads_before)

    # Also remove duplicate navigate immediately after the spurious download
    for dl_pos in downloads_before:
        next_pos = dl_pos + 1
        if next_pos >= len(plan) or plan[next_pos].get("action") != "navigate":
            continue
        prev_nav = next(
            (plan[k] for k in range(dl_pos - 1, -1, -1) if plan[k].get("action") == "navigate"),
            None,
        )
        if prev_nav is None:
            continue
        prev_path = prev_nav.get("path", [])
        next_path = plan[next_pos].get("path", [])
        if prev_path and prev_path == next_path:
            positions_to_remove.add(next_pos)
            print(f"   🔧 REMOVE duplicate navigate after spurious download (path={next_path})")

    result = []
    for i, step in enumerate(plan):
        if i in positions_to_remove:
            if step.get("action") == "download":
                print(
                    f"   🔧 REMOVE spurious download('{step.get('target', '?')}', "
                    f"'{step.get('value', '')}') before edit_row"
                )
            continue
        result.append(step)
    return result


def _remove_edit_row_before_checkbox(plan):
    """
    Remove edit_row(RANDOM) steps that appear before a checkbox step on a list page
    with NO form action between them.

    AI confuses "Chọn N ID bất kỳ" (select rows → checkbox) with
    "Sửa [entity] bất kỳ" (edit row → edit_row).  The fixer only removes
    edit_row(RANDOM) when checkbox appears before any update_form/save_form in
    the remaining plan — meaning no real form was opened.
    """
    _FORM_BLOCKERS = ("update_form", "save_form", "scan_tabs", "check_fields")

    result = []
    for i, step in enumerate(plan):
        action = step.get("action", "")
        if (
            action in ("edit_row", "clone_row")
            and step.get("target", "").upper() == "RANDOM"
        ):
            # Scan forward: checkbox must appear before any form-blocker action
            checkbox_before_form = False
            for s in plan[i + 1:]:
                a = s.get("action", "")
                if a == "checkbox":
                    checkbox_before_form = True
                    break
                if a in _FORM_BLOCKERS:
                    break
            if checkbox_before_form:
                print(
                    "   🔧 REMOVE spurious edit_row(RANDOM) before checkbox "
                    "(AI confused 'Chọn N bất kỳ' with edit_row)"
                )
                continue
        result.append(step)
    return result




def _fix_pve_clone_chapter(plan, user_command=""):
    """
    Fix AI confusing "Clone Chapter" (in-page button) with clone_row (table action).

    Two-pass approach:
    PASS 1 — Fix book entry if AI used clone_row instead of edit_row for "Sửa ID vừa clone".
             Also removes any wrong clone-modal update_form/save_form/wait block that follows.
    PASS 2 — Ensure click("Clone Chapter") is followed by click("Chapter N") + save_form(save).
             Fixes the common AI mistake of generating update_form + save_form(clone) after
             click("Clone Chapter") instead of click("Chapter N") + save_form(save).
    """
    import re as _re

    cmd_lower = (user_command or "").lower()
    if "clone chapter" not in cmd_lower:
        return plan

    m = _re.search(r"chapter\s+(\d+)", cmd_lower)
    chapter_target = f"Chapter {m.group(1)}" if m else "Chapter 1"

    result = list(plan)

    # ── PASS 1: Fix book entry ────────────────────────────────────────────────
    edit_positions = [i for i, s in enumerate(result) if s.get("action") == "edit_row"]
    clone_positions = [i for i, s in enumerate(result) if s.get("action") == "clone_row"]

    if not edit_positions and clone_positions:
        # AI used clone_row for "Sửa ID vừa clone". Convert it to edit_row and
        # remove the wrong clone-modal block (save_form/update_form/wait) that follows.
        first_clone = clone_positions[0]
        clone_target = result[first_clone].get("target", "")
        end_idx = first_clone + 1
        while end_idx < len(result) and result[end_idx].get("action") in (
            "save_form", "update_form", "wait"
        ):
            end_idx += 1
        result = (
            result[:first_clone]
            + [{"action": "edit_row", "target": clone_target}, {"action": "wait"}]
            + result[end_idx:]
        )
        print(
            f"   🔧 PVE-CLONE-CHAPTER(pass1): clone_row → edit_row('{clone_target}') + wait"
        )

    elif edit_positions:
        # If clone_row also appears AFTER the last edit_row, remove it (old Case 1).
        last_edit = max(edit_positions)
        clone_idx = next(
            (i for i, s in enumerate(result) if i > last_edit and s.get("action") == "clone_row"),
            None,
        )
        if clone_idx is not None:
            end_idx = clone_idx + 1
            while end_idx < len(result) and result[end_idx].get("action") in (
                "update_form", "save_form"
            ):
                end_idx += 1
            result = result[:clone_idx] + result[end_idx:]
            print(f"   🔧 PVE-CLONE-CHAPTER(pass1-orig): removed spurious clone_row block inside book")

    # ── PASS 2: Fix the Clone Chapter click sequence ──────────────────────────
    edit_positions = [i for i, s in enumerate(result) if s.get("action") == "edit_row"]
    if not edit_positions:
        return result

    last_edit = max(edit_positions)

    # Remove any click("Clone Chapter") that appears BEFORE edit_row — AI hallucination
    before_count = sum(
        1 for i, s in enumerate(result)
        if i < last_edit
        and s.get("action") == "click"
        and "clone chapter" in str(s.get("target", "")).lower()
    )
    if before_count:
        result = [
            s for i, s in enumerate(result)
            if not (
                i < last_edit
                and s.get("action") == "click"
                and "clone chapter" in str(s.get("target", "")).lower()
            )
        ]
        # Recalculate positions after removal
        edit_positions = [i for i, s in enumerate(result) if s.get("action") == "edit_row"]
        last_edit = max(edit_positions)
        print(f"   🔧 PVE-CLONE-CHAPTER(pass2-pre): removed {before_count} spurious click('Clone Chapter') before edit_row")

    # Find click("Clone Chapter") after edit_row
    click_clone_idx = next(
        (
            i for i, s in enumerate(result)
            if i > last_edit
            and s.get("action") == "click"
            and "clone chapter" in str(s.get("target", "")).lower()
        ),
        None,
    )

    if click_clone_idx is None:
        # No click("Clone Chapter") yet — inject full sequence after edit_row+wait
        insert_pos = last_edit + 1
        while insert_pos < len(result) and result[insert_pos].get("action") == "wait":
            insert_pos += 1
        end_idx = insert_pos
        while end_idx < len(result) and result[end_idx].get("action") in (
            "update_form", "save_form"
        ):
            end_idx += 1
        result = (
            result[:insert_pos]
            + [
                {"action": "click", "target": "Clone Chapter"},
                {"action": "click", "target": chapter_target},
                {"action": "save_form", "mode": "save"},
            ]
            + result[end_idx:]
        )
        print(
            f"   🔧 PVE-CLONE-CHAPTER(pass2): injected click('Clone Chapter')"
            f" + click('{chapter_target}') + save_form(save)"
        )
        return result

    # click("Clone Chapter") found — check what comes right after
    next_idx = click_clone_idx + 1
    if (
        next_idx < len(result)
        and result[next_idx].get("action") == "click"
        and chapter_target.lower() in str(result[next_idx].get("target", "")).lower()
    ):
        # Already has click("Chapter N") — fix save mode if wrong
        save_idx = next_idx + 1
        if save_idx < len(result) and result[save_idx].get("action") == "save_form":
            result[save_idx]["mode"] = "save"
        return result

    # Wrong steps after click("Clone Chapter"): replace with correct sequence.
    end_idx = next_idx
    while end_idx < len(result) and result[end_idx].get("action") in (
        "update_form", "save_form"
    ):
        end_idx += 1
    result = (
        result[:next_idx]
        + [
            {"action": "click", "target": chapter_target},
            {"action": "save_form", "mode": "save"},
        ]
        + result[end_idx:]
    )
    print(
        f"   🔧 PVE-CLONE-CHAPTER(pass2): after click('Clone Chapter') → "
        f"click('{chapter_target}') + save_form(save)"
    )
    return result




def _fix_rbe_clone_field_name(plan, user_command=""):
    """
    RBE clone modal uses label 'Cloned Rules Based Tournament ID', but the AI
    is taught 'New ID' (generic). Rename any generic ID key in an update_form
    that follows a clone_row when the command is in RBE context.
    """
    cmd_lower = (user_command or "").lower()
    if "rbe" not in cmd_lower:
        return plan

    # Find clone_row positions so we only rewrite update_forms after them
    clone_positions = {i for i, s in enumerate(plan) if s.get("action") == "clone_row"}
    if not clone_positions:
        return plan

    for i, step in enumerate(plan):
        if step.get("action") != "update_form":
            continue
        # Only rewrite update_forms that come after a clone_row
        if not any(cp < i for cp in clone_positions):
            continue
        data = step.get("data", {})
        for generic_key in ("New ID", "New Event ID", "New Tournament ID"):
            if generic_key in data:
                data["Cloned Rules Based Tournament ID"] = data.pop(generic_key)
                print(f"   🔧 RBE clone: renamed '{generic_key}' → 'Cloned Rules Based Tournament ID'")
                break
    return plan


def _fix_clone_modal_new_prefix_fields(plan, user_command=""):
    """
    Clone modals often label fields as 'X' but the AI generates 'New X' because
    the test-case text says "New X: ...".  Strip the known 'New ' prefixes so
    _find_input_element gets the label text that actually exists in the DOM.

    Known mappings (AI-generated key → DOM <label> text):
      "New Section ID" → "Section ID"   (Offer Section clone modal, for='section_id')
    """
    _NEW_PREFIX_RENAMES = {
        "new section id": "Section ID",
    }
    clone_positions = {i for i, s in enumerate(plan) if s.get("action") == "clone_row"}
    if not clone_positions:
        return plan
    for i, step in enumerate(plan):
        if step.get("action") != "update_form":
            continue
        if not any(cp < i for cp in clone_positions):
            continue
        data = step.get("data", {})
        for k in list(data.keys()):
            canonical = _NEW_PREFIX_RENAMES.get(k.lower().strip())
            if canonical and k != canonical:
                data[canonical] = data.pop(k)
                print(f"   🔧 CLONE MODAL: renamed '{k}' → '{canonical}'")
    return plan


def _fix_id_only_update_to_edit_row(plan):
    """
    Detect update_form({*ID: value}) on a list page (no preceding edit_row/clone_row)
    and convert it to edit_row(target=value).

    Pattern: AI generates update_form({"Rules Based Tournament ID": "hieunm_test_..."})
    right after navigate + checkbox steps, meaning it's actually a table-row edit, not
    a form field fill.  Detection criteria:
      - update_form with exactly 1 entry
      - the key ends with " id" (case-insensitive) or is exactly "id"
      - the value contains no spaces (looks like an ID, not free text)
      - no edit_row or clone_row appears anywhere before this step in the plan
    """
    opened_form = False  # True once we've seen edit_row or clone_row
    result = []
    for step in plan:
        action = step.get("action", "")
        if action in ("edit_row", "clone_row"):
            opened_form = True
        if action == "update_form" and not opened_form:
            data = step.get("data", {})
            if len(data) == 1:
                key, val = next(iter(data.items()))
                key_l = str(key).lower().strip()
                val_s = str(val).strip()
                is_id_key = key_l == "id" or key_l.endswith(" id")
                is_id_val = bool(val_s) and " " not in val_s
                if is_id_key and is_id_val:
                    print(
                        f"   🔧 CONVERT update_form({{{key!r}: {val_s!r}}}) → "
                        f"edit_row(target={val_s!r}) (single-ID on list page)"
                    )
                    result.append({"action": "edit_row", "target": val_s})
                    opened_form = True
                    continue
        result.append(step)
    return result




def _remove_click_after_clone_save(plan):
    """
    Remove a 'click' step that immediately follows save_form(mode='clone').

    save_form(mode='clone') already clicks the clone submit button
    (including PVE's "Create book and Open in V2"). An extra click step
    generated by the AI would double-fire the button, causing unexpected
    navigation or errors.
    """
    _SUBMIT_KEYWORDS = ("create", "clone", "save", "submit", "confirm", "open in")
    result = []
    i = 0
    while i < len(plan):
        step = plan[i]
        if (
            step.get("action") == "save_form"
            and step.get("mode") == "clone"
            and i + 1 < len(plan)
            and plan[i + 1].get("action") == "click"
        ):
            next_target = str(plan[i + 1].get("target", "")).lower()
            if any(kw in next_target for kw in _SUBMIT_KEYWORDS):
                print(
                    f"   🔧 Removed redundant click('{plan[i + 1].get('target')}') after save_form(mode=clone)"
                )
                result.append(step)
                i += 2
                continue
        result.append(step)
        i += 1
    return result




def _inject_missing_clone_row(plan, user_command=""):
    """
    AUTO-FIX: Detect when user command mentions "Clone ID: X" but AI
    completely skipped the clone_row action. Inject it deterministically.

    This handles the case where the AI jumps directly to update_form
    without first generating clone_row.

    Detection patterns in user command:
      - "Clone ID: X"
      - "Bấm nút Clone ID: X"
      - "Clone X" (where X looks like an ID)
      - "Bấm Clone X"

    Also ensures "New Event ID" / "New ID" is present in update_form data
    when "New ID: Y" is mentioned in the command.
    """
    import re as _re

    if not plan or not user_command:
        return plan

    # Check if plan already has a clone_row action
    has_clone_row = any(step.get("action") == "clone_row" for step in plan)
    if has_clone_row:
        return plan

    # --- Detect clone target from user command ---
    # Patterns (case-insensitive, Vietnamese + English):
    #   "Clone ID: EventGacha_test_15"
    #   "Bấm nút Clone ID: EventGacha_test_15"
    #   "Bấm Clone EventGacha_test_15"
    #   "Clone EventGacha_test_15"
    #   "Clone một ID bất kỳ"
    #   "Clone bất kỳ"
    #   "Clone random"
    clone_patterns = [
        # "Clone ID: X" or "Bấm nút Clone ID: X" — ID is part of the label
        r"(?:bấm\s+(?:nút\s+)?)?clone\s+id\s*:\s*([\w\-\.]+)",
        # "Clone X" where X looks like an ID (contains underscore or is alphanumeric)
        r"(?:bấm\s+(?:nút\s+)?)?clone\s+([\w\-\.]+(?:_[\w\-\.]+)+)",
        # "Clone bất kỳ", "Clone một ID bất kỳ", "Clone random" → RANDOM
        r"(?:bấm\s+(?:nút\s+)?)?clone\s+(?:một\s+)?(?:\w+\s+)*(?:bất\s*kỳ|random|any)",
    ]

    clone_target = None
    for idx_p, pattern in enumerate(clone_patterns):
        match = _re.search(pattern, user_command, _re.IGNORECASE)
        if match:
            if idx_p == 2:  # Random pattern matched
                clone_target = "RANDOM"
            else:
                clone_target = match.group(1).strip()
            break

    if not clone_target:
        return plan

    print(
        f"   🔧 CRITICAL AUTO-FIX: AI skipped clone_row! Detected 'Clone {clone_target}' in user command."
    )

    # --- Detect New ID from user command (generic: New Event ID, New FF ID, New ID) ---
    new_id = None
    new_id_field_name = "New Event ID"  # default
    new_id_patterns = [
        r"(new\s+(?:\w+\s+)?id)\s*:\s*([\w\-\.]+)",
    ]
    for pattern in new_id_patterns:
        match = _re.search(pattern, user_command, _re.IGNORECASE)
        if match:
            raw_label = match.group(1)
            new_id = match.group(2).strip()
            # Normalize field name
            words = raw_label.split()
            normalized = []
            for w in words:
                if w.lower() == "id":
                    normalized.append("ID")
                elif len(w) <= 2:
                    normalized.append(w.upper())  # Short abbrevs: "ff" → "FF"
                else:
                    normalized.append(w.capitalize())  # "new" → "New"
            new_id_field_name = " ".join(normalized)
            break

    # --- Find injection point ---
    # Insert clone_row AFTER navigate (if any) and BEFORE the first update_form
    inject_index = 0
    for idx, step in enumerate(plan):
        action = step.get("action", "")
        if action == "navigate":
            inject_index = idx + 1
        elif action in ("update_form", "edit_row"):
            inject_index = idx
            break

    # If AI generated edit_row instead of clone_row for the same target, replace it
    replaced_edit = False
    for idx, step in enumerate(plan):
        if step.get("action") == "edit_row" and step.get("target") == clone_target:
            step["action"] = "clone_row"
            replaced_edit = True
            print(
                f"   🔧 AUTO-FIX: Converted edit_row('{clone_target}') → clone_row('{clone_target}')"
            )
            break

    if not replaced_edit:
        # Inject clone_row at the right position
        clone_step = {"action": "clone_row", "target": clone_target}
        plan.insert(inject_index, clone_step)
        print(
            f"   🔧 AUTO-FIX: Injected clone_row('{clone_target}') at position {inject_index}"
        )

    # --- Ensure New ID field is in the update_form data ---
    if new_id:
        # Find the first update_form after clone_row
        clone_idx = None
        for idx, step in enumerate(plan):
            if step.get("action") == "clone_row" and step.get("target") == clone_target:
                clone_idx = idx
                break

        if clone_idx is not None:
            # Look for update_form immediately after clone_row
            for idx in range(clone_idx + 1, len(plan)):
                step = plan[idx]
                if step.get("action") == "update_form":
                    data = step.get("data", {})
                    # Check if any New ID variant is already present (case-insensitive)
                    has_new_id = any(
                        _re.search(r"\bnew\b.*\bid\b", k, _re.IGNORECASE)
                        for k in data.keys()
                    )
                    if not has_new_id:
                        # Insert New ID field at the beginning of data
                        new_data = {new_id_field_name: new_id}
                        new_data.update(data)
                        step["data"] = new_data
                        print(
                            f"   🔧 AUTO-FIX: Added '{new_id_field_name}': '{new_id}' to update_form data"
                        )
                    break
                elif step.get("action") not in ("wait",):
                    # If there's no update_form directly after clone, create one
                    new_update = {
                        "action": "update_form",
                        "data": {new_id_field_name: new_id},
                    }
                    plan.insert(idx, new_update)
                    print(
                        f"   🔧 AUTO-FIX: Created update_form with '{new_id_field_name}': '{new_id}'"
                    )
                    break

    return plan




def _extract_clone_modal_fields(user_command):
    """
    Parse user command to extract clone modal field values.
    Returns a dict of modal fields extracted from the command text.

    Handles patterns like:
      "Clone ID: X -> New ID: Y, gate: Z, radio: Use another currency, currency: W"
      "Clone một ID bất kỳ -> New FF ID: Y, Gate: Z"
      "Clone random -> New Event ID: Y, Gate: Z"
    """
    import re as _re

    if not user_command:
        return {}

    modal_data = {}

    # --- Step 1: Find the Clone ACTION step (not a testcase header like "Clone the PVE:") ---
    # Prefer "-> Clone" pattern which marks the actual action step after navigation.
    # Fallback to first bare "Clone" if no arrow-prefixed clone found.
    arrow_to_clone = _re.search(r"->\s*clone\b", user_command, _re.IGNORECASE)
    if arrow_to_clone:
        # "remaining" is everything after the Clone step's own "->" up to the next "->"
        # i.e. the content of "-> Clone 1 Book contain LTPVE bất kỳ -> <fields>"
        clone_step_end = arrow_to_clone.end()          # position just after "-> clone"
        next_arrow = user_command.find("->", clone_step_end)
        if next_arrow == -1:
            return {}
        remaining = user_command[next_arrow + 2 :].strip()
    else:
        clone_start = _re.search(r"\bclone\b", user_command, _re.IGNORECASE)
        if not clone_start:
            return {}
        arrow_pos = user_command.find("->", clone_start.start())
        if arrow_pos == -1:
            return {}
        remaining = user_command[arrow_pos + 2 :].strip()

    # Find the boundary (next major action marker after ->)
    boundary_match = _re.search(
        r"->\s*(?:đợi|wait|sửa|bấm\s+nút\s+save|save|click|vào|export|import|process|logo|the\s+brick)",
        remaining,
        _re.IGNORECASE,
    )
    if boundary_match:
        segment = remaining[: boundary_match.start()].strip()
    else:
        segment = remaining.strip()

    if not segment:
        return {}

    print(f"   🔍 Parsing clone modal fields from segment: '{segment[:100]}...'")

    # --- Extract New [X] ID (generic: handles New Event ID, New FF ID, New ID, etc.) ---
    new_id_match = _re.search(
        r"(new\s+(?:\w+\s+)?id)\s*:\s*([\w\-\.]+)", segment, _re.IGNORECASE
    )
    if new_id_match:
        raw_label = new_id_match.group(1)  # e.g. "New FF ID", "New Event ID"
        value = new_id_match.group(2).strip()
        # Normalize field name: capitalize words, keep ID/FF uppercase
        words = raw_label.split()
        normalized = []
        for w in words:
            if w.lower() == "id":
                normalized.append("ID")
            elif len(w) <= 2:
                normalized.append(w.upper())  # Short abbrevs: "ff" → "FF"
            else:
                normalized.append(w.capitalize())  # "new" → "New", "event" → "Event"
        field_name = " ".join(normalized)
        modal_data[field_name] = value

    # --- Extract Gate ---
    gate_match = _re.search(r"\bgate\s*:\s*([\w\-\.]+)", segment, _re.IGNORECASE)
    if gate_match:
        modal_data["Gate"] = gate_match.group(1).strip()

    # --- Extract Radio selection ---
    # "radio: Use another currency" or "radio: Auto Generate a new currency"
    radio_match = _re.search(
        r"radio\s*:\s*((?:use another currency|auto generate[\w\s]*))",
        segment,
        _re.IGNORECASE,
    )
    if radio_match:
        radio_label = radio_match.group(1).strip()
        # Capitalize properly
        if "use another" in radio_label.lower():
            modal_data["Use another currency"] = "select"
        elif "auto generate" in radio_label.lower():
            modal_data["Auto Generate a new currency"] = "select"
        else:
            modal_data[radio_label] = "select"

    # --- Extract Currency ---
    # Match "currency: X" but NOT "radio: ... currency" or "another currency"
    currency_match = _re.search(
        r"(?<!another\s)(?<!a new\s)\bcurrency\s*:\s*([\w\-\.]+)",
        segment,
        _re.IGNORECASE,
    )
    if currency_match:
        val = currency_match.group(1).strip()
        # Avoid capturing "GachaShard" if it's actually in a radio label context
        if val.lower() not in ("use", "auto", "another", "a"):
            modal_data["Currency"] = val

    # --- Extract Book Name (PVE clone modal) ---
    # Handles "Sửa Book Name: X" or "Book Name: X"
    book_name_match = _re.search(
        r"(?:sửa\s+)?book\s*name\s*:\s*([\w\-\.]+)",
        segment,
        _re.IGNORECASE,
    )
    if book_name_match:
        modal_data["Book Name"] = book_name_match.group(1).strip()

    if modal_data:
        print(f"   ✅ Extracted clone modal fields: {modal_data}")
    else:
        print(f"   ⚠️ Could not extract clone modal fields from command")

    return modal_data




def _inject_clone_save(plan, user_command=""):
    """
    AUTO-FIX: Inject save_form(mode='clone') after clone_row → update_form pattern.

    The Clone modal has its own set of fields (New Event ID, Gate, radio, Currency).
    After filling the modal, the user must click the Clone button (= save_form mode=clone).
    Any fields that belong to the NEW event page (Schedule, etc.) come AFTER that.

    This function:
    1. Detects clone_row followed by update_form
    2. Splits update_form into MODAL fields + POST-CLONE fields (if mixed)
    3. Injects save_form(mode=clone) between them
    4. If modal update_form is entirely missing, extracts fields from user_command
    """
    # Fields that live INSIDE the Clone modal
    CLONE_MODAL_FIELD_KEYWORDS = {
        "new event id",
        "new id",
        "new ff id",
        "new gacha id",
        "new boss id",
        "new offer id",
        "new mission id",
        "gate",
        "currency",
        "use another currency",
        "auto generate a new currency",
        "auto generate",
        "clone milestones",
        "book name",          # PVE clone modal
    }

    # Fields that belong OUTSIDE the modal (on the new event page after cloning)
    POST_CLONE_FIELD_KEYWORDS = {
        "schedule",
        "date",
        "time",
        "start",
        "end",
        "leaderboard",
        "consumable limit",
        "milestones type",
        "bracket preset",
    }

    def is_modal_field(key):
        import re as _re

        k = key.lower().strip()
        # Direct keyword match
        if any(kw in k for kw in CLONE_MODAL_FIELD_KEYWORDS):
            return True
        # Pattern match: "new ... id" covers all event types
        # e.g. "New FF ID", "New Event ID", "New Boss ID", etc.
        if _re.search(r"\bnew\b.*\bid\b", k):
            return True
        return False

    def is_post_clone_field(key):
        k = key.lower().strip()
        # If explicitly a modal field, don't treat as post-clone
        if is_modal_field(k):
            return False
        return any(kw in k for kw in POST_CLONE_FIELD_KEYWORDS)

    if not plan:
        return plan

    result = []
    i = 0
    while i < len(plan):
        step = plan[i]
        action = step.get("action", "")

        if action == "clone_row":
            result.append(step)
            i += 1

            # Gather consecutive update_form steps that follow clone_row
            update_forms = []
            while i < len(plan) and plan[i].get("action") == "update_form":
                update_forms.append(plan[i])
                i += 1

            if not update_forms:
                # Check if save_form(clone) is immediately after clone_row
                if (
                    i < len(plan)
                    and plan[i].get("action") == "save_form"
                    and plan[i].get("mode") == "clone"
                ):
                    # BAD PATTERN: clone_row → save_form(clone) → [wait?] → update_form(modal fields)
                    # Look ahead to pull modal update_form fields BEFORE save_form(clone)
                    j = i + 1  # start looking past save_form(clone)

                    # Skip wait steps between save_form and update_form
                    skipped_waits = []
                    while j < len(plan) and plan[j].get("action") == "wait":
                        skipped_waits.append(plan[j])
                        j += 1

                    # Collect consecutive update_form steps ahead
                    lookahead_updates = []
                    while j < len(plan) and plan[j].get("action") == "update_form":
                        lookahead_updates.append(plan[j])
                        j += 1

                    if lookahead_updates:
                        # Merge all ahead update_form data to check for modal fields
                        all_data = {}
                        for uf in lookahead_updates:
                            all_data.update(uf.get("data") or {})

                        # Check if any modal fields are in the lookahead
                        has_modal = any(is_modal_field(k) for k in all_data)

                        if has_modal:
                            # Reorder: split modal vs post-clone, emit correctly
                            modal_data = {}
                            post_clone_data = {}
                            mixed_data = {}
                            for key, val in all_data.items():
                                if is_modal_field(key):
                                    modal_data[key] = val
                                elif is_post_clone_field(key):
                                    post_clone_data[key] = val
                                else:
                                    mixed_data[key] = val
                            modal_data.update(mixed_data)

                            if modal_data:
                                result.append(
                                    {"action": "update_form", "data": modal_data}
                                )
                                print(
                                    f"   🔧 AUTO-FIX: Moved misplaced modal fields {list(modal_data.keys())} "
                                    "before save_form(mode=clone)"
                                )
                            result.append({"action": "save_form", "mode": "clone"})
                            for w in skipped_waits:
                                result.append(w)
                            if post_clone_data:
                                result.append(
                                    {"action": "update_form", "data": post_clone_data}
                                )
                                print(
                                    f"   🔧 AUTO-FIX: Placed post-clone fields {list(post_clone_data.keys())} "
                                    "after save_form(mode=clone)"
                                )
                            # Advance i past all consumed steps
                            i = j
                            continue

                    # No modal fields found ahead — try extracting from user command
                    extracted = _extract_clone_modal_fields(user_command)
                    if extracted:
                        result.append({"action": "update_form", "data": extracted})
                        print(
                            f"   🔧 CRITICAL AUTO-FIX: Injected missing modal update_form "
                            f"from user command: {list(extracted.keys())}"
                        )
                        result.append({"action": "save_form", "mode": "clone"})
                        for w in skipped_waits:
                            result.append(w)
                        # Re-emit ahead update_forms as post-clone
                        for uf in lookahead_updates:
                            result.append(uf)
                        i = j
                    else:
                        # Truly nothing — pass through as-is
                        pass
                    continue

                # No update_form AND no save_form(clone) immediately after clone_row.
                # NEW: Look ahead past wait steps to find update_form(s) with modal fields.
                # Handles AI pattern: clone_row → wait → update_form({modal fields}) → save_form
                j = i
                ahead_waits = []
                while j < len(plan) and plan[j].get("action") == "wait":
                    ahead_waits.append(plan[j])
                    j += 1
                ahead_updates = []
                while j < len(plan) and plan[j].get("action") == "update_form":
                    ahead_updates.append(plan[j])
                    j += 1

                if ahead_updates:
                    all_data = {}
                    for uf in ahead_updates:
                        all_data.update(uf.get("data") or {})
                    has_modal = any(is_modal_field(k) for k in all_data)
                    if has_modal:
                        modal_data = {k: v for k, v in all_data.items() if is_modal_field(k)}
                        post_clone_data = {k: v for k, v in all_data.items() if is_post_clone_field(k)}
                        mixed_data = {k: v for k, v in all_data.items() if not is_modal_field(k) and not is_post_clone_field(k)}
                        modal_data.update(mixed_data)
                        result.append({"action": "update_form", "data": modal_data})
                        result.append({"action": "save_form", "mode": "clone"})
                        print(
                            f"   🔧 AUTO-FIX: Pulled wait-skipped modal fields "
                            f"{list(modal_data.keys())} before save_form(clone)"
                        )
                        if post_clone_data:
                            result.append({"action": "update_form", "data": post_clone_data})
                        # Also consume a misplaced save_form that immediately follows the update_forms
                        if j < len(plan) and plan[j].get("action") == "save_form":
                            j += 1
                        i = j
                        continue

                # Fallback: extract from user command text
                extracted = _extract_clone_modal_fields(user_command)
                if extracted:
                    result.append({"action": "update_form", "data": extracted})
                    print(
                        f"   🔧 CRITICAL AUTO-FIX: Injected missing modal update_form "
                        f"from user command: {list(extracted.keys())}"
                    )
                result.append({"action": "save_form", "mode": "clone"})
                print("   🔧 AUTO-FIX: Injected save_form(mode=clone) after clone_row")
                continue

            # Check if save_form(mode=clone) is already immediately after update_forms
            already_has = (
                i < len(plan)
                and plan[i].get("action") == "save_form"
                and plan[i].get("mode") == "clone"
            )

            if already_has:
                # Already correct — just pass through
                for uf in update_forms:
                    result.append(uf)
                continue

            # Merge all update_form data into one flat dict to analyse
            all_data = {}
            for uf in update_forms:
                all_data.update(uf.get("data") or {})

            # Split: modal fields vs post-clone fields
            modal_data = {}
            post_clone_data = {}
            mixed_data = {}  # Fields that are neither clearly modal nor post-clone

            for key, val in all_data.items():
                if is_modal_field(key):
                    modal_data[key] = val
                elif is_post_clone_field(key):
                    post_clone_data[key] = val
                else:
                    mixed_data[key] = val

            # Fields in mixed_data that have no clear ownership stay with modal
            # (safe default: they were probably intended for the modal)
            modal_data.update(mixed_data)

            # If no modal fields found in update_form, try extracting from user command
            if not modal_data:
                extracted = _extract_clone_modal_fields(user_command)
                if extracted:
                    modal_data = extracted
                    print(
                        f"   🔧 CRITICAL AUTO-FIX: No modal fields in update_form, "
                        f"extracted from user command: {list(extracted.keys())}"
                    )

            if modal_data:
                result.append({"action": "update_form", "data": modal_data})

            # Always inject the Clone button click
            result.append({"action": "save_form", "mode": "clone"})
            print(
                f"   🔧 AUTO-FIX: Injected save_form(mode=clone) after clone modal fields {list(modal_data.keys())}"
            )

            if post_clone_data:
                result.append({"action": "update_form", "data": post_clone_data})
                print(
                    f"   🔧 AUTO-FIX: Separated post-clone fields {list(post_clone_data.keys())} after Clone button"
                )

            continue

        result.append(step)
        i += 1

    return result
