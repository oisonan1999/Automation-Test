# automation/form_handler/rbe_task_panel.py
# RBE "Tasks" tab special-case handler.
#
# The RBE Tasks tab renders a repeated card per task ("Task 1", "Task 2", ...).
# EVERY control inside a card carries a stable `name="pm[<idx>][<field>]"`
# attribute where idx = TaskNumber - 1 (verified 1:1 ordered on the live page).
# This makes the whole tab deterministically fillable by name — no fragile
# label/section heuristics needed — as long as the AI keys are shaped
# "Task <N> <FieldLabel>".
#
# Handled fields (per task N, idx = N-1):
#   Condition            -> select2  pm[idx][CompletionCondition]   (option value == text, e.g. "Signpost")
#   Description / Loc /
#     Signpost ID        -> select2  pm[idx][PointTypeDescription]  (localization picker)
#   Count                -> number   pm[idx][CompletionCount]
#   Complete Type 1/2/3  -> text     pm[idx][CompletionType1..3]    (opens shared #ctype-modal)
#   Default Score        -> number   pm[idx][Score]
#   Link / Deeplink      -> text     pm[idx][deeplink]
#   Link Start Time      -> flatpickr pm[idx][start_time]
#   Link End Time        -> flatpickr pm[idx][end_time]
#   League Min / Min     -> select   pm[idx][min_league]            (options 1..24)
#   League Max / Max     -> select   pm[idx][max_league]
#   Attempt              -> number   pm[idx][attempt]
#   Is hidden            -> checkbox pm[idx][is_hidden]             (custom switch)
#   Accumulated          -> checkbox pm[idx][accumulated]          (custom switch)
#
# The shared Complete-Type modal (#ctype-modal) has:
#   #complete-type-category        (category select, e.g. PVP / PVE Book / Chapter)
#   #complete-type-value           (select2 value dropdown, populated from category)
#   #complete-type-value-integer   (number input, shown for numeric types, class d-none otherwise)
#   .btn-save-ctype                (Save changes)
# On save the app writes "<category>:<value>" back into the CompletionTypeX input.

import re
import time


