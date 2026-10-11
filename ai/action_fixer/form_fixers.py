# ai/action_fixer/form_fixers.py - split from action_fixer.py
# Form step merges: update+save, PVE CSS update
import re

from ._constants import (
    DEPLOYMENT_KEYWORDS,
    PAGE_TAB_NAMES,
    NAVIGATION_PATH_MAP,
    ACTION_NAME_MAP,
    VALID_ACTIONS,
    _VALID_DEPLOY_OPTIONS,
)


def _merge_consecutive_update_save(plan):
    """
    Merge consecutive update_form → save_form(save) sequences into a single
    update_form → save_form(save).

    Pattern:
        update_form(A) → save_form(save) → update_form(B) → save_form(save) → ...
    Becomes:
        update_form(A ∪ B ∪ ...) → save_form(save)

    This prevents form validation errors when interdependent fields
    (e.g. PreEvent Phase dates and Active Phase dates) are split across
    separate save operations by the AI.

    Only merges save_form with mode='save'. Does NOT merge 'clone' or 'continue'.
    """
    if not plan or len(plan) < 4:
        return plan

    merged = []
    i = 0

    while i < len(plan):
        step = plan[i]

        # Check if this starts an update_form → save_form(save) sequence
        if (
            step.get("action") == "update_form"
            and i + 1 < len(plan)
            and plan[i + 1].get("action") == "save_form"
            and plan[i + 1].get("mode") == "save"
        ):
            # Collect all consecutive update_form → save_form(save) pairs
            combined_data = dict(step.get("data") or {})
            pairs_count = 1
            j = i + 2  # After the first save_form

            while (
                j < len(plan)
                and plan[j].get("action") == "update_form"
                and j + 1 < len(plan)
                and plan[j + 1].get("action") == "save_form"
                and plan[j + 1].get("mode") == "save"
            ):
                # Merge data from next update_form
                combined_data.update(plan[j].get("data") or {})
                pairs_count += 1
                j += 2  # Skip both update_form and save_form

            if pairs_count > 1:
                # We merged multiple pairs
                print(
                    f"   🔧 MERGE: Combined {pairs_count} update_form+save_form(save) "
                    f"pairs into 1 (fields: {list(combined_data.keys())})"
                )
                merged.append({"action": "update_form", "data": combined_data})
                merged.append({"action": "save_form", "mode": "save"})
                i = j
            else:
                # Only one pair, keep as-is
                merged.append(plan[i])
                i += 1
        else:
            merged.append(step)
            i += 1

    return merged




def _fix_rbe_type_modal_continue(plan):
    """
    Replace save_form that follows a Radio-only update_form with click("Continue").

    Pattern AI generates (wrong):
        click("New Rules Based Event") → update_form({"Radio: Solo": "select"}) → save_form
        click("New Rules Based Event") → update_form({"Solo": "select"}) → save_form(mode="continue")

    Correct (the modal has a "Continue" button, not Save):
        click("New Rules Based Event") → update_form({"Radio: Solo": "select"}) → click("Continue")

    Detection:
      - update_form ALL keys start with "Radio:" (any following save_form mode), OR
      - single-key update_form ALL values "select"/"on" AND previous step was click("New ...")
    """
    import re as _re

    if not plan or len(plan) < 2:
        return plan

    result = []
    i = 0
    while i < len(plan):
        step = plan[i]
        data = step.get("data") if isinstance(step.get("data"), dict) else {}

        prev_is_new_click = (
            bool(result)
            and result[-1].get("action") == "click"
            and _re.search(r"\bnew\b", str(result[-1].get("target", "")), _re.IGNORECASE)
        )

        is_radio_only = (
            step.get("action") == "update_form"
            and len(data) > 0
            and (
                # Pattern A: explicit "Radio:" prefix keys
                all(str(k).strip().lower().startswith("radio:") for k in data.keys())
                # Pattern B: bare radio name (e.g. "Solo") after "New X" click
                or (
                    prev_is_new_click
                    and len(data) == 1
                    and all(str(v).strip().lower() in ("select", "on") for v in data.values())
                )
            )
        )

        if (
            is_radio_only
            and i + 1 < len(plan)
            and plan[i + 1].get("action") == "save_form"
            # accept any mode (save, continue, clone, or no mode)
        ):
            result.append(step)
            result.append({"action": "click", "target": "Continue"})
            print(
                "   🔧 RBE-MODAL: Replaced save_form → click('Continue') after Radio-only update_form"
            )
            i += 2  # skip both update_form and save_form
        else:
            result.append(step)
            i += 1

    return result


