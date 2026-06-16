# automation/table_handler/table_filter.py - split from table_handler.py
# Filter/search table data, locate data table, wait for rows
import time
import re
import random


class TableFilterMixin:
    """Filter/search table data, locate data table, wait for rows"""

    def _ensure_liveoptest_items_visible(self, page):
        """Auto-uncheck 'Hide LiveopsTest gate items' checkbox if present and checked."""
        try:
            result = page.evaluate("""
                () => {
                    // Direct hit by the exact checkbox id/name (Django: id=hide-liveops-test-gate
                    // name=hide_liveops_test_gate). MUST target it directly — the page also has a
                    // 'hide_delete_gate' checkbox right before it, and the label is a bare text node
                    // (not a <label>/<span>), so a text-based ancestor search grabs the WRONG box.
                    const direct = document.querySelector(
                        'input[type="checkbox"][name*="liveops_test"],'
                        + 'input[type="checkbox"][name*="liveopstest"],'
                        + 'input[type="checkbox"][id*="liveops-test"],'
                        + 'input[type="checkbox"][id*="liveopstest"]'
                    );
                    if (direct) {
                        if (direct.checked) { direct.click(); return true; }
                        return false;
                    }
                    // Fallback: text-based search for Vue/BootstrapVue pages with different markup
                    const allEls = document.querySelectorAll('label, span, div');
                    for (const el of allEls) {
                        if (!/hide liveo[p]?stest/i.test(el.textContent || '')) continue;
                        if (!el.offsetParent) continue;
                        let chk = el.querySelector('input[type="checkbox"]');
                        if (!chk && el.previousElementSibling && el.previousElementSibling.tagName === 'INPUT')
                            chk = el.previousElementSibling;
                        if (!chk) chk = el.parentElement && el.parentElement.querySelector('input[type="checkbox"]');
                        if (chk && chk.checked) {
                            // Click the label/wrapper so Vue/BootstrapVue event handlers fire.
                            // For Django GET forms clicking the label only changes DOM state
                            // (no page reload) — Filter button submission handles the reload.
                            const clickTarget = (el.tagName === 'LABEL')
                                ? el
                                : (el.querySelector('label') || el.closest('label') || el);
                            clickTarget.click();
                            return true;
                        }
                        if (chk && !chk.checked) return false;
                    }
                    return null;
                }
            """)
            if result is True:
                print("   🔓 Auto-unchecked 'Hide LiveopsTest gate items'")
                # Small pause for any DOM updates; caller's _wait_for_long_loading handles spinners.
                # Do NOT call wait_for_load_state here — for Django GET forms the checkbox click
                # itself does NOT navigate; only the Filter submit does.
                time.sleep(0.5)
        except Exception as e:
            print(f"   ⚠️ _ensure_liveoptest_items_visible: {e}")

    def _auto_filter_data(self, page, keyword):
        # _ensure_liveoptest_items_visible is intentionally NOT called here.
        # It is already called in _click_icon_in_row before the first JS row search,
        # so calling it again would trigger a second AJAX reload and stale DOM issues.
        # Callers that invoke _auto_filter_data directly (e.g. handle_checkbox) do NOT
        # go through _click_icon_in_row, so they still need the uncheck — those callers
        # should call _ensure_liveoptest_items_visible themselves before calling here.
        if hasattr(self, "_wait_for_long_loading"):
            try:
                self._wait_for_long_loading(page)
            except Exception:
                pass
        try:
            search_input = None

            # Strategy 0: JS-based fill for Django filterbox (bypasses is_visible() issues).
            # For pages like Offer Section, the event_id input may fail Playwright's
            # visibility check even though it exists in the DOM (e.g. inside a collapsed
            # filterbox or obscured by select2 z-index). We set the value directly via JS
            # and then use Playwright only to click the submit button.
            try:
                fill_result = page.evaluate(
                    """(keyword) => {
                        const selectors = [
                            "input[name='event_id']",
                            "input#event-id",
                            "input[id*='event-id']",
                            "input[name*='event_id']",
                            // Offer Section (Django filterbox): field is name=contains id=id_contains
                            "input#id_contains",
                            "input[name='contains']",
                            "input[id*='contains']",
                            "input[name*='contains']"
                        ];
                        // Re-uncheck "Hide LiveopsTest gate items" in the SAME pass so the
                        // checkbox is guaranteed unchecked at submit time. The earlier
                        // uncheck in _click_icon_in_row is lost when the Django GET filter
                        // form navigates/reloads (checkbox reverts to its default = checked),
                        // which hides the just-cloned LiveOpsTest row from the filter result.
                        let uncheckedHide = false;
                        // Direct hit by exact id/name — the page also has a 'hide_delete_gate'
                        // checkbox and the label is a bare text node, so target this box directly.
                        const hideChk = document.querySelector(
                            'input[type="checkbox"][name*="liveops_test"],'
                            + 'input[type="checkbox"][name*="liveopstest"],'
                            + 'input[type="checkbox"][id*="liveops-test"],'
                            + 'input[type="checkbox"][id*="liveopstest"]'
                        );
                        if (hideChk && hideChk.checked) {
                            hideChk.click();
                            uncheckedHide = true;
                        }
                        for (const sel of selectors) {
                            const inp = document.querySelector(sel);
                            if (inp) {
                                // Use native setter so framework binding picks it up
                                const setter = Object.getOwnPropertyDescriptor(
                                    window.HTMLInputElement.prototype, 'value'
                                ).set;
                                setter.call(inp, keyword);
                                inp.dispatchEvent(new Event('input', {bubbles: true}));
                                inp.dispatchEvent(new Event('change', {bubbles: true}));
                                return {ok: true, sel: sel, name: inp.name, id: inp.id,
                                        uncheckedHide: uncheckedHide};
                            }
                        }
                        // Debug: dump all inputs so we can see what's available
                        const allInputs = Array.from(
                            document.querySelectorAll('input[type="text"], input:not([type])')
                        ).map(i => ({n: i.name, id: i.id, vis: i.offsetParent !== null,
                                     ph: i.placeholder, cls: i.className.slice(0, 30)}));
                        return {ok: false, inputs: allInputs};
                    }""",
                    keyword,
                )
                if fill_result and fill_result.get("ok"):
                    sel = fill_result.get("sel", "")
                    inp_name = fill_result.get("name", "")
                    inp_id = fill_result.get("id", "")
                    print(f"      👉 JS-filled event_id input: sel={sel} name={inp_name} id={inp_id}")
                    if fill_result.get("uncheckedHide"):
                        print("      🔓 Re-unchecked 'Hide LiveopsTest gate items' before filter submit")
                    # Grab the locator for the submit button. Use the SAME robust
                    # selectors as the visible-input path below — the RBE "Filter Data"
                    # button is a <button>/<a> (NOT input[type=submit]/button[type=submit]),
                    # so the old narrow list never matched it and the filter never applied.
                    _submit_clicked = False
                    for submit_sel in [
                        "button#btn-filter",
                        "input[type='submit'][value*='Filter']",
                        ".filterbox input[type='submit']",
                        ".filterbox button[type='submit']",
                        ".filterbox button:has-text('Filter')",
                        "form[method='get'] input[type='submit']",
                        "button:has-text('Filter Data')",
                        "button:has-text('Filter')",
                        "a.btn:has-text('Filter')",
                        "input[type='submit']",
                        "button[type='submit']",
                    ]:
                        try:
                            loc = page.locator(submit_sel)
                            if loc.count() > 0 and loc.first.is_visible():
                                loc.first.click()
                                _submit_clicked = True
                                print(f"      🔘 Clicked submit: {submit_sel}")
                                break
                        except Exception:
                            pass
                    if not _submit_clicked:
                        # Fallback: submit the form that actually CONTAINS the filled
                        # input (inp.form) — the old fallback only knew .filterbox/section
                        # forms, so RBE's filter form (different action) was never submitted.
                        submitted = page.evaluate(
                            """(sel) => {
                                const inp = document.querySelector(sel);
                                const form = (inp && inp.form) ||
                                             document.querySelector(".filterbox form") ||
                                             document.querySelector("form[action*='section']") ||
                                             document.querySelector("form[method='get']");
                                if (form) { form.submit(); return true; }
                                return false;
                            }""",
                            sel,
                        )
                        print(f"      🔘 JS form.submit() fallback (submitted={submitted})")
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    time.sleep(0.5)
                    return True
                elif fill_result and not fill_result.get("ok"):
                    # Debug: no input found, dump what is there
                    inputs = fill_result.get("inputs", [])
                    print(f"      ⚠️ JS fill: no event_id input found. All text inputs:")
                    for i in inputs:
                        print(f"         name={i.get('n')} id={i.get('id')} vis={i.get('vis')} ph='{i.get('ph')}' cls={i.get('cls')}")
            except Exception as e:
                print(f"      ⚠️ JS fill strategy failed: {e}")

            # Strategy 1: exact name/id attribute — most reliable, no DOM traversal.
            # Handles Django filterboxes (e.g. Offer Section: input has NO placeholder).
            # IMPORTANT: call .count() on the BASE locator, not on .first, to avoid
            # Playwright's .first.count() always returning 1 regardless of match.
            for sel in [
                "input[name='event_id']",
                "input#event-id",
                "input[id*='event-id']",
                "input[name*='event_id']",
                "input[id*='filter-id']",
                "input[name*='filter_id']",
                # Offer Section (Django filterbox): field is name=contains id=id_contains
                "input#id_contains",
                "input[name='contains']",
                "input[id*='contains']",
                "input[name*='contains']",
            ]:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        search_input = loc.first
                        print(f"      👉 Found ID filter input via selector: {sel}")
                        break
                except Exception:
                    pass

            # Strategy 2: ".input-group-text" label containing "ID" → adjacent input
            # (Bootstrap .input-group layout used by most Vue-based pages).
            if not search_input:
                try:
                    for lbl in page.locator(
                        ".input-group-text, .input-group-prepend .input-group-text"
                    ).all():
                        if not lbl.is_visible():
                            continue
                        if not re.search(r"\bid\b", lbl.inner_text(), re.IGNORECASE):
                            continue
                        grp = lbl.locator(
                            "xpath=ancestor::div[contains(@class,'input-group')]"
                        ).first
                        inp = grp.locator("input[type='text'], input:not([type])").first
                        if inp.count() > 0 and inp.is_visible():
                            search_input = inp
                            print(f"      👉 Found ID Contains via input-group label")
                            break
                except Exception:
                    pass

            # Strategy 3: placeholder text
            if not search_input:
                for p in ["ID Contains", "ID", "Search", "Name", "Filter", "Title"]:
                    try:
                        inp = page.get_by_placeholder(re.compile(p, re.IGNORECASE))
                        if inp.count() > 0 and inp.first.is_visible():
                            search_input = inp.first
                            print(f"      👉 Found ID filter input via placeholder: {p}")
                            break
                    except Exception:
                        pass

            # Strategy 4: first visible text input inside known filter containers.
            # Exclude .chosen-search-input / select2 search boxes — on pages like Offer
            # Section the Gate dropdown's chosen-search-input is the FIRST visible text
            # input in .filterbox, so a bare input[type='text'] would grab it instead of
            # the real ID Contains field and filter on an empty keyword.
            _not_dropdown_search = (
                ":not(.chosen-search-input):not(.select2-search__field)"
                ":not([class*='multiselect'])"
            )
            if not search_input:
                for container in [".filterbox", ".filter-box", ".card-header", ".card-body"]:
                    try:
                        loc = page.locator(
                            f"{container} input[type='text']{_not_dropdown_search}"
                        )
                        if loc.count() > 0 and loc.first.is_visible():
                            search_input = loc.first
                            print(
                                f"      👉 Found ID filter input in container: {container}"
                            )
                            break
                    except Exception:
                        pass

            # Strategy 5 (last resort): first visible text input on the whole page
            if not search_input:
                try:
                    loc = page.locator(
                        f"input[type='text']{_not_dropdown_search}:visible"
                    )
                    if loc.count() > 0 and loc.first.is_visible():
                        search_input = loc.first
                        print(f"      👉 Found ID filter input via first visible text input")
                except Exception:
                    pass

            if search_input and search_input.is_visible():
                # Re-uncheck "Hide LiveopsTest gate items" right before submit (idempotent —
                # only clicks if currently checked). Guards the Django GET-form case where
                # the box reverted to checked after an earlier navigation, which would hide
                # the just-cloned LiveOpsTest row from the filter result.
                self._ensure_liveoptest_items_visible(page)
                print(f"      👉 Auto Filter: '{keyword}'")
                search_input.fill(keyword)
                time.sleep(0.2)

                # Submit: use Playwright locator (NOT page.evaluate + element_handle) to
                # avoid "Execution context was destroyed" when the submit click navigates
                # the page (e.g. Django GET form at /offers/section/).
                _filter_clicked = False
                try:
                    # Walk up to the ancestor <form> and find its submit control
                    _form_loc = search_input.locator("xpath=ancestor::form")
                    if _form_loc.count() > 0:
                        _submit = _form_loc.locator(
                            "input[type='submit'], button[type='submit'], button"
                        ).first
                        if _submit.count() > 0 and _submit.is_visible():
                            _submit.click()
                            _filter_clicked = True
                            print(f"      🔘 Clicked Filter button (form submit)")
                except Exception:
                    pass

                if not _filter_clicked:
                    try:
                        _filter_btn = page.locator(
                            "button#btn-filter, button:has-text('Filter'), "
                            "a.btn:has-text('Filter'), input[type='submit'][value='Filter']"
                        ).first
                        if _filter_btn.count() > 0 and _filter_btn.is_visible():
                            _filter_btn.click()
                            _filter_clicked = True
                            print(f"      🔘 Clicked Filter button")
                    except Exception:
                        pass

                if not _filter_clicked:
                    search_input.press("Enter")
                    print(f"      🔘 Pressed Enter to filter")

                # Wait for both AJAX reload and full GET-form navigation
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                time.sleep(0.5)
                return True
        except Exception as e:
            print(f"      ⚠️ _auto_filter_data error: {e}")
        return False

    def wait_for_table_data(self, page, timeout=10):
        """Chờ bảng có dữ liệu"""
        s = time.time()
        while time.time() - s < timeout:
            if page.locator("tbody tr").count() > 0:
                return True
            time.sleep(0.5)
        return False

    def _find_data_table(self, page):
        """Tìm bảng chứa checkbox (loại bỏ bảng layout/header)"""
        tables = page.locator("table").all()
        for tbl in tables:
            if not tbl.is_visible():
                continue
            if tbl.locator("tbody tr input[type='checkbox']").count() > 0:
                return tbl
        return page.locator("table").last

    def _perform_table_filter(self, page, col_name, value):
        """Tự động điền Filter và bấm nút"""
        self._ensure_liveoptest_items_visible(page)
        # 1. Tìm Input
        search_input = None
        placeholders = [f"{col_name} Contains", f"{col_name}", "Search", "Filter", "ID"]

        for p in placeholders:
            inp = page.get_by_placeholder(re.compile(p, re.IGNORECASE)).first
            if inp.is_visible():
                search_input = inp
                print(f"      👉 Found Filter Input: '{p}'")
                break

        if not search_input:
            search_input = page.locator(
                ".filter-box input, .card-header input, input.form-control"
            ).first

        if search_input and search_input.is_visible():
            search_input.fill(str(value))

            # 2. Bấm nút Filter
            btn = (
                page.locator("button, a.btn")
                .filter(has_text=re.compile("Filter|Search|Go", re.IGNORECASE))
                .first
            )
            if not btn.is_visible():
                btn = page.locator(
                    "button:has(i.fa-search), button:has(i.fa-filter)"
                ).first

            if btn.is_visible():
                btn.click()
            else:
                search_input.press("Enter")

            # Chờ reload
            time.sleep(2.0)
            page.wait_for_load_state("networkidle")
            return True

        return False

    # ============================
    # DRAG-AND-DROP REORDER
    # ============================