class RbeTaskPanelMixin:
    """Fills the RBE Tasks-tab per-task cards by `pm[idx][field]` name."""

    def delete_all_tasks(self, page):
        """RBE Tasks-tab: delete every task card except Task 1.

        Each task card (Task 2+) has a trash-icon button
        (`button.btn-remove-task-item`); Task 1 has NO such button — it's the
        one card the app never lets you remove, so "delete all tasks" means
        "delete down to Task 1". Deleting a row is an immediate, uncommitted
        DOM change (removes the card from the page's local task array); it is
        only sent to the server on the main form Save.

        Click the LAST remove button repeatedly (removing from the end avoids
        any index-shift surprises from removing a middle row) until either no
        remove buttons remain, or the visible Task 1 stays as the sole card.
        No confirmation dialog appears — verified live.
        """
        try:
            before = page.locator("b.task-num").count()
        except Exception:
            before = None
        print(f"      🗑️ [RBE Task] Delete All Tasks: starting (visible tasks={before})")

        removed = 0
        max_clicks = 500  # hard safety cap; a real RBE never has this many tasks
        for _ in range(max_clicks):
            btn = page.locator("button.btn-remove-task-item").last
            try:
                if btn.count() == 0:
                    break
                btn.scroll_into_view_if_needed()
                btn.click(force=True)
                removed += 1
                time.sleep(0.25)
            except Exception as e:
                print(f"         ⚠️ [RBE Task] delete click failed, stopping: {e}")
                break

        try:
            after = page.locator("b.task-num").count()
        except Exception:
            after = None
        print(
            f"      🗑️ [RBE Task] Delete All Tasks: removed {removed} task(s), "
            f"{before} -> {after} remaining"
        )
        return [
            {
                "step": "Delete All Tasks",
                "status": "PASS" if (after is None or after <= 1) else "WARNING",
                "details": f"removed {removed} task(s); {before} -> {after} remaining",
            }
        ]

    # ── Field label → resolver spec ────────────────────────────────────────
    # Each entry: normalized-label-regex -> (kind, pm_field, [extra])
    # Resolved dynamically in _rbe_task_resolve_field so aliases stay in one place.

    def _rbe_task_field_spec(self, field_label):
        """Map a per-task field label to (kind, pm_field, meta).

        kind ∈ {condition, loc, select, number, text, datetime, toggle, ctype}
        Returns None if the label isn't a recognized RBE-task field.
        """
        f = re.sub(r"[\s_]+", " ", str(field_label).lower()).strip()

        # Complete Type slot: "complete type 1", "type 2", "completion type 3"
        m = re.match(r"(?:complete|completion)?\s*type\s*([123])$", f)
        if m:
            return ("ctype", f"CompletionType{m.group(1)}", {"slot": int(m.group(1))})

        if f in ("condition", "completion condition", "complete condition"):
            return ("condition", "CompletionCondition", {})

        if f in (
            "description",
            "loc",
            "localization",
            "signpost id",
            "signpost",
            "point type description",
            "point type",
            "loc description",
            "condition description",
            "condition loc",
            "condition localization",
        ):
            return ("loc", "PointTypeDescription", {})

        if f in ("count", "completion count", "complete count"):
            return ("number", "CompletionCount", {})

        if f in ("default score", "score"):
            return ("number", "Score", {})

        if f in ("attempt", "attempts"):
            return ("number", "attempt", {})

        if f in ("link", "deeplink", "deep link"):
            return ("text", "deeplink", {})

        if f in (
            "link start time",
            "start time",
            "start date time",
            "start",
            "start time utc",
            "link start",
        ):
            return ("datetime", "start_time", {})

        if f in (
            "link end time",
            "end time",
            "end date time",
            "end",
            "end time utc",
            "link end",
        ):
            return ("datetime", "end_time", {})

        if f in ("league min", "min league", "min", "league minimum"):
            return ("select", "min_league", {})

        if f in ("league max", "max league", "max", "league maximum"):
            return ("select", "max_league", {})

        if f in ("is hidden", "hidden", "ishidden"):
            return ("toggle", "is_hidden", {})

        if f in ("accumulated", "accumulate", "is accumulated"):
            return ("toggle", "accumulated", {})

        return None

    def _handle_rbe_task_panel(self, page, data):
        """RBE Tasks-tab special-case. Fills every "Task <N> <field>" key by
        `pm[idx][field]` name, popping handled keys from `data` so the generic
        loop skips them. Never hard-fails the whole automation.

        Only runs when: (a) data has at least one "Task <N> ..." key AND
        (b) the page actually has pm[...] task inputs. Otherwise no-op.
        """
        try:
            if not isinstance(data, dict):
                return

            # Detect candidate keys: "Task 3 Condition", "task 12 is hidden", ...
            task_key_re = re.compile(r"^\s*task\s+(\d+)\s+(.+)$", re.IGNORECASE)
            candidates = []
            for k in list(data.keys()):
                m = task_key_re.match(str(k))
                if m:
                    candidates.append((k, int(m.group(1)), m.group(2).strip()))

            if not candidates:
                return

            # Guard: only act on a page that has the RBE task cards.
            try:
                if page.locator("input[name^='pm['], select[name^='pm[']").count() == 0:
                    print(
                        "         ℹ️ [RBE Task] 'Task N' keys present but no pm[] "
                        "inputs on page — leaving for generic fill."
                    )
                    return
            except Exception:
                return

            print(
                f"         🗂️ [RBE Task] special-case entered "
                f"({len(candidates)} task field(s))"
            )

            # Process condition FIRST for each task (revealing dependent fields
            # like PointTypeDescription/Complete Types), then the rest.
            def _order_key(item):
                _, _, field = item
                spec = self._rbe_task_field_spec(field)
                kind = spec[0] if spec else "z"
                # condition(0) < loc(1) < other fields(2) < complete-types(3, by slot).
                # Complete Types LAST and in ascending slot order because Type 2/3
                # only render after Type 1 (and the right condition) are set.
                if kind == "ctype":
                    return (3, spec[2].get("slot", 9))
                return ({"condition": 0, "loc": 1}.get(kind, 2), 0)

            candidates.sort(key=_order_key)

            for orig_key, task_num, field_label in candidates:
                value = data.get(orig_key)
                spec = self._rbe_task_field_spec(field_label)
                if spec is None:
                    print(
                        f"         ⚠️ [RBE Task] Unknown field '{field_label}' "
                        f"(Task {task_num}) — leaving for generic fill."
                    )
                    continue

                kind, pm_field, meta = spec
                idx = task_num - 1
                sel = f"[name='pm[{idx}][{pm_field}]']"

                print(
                    f"         ↳ [RBE Task {task_num}] {field_label} "
                    f"-> pm[{idx}][{pm_field}] = '{value}'"
                )

                ok = False
                try:
                    if kind == "condition":
                        ok = self._rbe_task_set_select2(page, sel, value)
                    elif kind == "loc":
                        ok = self._rbe_task_set_loc(page, sel, value)
                    elif kind == "select":
                        ok = self._rbe_task_set_native_select(page, sel, value)
                    elif kind == "number" or kind == "text":
                        ok = self._rbe_task_fill_input(page, sel, value)
                    elif kind == "datetime":
                        ok = self._rbe_task_fill_datetime(page, sel, value)
                    elif kind == "toggle":
                        ok = self._rbe_task_set_toggle(page, sel, value)
                    elif kind == "ctype":
                        ok = self._rbe_task_set_complete_type(
                            page, idx, meta["slot"], value
                        )
                except Exception as e:
                    print(f"         ⚠️ [RBE Task] fill error for '{orig_key}': {e}")

                # Pop the key regardless so the generic loop doesn't re-attempt
                # (generic finder can't locate these labels — it returns 0 candidates).
                data.pop(orig_key, None)
                if ok:
                    print(f"            ✅ [RBE Task] set '{field_label}'")
                else:
                    print(f"            ⚠️ [RBE Task] could not set '{field_label}'")

        except Exception as e:
            print(f"         ⚠️ [RBE Task] handler aborted: {e}")

    # ── Field setters ──────────────────────────────────────────────────────

    def _rbe_task_set_select2(self, page, sel, value):
        """Set a select2-backed <select> whose option value == text (Condition)."""
        val = str(value).strip()
        loc = page.locator(f"select{sel}").first
        if loc.count() == 0:
            return False
        loc.scroll_into_view_if_needed()
        try:
            # Native + jQuery/select2 change trigger so dependent UI updates.
            done = loc.evaluate(
                """(el, want) => {
                    const wantL = String(want).toLowerCase().trim();
                    let matched = null;
                    for (const o of el.options) {
                        if (o.value.toLowerCase().trim() === wantL ||
                            o.text.toLowerCase().trim() === wantL) { matched = o.value; break; }
                    }
                    if (matched === null) {
                        for (const o of el.options) {
                            if (o.text.toLowerCase().includes(wantL) && o.value) { matched = o.value; break; }
                        }
                    }
                    if (matched === null) return false;
                    el.value = matched;
                    if (window.jQuery) {
                        window.jQuery(el).val(matched).trigger('change');
                    } else {
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                    return true;
                }""",
                val,
            )
            time.sleep(0.6)
            return bool(done)
        except Exception:
            return False

    def _rbe_task_set_loc(self, page, sel, value):
        """Set the localization/description select2 (PointTypeDescription).

        The value is a localization key (e.g. '!!R44_TASK_WIN_DESCRIPT') that
        must already exist as a choosable option in the app's AJAX-backed
        localization list (this widget picks EXISTING loc entries; it is not a
        free-text creator). Try exact option match first (covers the case
        where the option is already preloaded on the page); else open the
        select2 search and look it up via AJAX.
        """
        val = str(value).strip()
        loc = page.locator(f"select{sel}").first
        if loc.count() == 0:
            return False
        loc.scroll_into_view_if_needed()

        # 1) Exact/partial existing-option match (fast path — only works when
        #    the <select> already has this option preloaded, e.g. it's the
        #    value the page loaded with).
        try:
            matched = loc.evaluate(
                """(el, want) => {
                    const wantL = String(want).toLowerCase().trim();
                    let m = null;
                    for (const o of el.options) {
                        if (o.value.toLowerCase().trim() === wantL ||
                            o.text.toLowerCase().trim() === wantL) { m = o.value; break; }
                    }
                    if (m === null) {
                        for (const o of el.options) {
                            if (o.text.toLowerCase().includes(wantL) && o.value) { m = o.value; break; }
                        }
                    }
                    if (m === null) return false;
                    el.value = m;
                    if (window.jQuery) window.jQuery(el).val(m).trigger('change');
                    else el.dispatchEvent(new Event('change', {bubbles:true}));
                    return true;
                }""",
                val,
            )
            if matched:
                time.sleep(0.4)
                try:
                    if loc.input_value().strip():
                        return True
                except Exception:
                    return True
        except Exception:
            pass

        # 2) Open the select2 search UI and look the key up via AJAX. The
        #    search box's query is triggered by REAL keystroke events —
        #    `.fill()` (a single synthetic 'input' dispatch) is silently
        #    ignored on the FIRST search of a session (shows "Please enter 1
        #    or more characters" even though the field visibly contains the
        #    text) — verified live. `press_sequentially()` (real per-char
        #    keydown/keyup) reliably triggers the AJAX query every time.
        try:
            wrapper = loc.locator(
                "xpath=following-sibling::span[contains(@class,'select2')][1]"
            ).first
            if wrapper.count() == 0:
                wrapper = loc.locator(
                    "xpath=preceding-sibling::span[contains(@class,'select2')][1]"
                ).first
            if wrapper.count() > 0:
                wrapper.click()
                time.sleep(0.6)
                search = page.locator(
                    ".select2-container--open input.select2-search__field"
                ).first
                if search.count() > 0:
                    search.press_sequentially(val, delay=25)
                    time.sleep(2.0)  # allow AJAX results

                    # Prefer an option whose text starts with "<val> (" (exact
                    # loc-key match, app renders "<key> (<preview text>)") over
                    # whatever happens to be first/highlighted — multiple keys
                    # can share a prefix (e.g. ..._WIN_DESCRIPT vs
                    # ..._WIN_DESCRIPT_DEFAULT).
                    val_lower = val.lower()
                    exact_opt = page.locator(
                        ".select2-container--open .select2-results__option"
                        ":not([aria-disabled='true'])"
                    ).filter(
                        has_text=re.compile(
                            r"^" + re.escape(val) + r"(\s*\(|$)", re.IGNORECASE
                        )
                    ).first
                    if exact_opt.count() > 0:
                        exact_opt.click()
                    else:
                        page.keyboard.press("Enter")
                    time.sleep(0.6)
        except Exception as e:
            print(f"            ⚠️ [RBE Task] loc search failed: {e}")

        # Verify write-back — this widget only picks EXISTING options, so a
        # key with no matching AJAX result leaves the select empty; report
        # that honestly instead of a blind success.
        try:
            written = loc.input_value().strip()
        except Exception:
            written = ""
        if written:
            return True
        print(
            f"            ⚠️ [RBE Task] loc key '{val}' not found via search "
            f"(this field only selects EXISTING localization entries, it "
            f"cannot create a new one)"
        )
        return False

    def _rbe_task_set_native_select(self, page, sel, value):
        """Set a plain native <select> (min_league / max_league) by value/label."""
        val = str(value).strip()
        # Normalize "League 7" -> "7"
        m = re.search(r"(\d+)", val)
        num = m.group(1) if m else val
        loc = page.locator(f"select{sel}").first
        if loc.count() == 0:
            return False
        loc.scroll_into_view_if_needed()
        for arg in ({"value": num}, {"label": num}, {"value": val}, {"label": val}):
            try:
                loc.select_option(**arg)
                # Ensure change event for any dependent listeners.
                loc.evaluate(
                    "el => { if(window.jQuery){window.jQuery(el).trigger('change');} "
                    "else {el.dispatchEvent(new Event('change',{bubbles:true}));} }"
                )
                return True
            except Exception:
                continue
        return False

    def _rbe_task_fill_input(self, page, sel, value):
        """Fill a plain number/text input by name."""
        val = re.sub(r"[\[\]'\"]", "", str(value)).strip()
        loc = page.locator(f"input{sel}").first
        if loc.count() == 0:
            return False
        loc.scroll_into_view_if_needed()
        try:
            loc.fill("")
            loc.fill(val)
            loc.evaluate(
                "el => el.dispatchEvent(new Event('change', {bubbles:true}))"
            )
            return True
        except Exception:
            try:
                loc.evaluate(
                    "(el, v) => { el.value = v; "
                    "el.dispatchEvent(new Event('input',{bubbles:true})); "
                    "el.dispatchEvent(new Event('change',{bubbles:true})); }",
                    val,
                )
                return True
            except Exception:
                return False

    # Formats accepted for RBE Task Link Start/End Time input, tried in order.
    # The on-page value is ALWAYS "YYYY-MM-DD HH:MM:SS" (flatpickr dateFormat
    # "Y-m-d H:i:S" — verified live), but the AI/command may hand us MM/DD/YYYY,
    # with/without comma, with/without AM/PM, or the ISO form itself.
    _RBE_TASK_DT_FORMATS = (
        "%m/%d/%Y %I:%M %p",
        "%m/%d/%Y, %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y, %H:%M",
        "%m/%d/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    def _rbe_task_parse_datetime(self, value):
        """Flexibly parse a Task Link Start/End Time value. Returns a
        datetime.datetime or None if unparseable."""
        from datetime import datetime as _dt

        val = re.sub(r"[\[\]'\"]", "", str(value)).strip()
        # 00:MM AM/PM -> 12:MM AM/PM (datetime.strptime rejects hour 00 with %I).
        val = re.sub(r"(\s)00:(\d{2})(\s*)(AM|PM)", r"\g<1>12:\2\3\4", val, flags=re.IGNORECASE)
        for fmt in self._RBE_TASK_DT_FORMATS:
            try:
                return _dt.strptime(val, fmt)
            except Exception:
                continue
        return None

    def _rbe_task_fill_datetime(self, page, sel, value):
        """Fill a flatpickr start/end input by name.

        The field is `readonly` with flatpickr `dateFormat: "Y-m-d H:i:S"`.
        Passing a raw STRING to `flatpickr.setDate()` makes flatpickr parse it
        using ITS OWN configured dateFormat tokens — feeding it an MM/DD/YYYY
        string (or any format flatpickr wasn't told to expect) silently
        misparses into a garbage date (verified live: "07/21/2026 11:00" fed
        as a raw string produced "2026-10-31 00:00:00", a full 3 months off,
        with NO error). The generic per-page format-detector
        (`_detect_input_datetime_format`) also doesn't recognize this field's
        own "YYYY-MM-DD HH:MM:SS" display format, so it never reformats the
        value first either — the raw AI string reaches flatpickr unchanged.

        Fix: parse the value into (y, mo, d, h, mi, s) ourselves in Python,
        then construct the date via `new Date(y, mo, d, h, mi, s)` with
        NUMERIC arguments in JS — this bypasses flatpickr's string date-format
        parser entirely, so there is no ambiguity regardless of what format
        the AI/command used. Verified live against the exact repro case.
        """
        loc = page.locator(f"input{sel}").first
        if loc.count() == 0:
            return False

        parsed = self._rbe_task_parse_datetime(value)
        if parsed is None:
            print(
                f"            ⚠️ [RBE Task] could not parse datetime '{value}' "
                f"(tried MM/DD/YYYY[, HH:MM[ AM/PM]] and YYYY-MM-DD HH:MM[:SS])"
            )
            return False

        try:
            loc.evaluate(
                """(el, [y, moZeroBased, d, h, mi, s]) => {
                    el.removeAttribute('readonly');
                    const dateObj = new Date(y, moZeroBased, d, h, mi, s);
                    if (el._flatpickr) {
                        el._flatpickr.setDate(dateObj, true);
                    } else {
                        el.value = dateObj.toISOString();
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                    }
                }""",
                [parsed.year, parsed.month - 1, parsed.day, parsed.hour, parsed.minute, parsed.second],
            )
            time.sleep(0.3)
        except Exception as e:
            print(f"            ⚠️ [RBE Task] datetime JS-set failed: {e}")
            return False

        # Verify the write-back actually reflects the intended value (catches
        # any residual flatpickr quirk instead of reporting a false success).
        try:
            written = loc.input_value().strip()
        except Exception:
            written = None
        expected_date = parsed.strftime("%Y-%m-%d")
        if written and written.startswith(expected_date):
            return True
        print(
            f"            ⚠️ [RBE Task] datetime write-back mismatch: "
            f"expected date '{expected_date}', got '{written}'"
        )
        return False

    def _rbe_task_set_toggle(self, page, sel, value):
        """Set a custom-switch checkbox (is_hidden / accumulated) to on/off."""
        want_on = str(value).lower().strip() in (
            "true", "1", "on", "yes", "enable", "enabled", "checked", "show", "hidden"
        )
        # NOTE: for is_hidden, "hidden"/"on"/"yes" => checked. "off"/"false"/"no" => unchecked.
        if str(value).lower().strip() in ("off", "false", "0", "no", "disable", "disabled", "unchecked", "visible"):
            want_on = False

        cb = page.locator(f"input{sel}").first
        if cb.count() == 0:
            return False
        cb.scroll_into_view_if_needed()
        try:
            cur = cb.is_checked()
        except Exception:
            cur = None

        if cur is not None and cur == want_on:
            return True  # already in desired state

        # App business rule: some toggles are disabled by design for the current
        # condition (e.g. Signpost-condition tasks cannot be hidden → is_hidden
        # is disabled). Never force a disabled toggle — the app would reject it
        # on save. Report the reason so it isn't mistaken for an automation bug.
        try:
            if cb.is_disabled():
                print(
                    f"            🚫 [RBE Task] toggle '{sel}' is DISABLED by the app "
                    f"for this task's condition — cannot set to "
                    f"{'ON' if want_on else 'OFF'} (skipping; not a bug)."
                )
                return True
        except Exception:
            pass

        # Custom switches hide the real input; click the associated label if present.
        try:
            cb_id = cb.get_attribute("id")
        except Exception:
            cb_id = None
        clicked = False
        if cb_id:
            lbl = page.locator(f"label[for='{cb_id}']").first
            if lbl.count() > 0:
                try:
                    lbl.click(force=True)
                    clicked = True
                except Exception:
                    clicked = False
        if not clicked:
            try:
                cb.click(force=True)
                clicked = True
            except Exception:
                try:
                    cb.evaluate("el => el.click()")
                    clicked = True
                except Exception:
                    clicked = False
        time.sleep(0.3)
        try:
            return cb.is_checked() == want_on
        except Exception:
            return clicked

    def _rbe_task_set_complete_type(self, page, idx, slot, value):
        """Open the shared #ctype-modal for pm[idx][CompletionType{slot}], set the
        category + value dropdowns, and Save changes.

        `value` accepts: "Category:Value", "Category / Value", "Category > Value",
        or just "Category" (value defaults to same). For numeric types, put the
        number as the value part (goes into #complete-type-value-integer).
        """
        raw = str(value).strip()
        parts = re.split(r"\s*[:/>|]\s*", raw, maxsplit=1)
        category = parts[0].strip()
        cval = parts[1].strip() if len(parts) > 1 else category

        # 1) Open modal by clicking the CompletionType input for this task.
        trigger = page.locator(
            f"input[name='pm[{idx}][CompletionType{slot}]']"
        ).first
        if trigger.count() == 0:
            print(f"            ⚠️ [RBE Task] CompletionType{slot} input not found")
            return False

        # Type 2/3 only render for certain condition + Type-1 combos (the app's
        # renderTaskCompleteType2/3). If the slot input is hidden, this Type isn't
        # valid for the current task state — skip cleanly instead of force-clicking
        # a display:none element (which throws). Give the render a moment first,
        # since Type-1's change/save is what reveals later slots.
        for _ in range(6):
            try:
                if trigger.is_visible():
                    break
            except Exception:
                pass
            time.sleep(0.4)
        try:
            if not trigger.is_visible():
                print(
                    f"            🚫 [RBE Task] Complete Type {slot} is HIDDEN for this "
                    f"task's condition + Type-1 combo (app only shows it for specific "
                    f"combinations) — skipping (not a bug)."
                )
                return True
        except Exception:
            pass

        trigger.scroll_into_view_if_needed()
        try:
            trigger.click(force=True)
        except Exception:
            trigger.evaluate("el => el.click()")

        modal = page.locator("#ctype-modal").first
        try:
            modal.wait_for(state="visible", timeout=5000)
        except Exception:
            print("            ⚠️ [RBE Task] #ctype-modal did not open")
            return False

        # 2) Wait for the category dropdown to be (re)populated for THIS slot.
        #    The modal is shared across slots and its category options reload
        #    ASYNCHRONOUSLY per slot+condition (app onClickCompleteTypeHandler
        #    awaits setupCompleteTypeCategorySelection). Selecting before the
        #    slot-specific options land (e.g. Type-1's pvp/book/... still present
        #    when we want Type-2's superstar/group) silently fails. Poll until an
        #    option matching our category token (by value OR text) exists.
        cat_sel = page.locator("#complete-type-category").first
        cat_ok = False
        resolved_value = None
        if cat_sel.count() > 0:
            deadline = time.time() + 6.0
            while time.time() < deadline:
                try:
                    resolved_value = cat_sel.evaluate(
                        """(el, want) => {
                            const wantL = String(want).toLowerCase().trim();
                            for (const o of el.options) {
                                if (o.value.toLowerCase().trim() === wantL) return o.value;
                            }
                            for (const o of el.options) {
                                if (o.text.toLowerCase().trim() === wantL) return o.value;
                            }
                            for (const o of el.options) {
                                if (o.value && o.text.toLowerCase().includes(wantL)) return o.value;
                            }
                            return null;
                        }""",
                        category,
                    )
                except Exception:
                    resolved_value = None
                if resolved_value is not None:
                    break
                time.sleep(0.3)

            if resolved_value is not None:
                # Set via JS with a NATIVE dispatchEvent('change') so the app's
                # vanilla addEventListener('change') fires (jQuery .trigger alone
                # does NOT — verified live). Use JS rather than Playwright
                # select_option because for Type 3 the category <select> is a
                # hidden select2 (aria-hidden) and select_option refuses hidden
                # elements. Also fire jQuery trigger for any jQuery-bound handlers.
                try:
                    cat_sel.evaluate(
                        """(el, v) => {
                            el.value = v;
                            el.dispatchEvent(new Event('change', {bubbles:true}));
                            if (window.jQuery) window.jQuery(el).val(v).trigger('change');
                        }""",
                        resolved_value,
                    )
                    cat_ok = True
                except Exception:
                    cat_ok = False
            else:
                _avail = []
                try:
                    _avail = cat_sel.evaluate(
                        "el => [...el.options].map(o => o.value+'='+o.text)"
                    )
                except Exception:
                    pass
                print(
                    f"            ⚠️ [RBE Task] category '{category}' not available for "
                    f"Complete Type {slot} (options: {_avail})"
                )
        time.sleep(1.0)  # let value options / integer field toggle

        # 3) Set value. Two kinds of value control depending on the category:
        #    (a) integer input (#complete-type-value-integer, shown for
        #        is_integer_input categories like damage) — fill it directly;
        #    (b) value select2 (#complete-type-value) — the save handler reads
        #        #complete-type-value.val(). Rather than drive the flaky select2
        #        search UI (which can't match numeric enum values like
        #        event_type:1 whose text is "Limited Time"), set the native
        #        <select> programmatically: append the option if absent, set
        #        .value, and fire native + jQuery change. The app runs a
        #        server-side combo-validation on Save that accepts the value if it
        #        is valid for the category — verified live for pvp/superstar/
        #        group/event_id/event_type. Value stores as "<category>:<value>".
        val_int = page.locator("#complete-type-value-integer").first
        int_visible = False
        try:
            int_visible = val_int.count() > 0 and val_int.is_visible()
        except Exception:
            int_visible = False

        # Canonicalize the pvp:pvp-style case: when the value equals the category
        # (case-insensitively), the real stored value is the category's canonical
        # option value (e.g. user "PVP:PVP" → "pvp:pvp", matching existing data)
        # rather than the user's raw casing.
        if resolved_value and cval and cval.lower() == category.lower():
            cval = resolved_value

        val_ok = False
        if int_visible and re.fullmatch(r"-?\d+", cval or ""):
            try:
                val_int.fill("")
                val_int.fill(cval)
                val_int.evaluate(
                    "el => el.dispatchEvent(new Event('change',{bubbles:true}))"
                )
                val_ok = True
            except Exception:
                val_ok = False
        else:
            try:
                val_sel = page.locator("#complete-type-value").first
                if val_sel.count() > 0:
                    val_sel.evaluate(
                        """(el, cval) => {
                            if (![...el.options].some(o => o.value === cval)) {
                                const opt = new Option(cval, cval, true, true);
                                el.appendChild(opt);
                            }
                            el.value = cval;
                            el.dispatchEvent(new Event('change', {bubbles:true}));
                            if (window.jQuery) window.jQuery(el).val(cval).trigger('change');
                        }""",
                        cval,
                    )
                    time.sleep(0.4)
                    try:
                        cur = val_sel.input_value()
                        val_ok = bool(cur and cur.strip())
                    except Exception:
                        val_ok = True
            except Exception:
                val_ok = False

        # 4) Save changes. The app runs an AJAX combo-validation on save; if the
        #    category+value pair is invalid for the task's condition it clears the
        #    input and shows "Invalid combination!". So the real success signal is
        #    the written-back input value, not the click.
        save_btn = page.locator("#ctype-modal .btn-save-ctype").first
        if save_btn.count() > 0:
            try:
                save_btn.click(force=True)
            except Exception:
                save_btn.evaluate("el => el.click()")
        try:
            modal.wait_for(state="hidden", timeout=5000)
        except Exception:
            time.sleep(0.8)
        time.sleep(0.5)

        # Read back the actual stored value ("<category>:<value>" or app-specific).
        try:
            written = trigger.input_value()
        except Exception:
            written = None
        if written and written.strip():
            print(f"            🧩 [RBE Task] Complete Type{slot} = '{written}'")
            return True
        print(
            f"            ⚠️ [RBE Task] Complete Type{slot} not written "
            f"(invalid category:value for this condition?) — cat_ok={cat_ok}, val_ok={val_ok}"
        )
        return False