def _fix_offer_filter_field(plan):
    """
    Normalize every page-filter field name to the canonical "ID contains".

    EVERY filter page in the Brick UI (Offer, Offer Section, Drip Offer, PVE,
    RBE, Gacha, Currency, ...) uses the SAME "ID contains" search box. The AI
    (and older prompt rules) sometimes emit per-page labels like "Offer Name",
    "Offer ID", "Section ID", etc. for a "Filter ... bất kỳ" command. Those
    labels don't exist on the page → field not found.

    Detection is value-based (the filter sentinel "RANDOM") so we never touch
    real multi-value filters like Boost Result Value2 = "Red".
    """
    _MISNAMED_FILTER_KEYS = {
        "offer name",
        "offer id",
        "section id",
        "section name",
        "id",
        "name",
        "id filter",
        "filter id",
        "search id",
    }

    result = []
    for step in plan:
        if (
            step.get("action") == "update_form"
            and isinstance(step.get("data"), dict)
            and len(step["data"]) == 1
        ):
            (k, v), = step["data"].items()
            is_filter_sentinel = str(v).strip().upper() == "RANDOM"
            needs_rename = k != "ID contains" and (
                is_filter_sentinel or k.lower().strip() in _MISNAMED_FILTER_KEYS
            )
            if needs_rename:
                print(
                    f"   🔧 FILTER-FIELD: Normalized '{k}' → 'ID contains' "
                    f"(all filter pages use the same search box)"
                )
                result.append({"action": "update_form", "data": {"ID contains": v}})
                continue
        result.append(step)

    return result


def _remove_spurious_edit_row_after_new_event(plan):
    """
    Remove spurious edit_row that AI adds after a "New X" creation flow.

    After click("New Rules Based Event") → update_form(radio) → save_form(continue)
    the page is already on the new entity's edit form. AI incorrectly thinks it
    needs to find & open the row from the table.

    Pattern to remove:
        click("New ...") → ... → save_form(mode="continue") | click("Continue")
        → [wait*] → edit_row(generated_id)  ← REMOVE THIS
        → update_form({... generated_id as a value ...})
    """
    import re as _re

    new_click_indices = [
        i for i, s in enumerate(plan)
        if s.get("action") == "click"
        and _re.search(r"\bnew\b", str(s.get("target", "")), _re.IGNORECASE)
    ]
    if not new_click_indices:
        return plan

    indices_to_remove = set()

    for new_click_idx in new_click_indices:
        # Find the first save_form(continue) or click("Continue") after new_click
        continue_idx = None
        for j in range(new_click_idx + 1, len(plan)):
            s = plan[j]
            if (
                s.get("action") == "save_form" and s.get("mode") == "continue"
            ) or (
                s.get("action") == "click"
                and str(s.get("target", "")).lower().strip() == "continue"
            ):
                continue_idx = j
                break
            if s.get("action") in ("navigate", "clone_row"):
                break

        if continue_idx is None:
            continue

        # Skip optional wait steps after continue
        j = continue_idx + 1
        while j < len(plan) and plan[j].get("action") == "wait":
            j += 1

        if j >= len(plan) or plan[j].get("action") != "edit_row":
            continue

        edit_row_target = str(plan[j].get("target", ""))
        is_random = edit_row_target.upper() == "RANDOM"
        is_generated_id = "_" in edit_row_target and len(edit_row_target) > 8

        if not is_random and not is_generated_id:
            continue

        if is_random:
            # edit_row("RANDOM") in a create-new flow is always spurious:
            # after clicking "Continue" you're already on the new entity's edit form.
            indices_to_remove.add(j)
            print(
                "   🔧 AUTO-FIX: Removed spurious edit_row('RANDOM') "
                "after 'New X' creation — already on the edit form"
            )
        else:
            # Confirm: the next update_form contains this same generated ID as a value
            next_idx = j + 1
            if next_idx < len(plan) and plan[next_idx].get("action") == "update_form":
                next_data = plan[next_idx].get("data", {})
                if any(str(v) == edit_row_target for v in next_data.values()):
                    indices_to_remove.add(j)
                    print(
                        f"   🔧 AUTO-FIX: Removed spurious edit_row('{edit_row_target}') "
                        "after 'New X' creation — already on the edit form"
                    )

    if not indices_to_remove:
        return plan
    return [s for i, s in enumerate(plan) if i not in indices_to_remove]


def _normalize_new_event_final_save(plan):
    """
    In a create-new flow (plan has click("New ...") + click("Continue")),
    normalize save_form(mode="continue") → save_form(mode="save") for the main form save.

    After _fix_rbe_type_modal_continue converts the type-modal save_form to
    click("Continue"), any remaining save_form(mode="continue") is the main form
    save. The RBE main form has a "Save" button, not "Save & Continue".
    Without this fix the save loop looks for "Continue" first and fails.

    Safety: only applies when plan has BOTH click("New ...") AND click("Continue").
    VS Tournament and other "save & continue" flows use edit_row (not "New X"),
    so has_new_click stays False and this normalizer never fires for them.
    """
    import re as _re

    has_new_click = any(
        s.get("action") == "click"
        and _re.search(r"\bnew\b", str(s.get("target", "")), _re.IGNORECASE)
        for s in plan
    )
    if not has_new_click:
        return plan

    has_click_continue = any(
        s.get("action") == "click"
        and str(s.get("target", "")).lower().strip() == "continue"
        for s in plan
    )
    if not has_click_continue:
        return plan

    result = []
    for step in plan:
        if step.get("action") == "save_form" and step.get("mode") == "continue":
            step = dict(step)
            step["mode"] = "save"
            print(
                "   🔧 NEW-EVENT: Normalized save_form(continue) → save_form(save) "
                "in create-new flow (main form uses Save not Save & Continue)"
            )
        result.append(step)
    return result


def _inject_missing_tab_click_before_save(plan, user_command=""):
    """
    Parse user_command for "Bấm vào tab X" / "Click tab X" patterns and inject
    click("X") before the corresponding save_form when it's missing.

    Uses a feature-context map so "Contest Superstars" is only injected before
    a save_form that follows a navigate to RBE (not in FCV3 or other features).
    "PVE" is already handled by _inject_fcv3_pve_tab_click; this fixer is the
    fallback for all other tabs.
    """
    import re as _re

    # Map: tab name (lower) → navigate-path substrings that indicate right feature context
    _TAB_FEATURE_CONTEXT = {
        "contest superstars": ["rbe", "rules based event", "rules based tournament"],
        "define schedules": ["rbe", "rules based event"],
        "pvp": ["fight card v3", "tournament"],
    }

    tab_re = _re.compile(
        r"(?:b[aấ]m\s+v[aà]o\s+tab|click\s+tab|v[aà]o\s+tab|b[aấ]m\s+tab)\s+([\w\s]+?)(?:\s*->|\s*$)",
        _re.IGNORECASE,
    )
    tabs_required = [m.group(1).strip() for m in tab_re.finditer(user_command)]
    if not tabs_required:
        return plan

    result = list(plan)

    for tab_name in tabs_required:
        tab_lower = tab_name.lower()
        context_keywords = _TAB_FEATURE_CONTEXT.get(tab_lower, [])

        # Already in the plan somewhere?
        if any(
            s.get("action") == "click"
            and str(s.get("target", "")).strip().lower() == tab_lower
            for s in result
        ):
            continue

        # Find the right save_form to inject before:
        # It must come after a navigate whose path matches the feature context.
        inject_idx = None
        in_right_context = not context_keywords  # no context required → any save_form works

        for j, s in enumerate(result):
            if s.get("action") == "navigate":
                path_str = " ".join(str(p).lower() for p in (s.get("path") or []))
                if context_keywords:
                    in_right_context = any(kw in path_str for kw in context_keywords)
                else:
                    in_right_context = True

            if s.get("action") == "save_form" and s.get("mode") != "clone" and in_right_context:
                # Make sure there's no click(tab) between last navigate and this save_form
                has_click = False
                for k in range(j - 1, -1, -1):
                    if result[k].get("action") == "click" and str(result[k].get("target", "")).strip().lower() == tab_lower:
                        has_click = True
                        break
                    if result[k].get("action") == "navigate":
                        break
                if not has_click:
                    inject_idx = j
                    break

        if inject_idx is not None:
            result.insert(inject_idx, {"action": "click", "target": tab_name})
            print(
                f"   🔧 TAB-CLICK: Injected click('{tab_name}') before save_form "
                f"(from command, context: {context_keywords or 'any'})"
            )

    return result


def _inject_fcv3_pve_tab_click(plan):
    """
    Inject click("PVE") before update_form containing FCV3 PVE tab fields
    (RBE Event, Contest Superstar ID) when in a Fight Card V3 context
    and no click("PVE") precedes the update_form.

    FCV3 has multiple tabs. PVE-specific fields are only reachable after
    clicking the "PVE" tab — the AI consistently forgets this step.
    """
    _FCV3_PVE_KEYS = {"rbe event", "contest superstar id"}

    result = []
    for step in plan:
        if (
            step.get("action") == "update_form"
            and isinstance(step.get("data"), dict)
            and any(str(k).strip().lower() in _FCV3_PVE_KEYS for k in step["data"].keys())
        ):
            # Is the most recent navigate pointing at Fight Card V3?
            in_fcv3 = False
            for s in reversed(result):
                if s.get("action") == "navigate":
                    path = s.get("path", [])
                    if isinstance(path, list):
                        in_fcv3 = any("fight card v3" in str(p).lower() for p in path)
                    break
                if s.get("action") == "process_deployment":
                    break

            if in_fcv3:
                # Already have click("PVE") since the last edit_row/navigate?
                has_pve_click = False
                for s in reversed(result):
                    if (
                        s.get("action") == "click"
                        and str(s.get("target", "")).strip().upper() == "PVE"
                    ):
                        has_pve_click = True
                        break
                    if s.get("action") in ("navigate", "edit_row", "clone_row"):
                        break

                if not has_pve_click:
                    result.append({"action": "click", "target": "PVE"})
                    print("   🔧 FCV3: Injected click('PVE') before PVE-tab update_form")

        result.append(step)

    return result


def _fix_restriction_slot_misclassified_as_edit_row(plan):
    """
    Fix "Edit Restriction Slot N, sửa Group M: [...]" misread as
    edit_row(target="Restriction Slot N") -> update_form({"Group M": "..."})
    instead of a single update_form({"Restriction Slot N": "Group M: [...]"})
    — the shape `_handle_restriction_slot_edit` (automation special-case)
    expects.

    The AI (esp. fast-mode Qwen) treats "Edit Restriction Slot N" as a
    click/edit_row action and "Group M" as an unrelated field, because there's
    no table row named "Restriction Slot N" — it's a fieldset+modal on the
    CURRENT page. Left as-is, edit_row crashes ("row not found") since there's
    no table on a single-entity edit form.
    """
    import re as _re
    import json as _json

    if not plan:
        return plan

    _SLOT_RE = _re.compile(r"^\s*restriction\s*slot\s*(\d+)\s*$", _re.IGNORECASE)
    _GROUP_KEY_RE = _re.compile(r"^\s*group\s*(\d+)\s*$", _re.IGNORECASE)

    result = []
    i = 0
    while i < len(plan):
        step = plan[i]

        is_slot_edit_row = (
            step.get("action") in ("edit_row", "click")
            and bool(_SLOT_RE.match(str(step.get("target", ""))))
        )

        if is_slot_edit_row and i + 1 < len(plan) and plan[i + 1].get("action") == "update_form":
            slot_num = _SLOT_RE.match(str(step.get("target", ""))).group(1)
            slot_key = f"Restriction Slot {slot_num}"
            nxt_data = plan[i + 1].get("data") or {}

            group_key = None
            group_val = None
            for k, v in nxt_data.items():
                m = _GROUP_KEY_RE.match(str(k))
                if m:
                    group_key = m.group(1)
                    group_val = v
                    break

            if group_key is not None:
                # Rebuild the item list whether the value is still bracketed
                # JSON or was already flattened to a comma string by the
                # earlier "list string" normalizer (STEP 2, runs first).
                raw = str(group_val).strip()
                items = None
                if raw.startswith("[") and raw.endswith("]"):
                    try:
                        items = _json.loads(raw)
                    except Exception:
                        items = None
                if items is None:
                    items = [p.strip() for p in raw.split(",") if p.strip()]

                spec = f"Group {group_key}: {_json.dumps(items, ensure_ascii=False)}"
                merged_data = dict(nxt_data)
                for k in list(merged_data.keys()):
                    if _GROUP_KEY_RE.match(str(k)):
                        merged_data.pop(k)
                merged_data[slot_key] = spec

                print(
                    f"   🔧 AUTO-FIX: '{step.get('action')}(\"{step.get('target')}\")' + "
                    f"update_form({{'Group {group_key}': ...}}) → update_form({{'{slot_key}': '{spec}'}})"
                )
                result.append({"action": "update_form", "data": merged_data})
                i += 2
                continue

        result.append(step)
        i += 1

    return result


def _resolve_same_as_field_reference(plan):
    """
    Resolve "Giống như <Field>" / "same as <Field>" placeholder VALUES in
    update_form data to the literal value <Field> already has elsewhere in the
    plan (e.g. "Display Name: Giống như Boss ID" should become the actual
    auto-generated ID typed into the clone modal's "New Boss ID" field).

    Without this, the AI has to re-derive the literal string purely from prose
    context with zero prompt guidance and zero safety net — this makes it
    deterministic instead.

    Search order: scan backward from the current step (inclusive of the
    current step's OTHER keys, in case the AI didn't split clone-modal fields
    into their own update_form), matching key names loosely (a "New " prefix
    is stripped so "New Boss ID" matches a reference to "Boss ID"). The
    nearest earlier match wins. Only ever rewrites values matching the
    trigger phrase; everything else is untouched.
    """
    import re as _re

    _SAME_AS_RE = _re.compile(
        r"^\s*(?:gi[ốo]ng\s+nh[ưu]|same\s+as)\s+(.+?)\s*$",
        _re.IGNORECASE,
    )

    def _normalize_key(k):
        k = str(k).strip().lower()
        if k.startswith("new "):
            k = k[4:].strip()
        return k

    for i, step in enumerate(plan):
        if step.get("action") != "update_form":
            continue
        data = step.get("data")
        if not isinstance(data, dict):
            continue

        for key, value in list(data.items()):
            if not isinstance(value, str):
                continue
            m = _SAME_AS_RE.match(value)
            if not m:
                continue

            ref_field = _normalize_key(m.group(1))
            resolved = None

            for j in range(i, -1, -1):
                prev = plan[j]
                if prev.get("action") != "update_form":
                    continue
                prev_data = prev.get("data")
                if not isinstance(prev_data, dict):
                    continue
                for pk, pv in prev_data.items():
                    if j == i and pk == key:
                        continue  # never resolve from itself
                    if (
                        _normalize_key(pk) == ref_field
                        and isinstance(pv, str)
                        and pv.strip()
                        and not _SAME_AS_RE.match(pv)
                    ):
                        resolved = pv
                        break
                if resolved:
                    break

            if resolved:
                print(
                    f"   🔧 SAME-AS: '{key}': '{value}' → '{resolved}' "
                    f"(resolved from earlier field '{ref_field}')"
                )
                data[key] = resolved
            else:
                print(
                    f"   ⚠️ SAME-AS: could not resolve '{value}' for '{key}' — "
                    f"no earlier field matching '{ref_field}' found"
                )

    return plan


def _merge_pve_css_update_steps(plan):
    """
    Merge ALL consecutive update_form steps where the first contains 'Contest Superstar'
    and the following ones contain CSS panel fields (Normal Node 1, Hard Node 1,
    Hell Node 1, RBE, SoftCurrency) into a single update_form.

    Problem: AI splits PVE CSS setup into one update_form PER FIELD instead of one
    combined call, e.g.:
      update_form({'Contest Superstar': 'on', 'RBE': ...})
      update_form({'Normal Node 1': ...})
      update_form({'SoftCurrency': ...})
      update_form({'Hard Node 1': ...})
      update_form({'SoftCurrency': ...})
      update_form({'Hell Node 1': ...})
      update_form({'SoftCurrency': ...})
    Only the FIRST of these triggers the special-case handler (it requires a
    'contest superstar' key); every subsequent standalone call falls through to
    the generic field finder, which searches literally for a label like
    "Hard Node 1" that doesn't exist in the DOM (real labels are just "Node 1"
    grouped under a "Hard" section header) -> 0 candidates found -> hangs/retries.

    Fix: Keep merging every following update_form step as long as ITS keys match
    the CSS panel pattern (not just the immediate next one), so the special-case
    handler processes the toggle + all panel data together in one call.
    """
    import re

    _CSS_PANEL_KEY_RE = re.compile(
        r"(normal|hard|hell)\s*node\s*1|^rbe$|\brbe\b|soft.?currency",
        re.IGNORECASE,
    )

    merged = []
    i = 0
    while i < len(plan):
        step = plan[i]
        if (
            step.get("action") == "update_form"
            and isinstance(step.get("data"), dict)
            and any(
                "contest superstar" in str(k).lower() for k in step["data"].keys()
            )
        ):
            combined_data = dict(step["data"])
            merged_count = 1
            j = i + 1
            while True:
                # Skip over bare wait steps (no data)
                while (
                    j < len(plan)
                    and plan[j].get("action") == "wait"
                    and not plan[j].get("data")
                ):
                    j += 1

                if j >= len(plan) or plan[j].get("action") != "update_form":
                    break

                nxt_data = plan[j].get("data") or {}
                has_panel_keys = any(
                    _CSS_PANEL_KEY_RE.search(str(k)) for k in nxt_data.keys()
                )
                if not has_panel_keys:
                    break

                combined_data.update(nxt_data)
                merged_count += 1
                j += 1

            if merged_count > 1:
                print(
                    f"   🔧 MERGE PVE-CSS: Combined {merged_count} update_form steps "
                    f"into one (keys: {list(combined_data.keys())})"
                )
                merged.append({"action": "update_form", "data": combined_data})
                i = j
            else:
                merged.append(step)
                i += 1
        else:
            merged.append(step)
            i += 1

    return merged


_DELETE_ALL_TASKS_TARGET_RE = re.compile(
    r"(xo[aá]\s*(t[aấ]t\s*c[aả])?\s*(c[aá]c)?\s*task|"
    r"delete\s*all\s*tasks?|remove\s*all\s*tasks?|clear\s*all\s*tasks?)",
    re.IGNORECASE,
)


def _fix_delete_all_tasks_misclassified_as_click(plan):
    """
    Fix "Xóa tất cả các task" / "Delete all tasks" misread as a literal
    click(target="Delete All Tasks") — there is no such button on the RBE
    Tasks tab, only a per-task trash icon, so the click fails with "Cannot
    find clickable element" and the whole run stops.

    The AI (esp. fast-mode) treats an instruction phrase as if it named a
    clickable UI element, the same class of mistake as filter/checkbox
    misclassification elsewhere in this module. Rewrite any click/select
    step whose target matches a delete-all-tasks phrase into the dedicated
    {"action": "delete_all_tasks"} step, which the automation layer
    (RbeTaskPanelMixin.delete_all_tasks) handles by repeatedly clicking each
    task's own trash icon until only Task 1 remains.
    """
    if not plan:
        return plan

    result = []
    changed = False
    for step in plan:
        action = step.get("action")
        target = str(step.get("target", "") or "")
        if action in ("click", "select") and _DELETE_ALL_TASKS_TARGET_RE.search(target):
            print(
                f"   🔧 FIX: '{action}(target=\"{target}\")' misclassified as click "
                f"→ delete_all_tasks"
            )
            result.append({"action": "delete_all_tasks"})
            changed = True
        else:
            result.append(step)

    if changed:
        return result
    return plan


