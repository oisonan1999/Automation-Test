# automation/form_handler/dropdown_handler.py - split from form_handler.py
# select2 / chosen / vue-multiselect dropdown handling
import time
import re
import random
from playwright.sync_api import Page


class DropdownHandlerMixin:
    """select2 / chosen / vue-multiselect dropdown handling"""

    def _try_select_option_by_select_option_text(self, page, option_text):
        """
        Select option trong bất kỳ <select> nào mà option text khớp với option_text.
        Hữu ích khi AI truyền kiểu key='Gold' -> value='select' (option-as-value),
        trong khi UI thực tế chỉ là dropdown.
        """
        try:
            if option_text is None:
                return False

            option_norm = re.sub(r"\s+", " ", str(option_text)).strip().lower()

            # Collect all selects (can be hidden)
            selects = page.locator("select").all()
            if not selects:
                return False

            # Candidates: selects có option text match (exact/normalized)
            candidates = []
            for sel in selects:
                try:
                    opts = sel.locator("option").all()
                    for opt in opts:
                        try:
                            t = (opt.inner_text() or "").strip()
                            t_norm = re.sub(r"\s+", " ", t).strip().lower()
                            if t_norm == option_norm:
                                candidates.append(sel)
                                break
                        except:
                            continue
                except:
                    continue

            # Try sequentially
            for sel in candidates:
                try:
                    if self._fill_element_smartly(page, sel, option_text):
                        return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"         ⚠️ _try_select_option_by_select_option_text error: {e}")
            return False

    def _try_set_select2_option_by_option_text(self, page, option_text):
        """
        Fallback: thử set select2/chosen dropdown bằng cách:
        - mở từng select2 selection (visible)
        - scan các `.select2-results__option` đang visible
        - nếu text match exact -> click
        """
        try:
            if option_text is None:
                return False

            option_norm = re.sub(r"\s+", " ", str(option_text)).strip().lower()
            if not option_norm:
                return False

            # Candidate select2 containers
            containers = page.locator(
                "span.select2-container, span.select2-selection"
            ).all()

            for cont in containers:
                try:
                    if not cont.is_visible():
                        continue
                except:
                    continue

                # Open dropdown
                try:
                    cont.click(force=True)
                except:
                    continue

                time.sleep(0.25)

                matched = False
                try:
                    matched = page.evaluate(
                        "(valueNorm) => {"
                        "  const norm = (s) => (s||'').toString().replace(/\\s+/g,' ').trim().toLowerCase();"
                        "  const opts = document.querySelectorAll('.select2-results__option, .select2-results__option[role=\"option\"]');"
                        "  for (const o of opts) {"
                        "    try {"
                        "      const rect = o.getBoundingClientRect();"
                        "      if (rect.width <= 0 || rect.height <= 0) continue;"
                        "      const t = norm(o.textContent);"
                        "      if (t === valueNorm) { o.click(); return true; }"
                        "    } catch (e) {}"
                        "  }"
                        "  return false;"
                        "}",
                        option_norm,
                    )
                except:
                    matched = False

                # Close dropdown regardless
                try:
                    page.keyboard.press("Escape")
                except:
                    pass

                if matched:
                    return True

            return False
        except Exception as e:
            print(f"         ⚠️ _try_set_select2_option_by_option_text error: {e}")
            return False

            # Collect all selects (can be hidden)
            selects = page.locator("select").all()
            if not selects:
                return False

            # Candidates: selects có option text match (exact/normalized)
            candidates = []
            for sel in selects:
                try:
                    opts = sel.locator("option").all()
                    for opt in opts:
                        try:
                            t = (opt.inner_text() or "").strip()
                            t_norm = re.sub(r"\s+", " ", t).strip().lower()
                            if t_norm == option_norm:
                                candidates.append(sel)
                                break
                        except:
                            continue
                except:
                    continue

            # Try fill sequentially
            for sel in candidates:
                try:
                    if self._fill_element_smartly(page, sel, option_text):
                        return True
                except:
                    continue

            return False
        except Exception as e:
            print(f"         ⚠️ _try_select_option_by_select_option_text error: {e}")
            return False

    def _find_custom_dropdown_wrapper(self, hidden_select):
        """Tìm thẻ bao (Wrapper) hiển thị của Select2 hoặc Chosen.js"""
        try:
            sel_id = hidden_select.get_attribute("id")

            # 1. Tìm theo ID Biến thể (Quan trọng cho Chosen)
            # ID gốc: clone-gate -> Chosen ID: clone_gate_chosen (dấu - thành _)
            if sel_id:
                # Case A: ID gốc + _chosen (Chuẩn Chosen)
                chosen_id = f"#{sel_id}_chosen"
                chosen_by_id = hidden_select.page.locator(chosen_id).first
                if chosen_by_id.count() > 0 and chosen_by_id.is_visible():
                    return chosen_by_id

                # Case B: Thay '-' thành '_' rồi + _chosen (Fix lỗi ID của bạn)
                alt_id = sel_id.replace("-", "_") + "_chosen"
                alt_chosen = hidden_select.page.locator(f"#{alt_id}").first
                if alt_chosen.count() > 0 and alt_chosen.is_visible():
                    return alt_chosen

                # Case C: Select2 container ID
                s2_id = f"#select2-{sel_id}-container"
                s2_container = hidden_select.page.locator(s2_id).first
                if s2_container.count() > 0 and s2_container.is_visible():
                    # Trả về cha của container (là .select2-container)
                    s2_parent = s2_container.locator(
                        "xpath=ancestor::span[contains(@class,'select2-container')]"
                    ).first
                    if s2_parent.count() > 0:
                        return s2_parent

            # 2. Tìm theo Sibling (Ngay bên cạnh)
            # Chosen: div.chosen-container
            chosen_sib = hidden_select.locator(
                "xpath=following-sibling::div[contains(@class, 'chosen-container')]"
            ).first
            if chosen_sib.count() > 0 and chosen_sib.is_visible():
                return chosen_sib

            # Select2: span.select2-container
            select2_sib = hidden_select.locator(
                "xpath=following-sibling::span[contains(@class, 'select2-container')]"
            ).first
            if select2_sib.count() > 0 and select2_sib.is_visible():
                return select2_sib

            # Vue Multiselect: div.multiselect
            multiselect_sib = hidden_select.locator(
                "xpath=following-sibling::div[contains(@class, 'multiselect')]"
            ).first
            if multiselect_sib.count() > 0 and multiselect_sib.is_visible():
                return multiselect_sib

            # 3. Tìm trong cùng parent container (Parent search)
            # Wrapper có thể nằm cùng parent với SELECT nhưng không phải sibling trực tiếp
            try:
                parent = hidden_select.locator("xpath=..").first
                if parent.count() > 0:
                    # Tìm wrapper trong parent
                    wrappers_in_parent = parent.locator(
                        "div.chosen-container, span.select2-container, div.multiselect"
                    ).all()

                    for wrapper in wrappers_in_parent:
                        if wrapper.is_visible():
                            return wrapper
            except:
                pass

            # 4. Global search gần SELECT (trong vòng 200px)
            # Last resort: Tìm wrapper gần vị trí SELECT
            try:
                sel_box = hidden_select.bounding_box()
                if sel_box:
                    all_wrappers = hidden_select.page.locator(
                        "div.chosen-container:visible, span.select2-container:visible, div.multiselect:visible"
                    ).all()

                    for wrapper in all_wrappers:
                        try:
                            w_box = wrapper.bounding_box()
                            if w_box:
                                # Kiểm tra khoảng cách
                                x_diff = abs(w_box["x"] - sel_box["x"])
                                y_diff = abs(w_box["y"] - sel_box["y"])

                                # Wrapper thường nằm cùng vị trí với SELECT
                                if x_diff < 200 and y_diff < 100:
                                    return wrapper
                        except:
                            continue
            except:
                pass

        except Exception as e:
            print(f"         ⚠️ Wrapper search error: {e}")

        return None

    def _try_set_select2_multiselect_by_placeholder(self, page, placeholder, value):
        """
        Select2 multiselect handler using placeholder to find the correct search input.
        Then locate its parent select2 container and reuse _handle_js_dropdown (multiselect).
        """
        try:
            value_str = str(value).strip()
            if not value_str:
                return False

            # Find the select2 search input by placeholder
            search_input = page.locator(
                f"input.select2-search__field[placeholder='{placeholder}']"
            ).first
            if search_input.count() == 0:
                # fallback: contains placeholder (some UIs localize or truncate)
                search_input = (
                    page.locator("input.select2-search__field")
                    .filter(has_text=placeholder)
                    .first
                )
            if search_input.count() == 0:
                # final fallback: match placeholder attr contains
                search_input = (
                    page.locator("input.select2-search__field")
                    .filter(
                        has=page.locator(
                            f"xpath=ancestor::*[contains(@placeholder, '{placeholder}') ]"
                        )
                    )
                    .first
                )

            if search_input.count() == 0:
                return False

            # The clickable container is typically the nearest select2 container/span
            # e.g. span.select2-selection--multiple
            container = search_input.locator(
                "xpath=ancestor::span[contains(@class,'select2-selection')]"
            ).first
            if container.count() == 0:
                container = search_input.locator(
                    "xpath=ancestor::*[contains(@class,'select2-container') or contains(@class,'select2-selection')]"
                ).first
            if container.count() == 0:
                return False

            if not container.is_visible():
                # even if hidden, force click should work inside select2
                pass

            # Reuse dropdown handler. For select2 multiselect, treat as 'select2'
            return self._handle_js_dropdown(page, container, value_str, "select2")
        except Exception as e:
            print(f"         ⚠️ _try_set_select2_multiselect_by_placeholder error: {e}")
            return False

    def _handle_js_dropdown(self, page, container, value, lib_type="chosen"):
        try:
            value_str = str(value).strip()
            clicked_exact = False
            # 1. Click mở dropdown
            container.scroll_into_view_if_needed()

            if lib_type == "chosen":
                trigger = container.locator("a.chosen-single, span").first
                if trigger.is_visible():
                    trigger.click(force=True)
                else:
                    container.click(force=True)
            elif lib_type == "multiselect":
                trigger = container.locator(
                    ".multiselect__input, .multiselect__tags"
                ).first
                if trigger.is_visible():
                    trigger.click(force=True)
                else:
                    container.click(force=True)
            else:
                # Select2: always use force=True to bypass modal backdrop / overlay
                container.click(force=True)

            # ========================================
            # 2. CHỜ DROPDOWN OPTIONS LOAD XONG
            # [PERF] Dùng JS evaluate thay vì .all() + .is_visible() trên từng element
            # Với 2500+ options, cách cũ tạo hàng nghìn round-trip → ~60s. JS evaluate chỉ 1 call → <1s
            # ========================================
            print(f"         ⏳ Waiting for dropdown options to load...")
            wait_start = time.time()
            max_wait = 3  # Chờ tối đa 3 giây
            options_loaded = False
            visible_count = 0

            while time.time() - wait_start < max_wait:
                try:
                    if lib_type == "chosen":
                        # Single JS call: check open state + count options
                        info = container.evaluate("""el => {
                            const cls = el.className || '';
                            const isOpen = cls.includes('chosen-with-drop');
                            const drop = el.querySelector('.chosen-drop');
                            const count = drop ? drop.querySelectorAll('li.active-result').length : 0;
                            return {isOpen: isOpen, count: count};
                        }""")
                        if not info.get("isOpen"):
                            print(f"         🔄 Dropdown not open yet, waiting...")
                        visible_count = info.get("count", 0)
                    elif lib_type == "multiselect":
                        visible_count = page.evaluate("""() => {
                            const opts = document.querySelectorAll('.multiselect__element, .multiselect__option');
                            let c = 0;
                            for (const o of opts) { if (o.offsetParent !== null) c++; }
                            return c;
                        }""")
                    else:
                        visible_count = page.evaluate("""() => {
                            const opts = document.querySelectorAll('.select2-results__option');
                            let c = 0;
                            for (const o of opts) { if (o.offsetParent !== null) c++; }
                            return c;
                        }""")

                    if visible_count > 0:
                        print(
                            f"         ✅ Dropdown loaded ({visible_count} options visible)"
                        )
                        options_loaded = True
                        break
                except:
                    pass
                time.sleep(0.3)

            if not options_loaded:
                print(
                    f"         ⚠️ Dropdown options may not be fully loaded, continuing anyway..."
                )
                # [FIX] For Select2 inside modals: force-open via jQuery API
                # because force=True click doesn't fire Select2's JS event handlers
                if lib_type == "select2":
                    try:
                        print(f"         🔧 Trying jQuery select2('open') API...")
                        page.evaluate("""
                            () => {
                                if (typeof jQuery === 'undefined') return;
                                jQuery('.modal.in select, .modal.show select').each(function() {
                                    var $el = jQuery(this);
                                    if ($el.data('select2')) {
                                        try { $el.select2('open'); } catch(e) {}
                                    }
                                });
                                jQuery('select').each(function() {
                                    var $el = jQuery(this);
                                    if ($el.data('select2')) {
                                        try { $el.select2('open'); } catch(e) {}
                                    }
                                });
                            }
                        """)
                        time.sleep(0.8)
                        # Re-check with JS evaluate
                        visible_count = page.evaluate("""() => {
                            const opts = document.querySelectorAll('.select2-results__option');
                            let c = 0;
                            for (const o of opts) { if (o.offsetParent !== null) c++; }
                            return c;
                        }""")
                        if visible_count > 0:
                            options_loaded = True
                            print(
                                f"         ✅ Select2 opened via jQuery API ({visible_count} options)"
                            )
                    except Exception as _e:
                        print(f"         ⚠️ jQuery Select2 open error: {_e}")

                # ========================================
                # 3. STRATEGY A: Tìm và click TRỰC TIẾP option khớp text (không cần search)
                #    Ưu tiên exact match trước, partial match sau
                #    [FIX] Improved for simple dropdowns with no search (e.g., Bracketed/Normal)
                # ========================================

                # Guard: if multiselect currently shows only empty-state items,
                # do not continue into search/keyboard fallbacks (this is where RBE can hang).
                if lib_type == "multiselect":
                    try:
                        empty_only = container.evaluate("""(el) => {
                            const opts = Array.from(el.querySelectorAll('.multiselect__element span, .multiselect__option'))
                                .filter(o => o && o.offsetParent !== null);
                            const texts = opts.map(o => (o.textContent || '').trim()).filter(Boolean);
                            if (!texts.length) return false;
                            const emptyRe = /(no elements found|list is empty|consider changing the search query)/i;
                            return texts.every(t => emptyRe.test(t));
                        }""")
                        if empty_only:
                            print(
                                "         ⚠️ [Dropdown] Multiselect only empty-state options; returning False to avoid hang."
                            )
                            try:
                                # try closing dropdown
                                page.keyboard.press("Escape")
                            except:
                                pass
                            return False
                    except Exception as _ms_empty_e:
                        print(
                            f"         ⚠️ [Dropdown] empty-state guard check error: {_ms_empty_e}"
                        )
            all_visible_opts = []  # Chỉ dùng cho fallback keyboard navigation
            value_lower = value_str.lower().replace("_", " ").replace("-", " ")
            try:
                # [PERF] Dùng 1 lệnh JS evaluate để tìm + click option khớp text
                # Thay vì .all() + .is_visible() + .inner_text() trên từng element (hàng nghìn round-trip)
                if lib_type == "chosen":
                    result = container.evaluate(
                        """(el, value) => {
                        const options = el.querySelectorAll('.chosen-drop li.active-result');
                        if (!options.length) {
                            // Fallback: try broader selector
                            const drop = el.querySelector('.chosen-drop');
                            if (drop) {
                                const allLi = drop.querySelectorAll('li');
                                return _matchAndClick(allLi, value);
                            }
                        }
                        return _matchAndClick(options, value);

                        function _matchAndClick(opts, val) {
                            const valueLower = val.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                            const total = opts.length;
                            function chosenClick(el) {
                                // Chosen.js listens on mouseup, not click. Must dispatch full mouse event sequence.
                                el.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                                el.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                                el.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                            }
                            // Exact match first
                            for (const opt of opts) {
                                const text = opt.textContent.trim();
                                const textLower = text.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                                if (textLower === valueLower || text === val) {
                                    chosenClick(opt);
                                    return {matched: true, text: text, type: 'exact', total: total};
                                }
                            }
                            // Partial match
                            for (const opt of opts) {
                                const text = opt.textContent.trim();
                                const textLower = text.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                                if (textLower.includes(valueLower) || valueLower.includes(textLower)) {
                                    chosenClick(opt);
                                    return {matched: true, text: text, type: 'partial', total: total};
                                }
                            }
                            return {matched: false, total: total};
                        }
                    }""",
                        value_str,
                    )
                elif lib_type == "multiselect":
                    result = page.evaluate(
                        """(value) => {
                        const options = document.querySelectorAll('.multiselect__element span, .multiselect__option');
                        const valueLower = value.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                        const visible = [];
                        for (const o of options) { if (o.offsetParent !== null) visible.push(o); }
                        const total = visible.length;
                        for (const opt of visible) {
                            const text = opt.textContent.trim();
                            const textLower = text.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                            if (textLower === valueLower || text === value) {
                                opt.click();
                                return {matched: true, text: text, type: 'exact', total: total};
                            }
                        }
                        for (const opt of visible) {
                            const text = opt.textContent.trim();
                            const textLower = text.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                            if (textLower.includes(valueLower) || valueLower.includes(textLower)) {
                                opt.click();
                                return {matched: true, text: text, type: 'partial', total: total};
                            }
                        }
                        return {matched: false, total: total};
                    }""",
                        value_str,
                    )
                else:  # select2
                    result = page.evaluate(
                        """(value) => {
                        const options = document.querySelectorAll('.select2-results__option');
                        const valueLower = value.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                        const visible = [];
                        for (const o of options) { if (o.offsetParent !== null) visible.push(o); }
                        const total = visible.length;

                        // In a Clone modal, clicking a result option dispatches a body-level
                        // click event that Bootstrap interprets as "click outside modal" and
                        // dismisses the modal. Use jQuery programmatic selection instead.
                        const modalEl = document.querySelector('.modal.show, .modal.in');
                        const inCloneModal = !!(modalEl &&
                            /Clone/i.test(modalEl.innerText || modalEl.textContent || ''));

                        function selectOpt(opt) {
                            if (!inCloneModal) { opt.click(); return; }
                            const optText = (opt.textContent || '').trim();
                            let optId = optText;
                            try {
                                const d = (typeof jQuery !== 'undefined') ? jQuery(opt).data('data') : null;
                                if (d && d.id !== undefined) optId = String(d.id);
                            } catch(e) {}
                            if (optId === optText) {
                                const m = (opt.id || '').match(/select2-[^-]+-result-[^-]+-(.+)$/);
                                if (m && m[1]) optId = m[1];
                            }
                            const dropdownEl = opt.closest('.select2-dropdown');
                            let $sel = null;
                            if (typeof jQuery !== 'undefined') {
                                jQuery('select').each(function() {
                                    const s2 = jQuery(this).data('select2');
                                    if (s2 && s2.$dropdown && s2.$dropdown[0] === dropdownEl) {
                                        $sel = jQuery(this); return false;
                                    }
                                });
                                if (!$sel) jQuery('select').each(function() {
                                    const s2 = jQuery(this).data('select2');
                                    if (s2 && s2.$container && s2.$container.hasClass('select2-container--open')) {
                                        $sel = jQuery(this); return false;
                                    }
                                });
                            }
                            if (!$sel) return;
                            if (!$sel.find('option[value="' + optId + '"]').length) {
                                $sel.append(new Option(optText, optId, true, true));
                            }
                            $sel.val(optId).trigger('change');
                            try { $sel.trigger('change.select2'); } catch(e) {}
                            try { $sel.select2('close'); } catch(e) {}
                        }

                        for (const opt of visible) {
                            const text = opt.textContent.trim();
                            const textLower = text.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                            if (textLower === valueLower || text === value) {
                                selectOpt(opt);
                                return {matched: true, text: text, type: 'exact', total: total};
                            }
                        }
                        for (const opt of visible) {
                            const text = opt.textContent.trim();
                            const textLower = text.toLowerCase().replace(/_/g, ' ').replace(/-/g, ' ');
                            if (textLower.includes(valueLower) || valueLower.includes(textLower)) {
                                selectOpt(opt);
                                return {matched: true, text: text, type: 'partial', total: total};
                            }
                        }
                        return {matched: false, total: total};
                    }""",
                        value_str,
                    )

                total = result.get("total", 0)
                print(f"         📋 Found {total} visible options for direct selection")

                if result.get("matched"):
                    match_type = result.get("type", "exact")
                    match_text = result.get("text", value_str)
                    if match_type == "exact":
                        print(
                            f"         ✅ [Dropdown] Exact match clicked: '{match_text}'"
                        )
                    else:
                        print(
                            f"         ✅ [Dropdown] Partial match clicked: '{match_text}'"
                        )
                    clicked_exact = True
            except Exception as e:
                print(f"         ⚠️ Direct match error: {e}")

            if clicked_exact:
                time.sleep(0.5)
                # [FIX] Trigger change event to update dependent fields
                try:
                    if lib_type == "chosen":
                        # Find the original select element
                        select_id = container.get_attribute("id") or ""
                        if select_id and "_chosen" in select_id:
                            original_id = select_id.replace("_chosen", "")
                            page.evaluate(f"""() => {{
                                    const sel = document.getElementById('{original_id}');
                                    if (sel) {{
                                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        if (typeof jQuery !== 'undefined') {{
                                            jQuery(sel).trigger('change');
                                        }}
                                    }}
                                }}""")
                except Exception as e:
                    print(f"         ⚠️ Change event trigger warning: {e}")
                page.keyboard.press("Tab")
                return True

            # ========================================
            # 4. STRATEGY B: Dùng Search box (nếu có)
            # CHÚ Ý: Dropdowns đơn giản (VD: Bracketed/Normal) không có search box
            # ========================================
            search_box = None
            if lib_type == "chosen":
                search_box = container.locator(
                    ".chosen-drop input, .chosen-search input"
                ).first
            elif lib_type == "multiselect":
                search_box = container.locator(".multiselect__input").first
            else:
                search_box = page.locator(
                    ".select2-container--open input.select2-search__field"
                ).first

            # Check if search box exists and is visible
            has_search = False
            try:
                search_box.wait_for(state="visible", timeout=1000)
                has_search = True
            except:
                # [FIX] No search box = simple dropdown. Strategy A should have worked.
                print(
                    f"         ⚠️ No search box found. This is a simple dropdown (e.g., 2 options)."
                )
                if not clicked_exact and all_visible_opts:
                    # Last resort: Try clicking first matching option again with different approach
                    print(f"         🔄 Retrying with keyboard navigation...")
                    try:
                        # Use keyboard to navigate
                        page.keyboard.press("Home")  # Go to first option
                        for opt in all_visible_opts:
                            opt_text = opt.inner_text().strip()
                            opt_lower = (
                                opt_text.lower().replace("_", " ").replace("-", " ")
                            )
                            if value_lower in opt_lower:
                                # Navigate with arrow keys until we find it
                                page.keyboard.press("ArrowDown")
                                time.sleep(0.2)
                        page.keyboard.press("Enter")
                        print(f"         ✅ [Keyboard] Selected via navigation")
                        return True
                    except Exception as e:
                        print(f"         ⚠️ Keyboard navigation error: {e}")

            if has_search and search_box and search_box.is_visible():
                # Luôn dùng value_str gốc làm search term (giữ nguyên underscore)
                # VD: "GachaShard_Feb2026_Wknd1_Main" phải search đúng như vậy
                search_term = value_str

                search_box.fill(search_term)
                print(f"         🔍 Searching: '{search_term}'")

                # CHỜ KẾT QUẢ FILTER
                # Select2 cần 3-4s để server trả về kết quả và render dropdown
                if lib_type == "select2":
                    time.sleep(3.5)
                else:
                    time.sleep(1.0)

                # PERF/FIX:
                # Tránh polling bằng `.all()` + `is_visible()` trên từng option (cực dễ treo khi list option nhiều).
                # Ta sẽ chọn option bằng JS match/click ở các nhánh phía dưới.
                visible_results = []

                # [FIX] Click option CHÍNH XÁC nhất (không phải first blind)
                clicked = False
                if visible_results:
                    # CHỜ 2S SAU KHI CÓ SEARCH RESULT (Đảm bảo UI dropdown đã render xong)
                    print(
                        f"         ⏳ Chờ 2s để search result ổn định trước khi click..."
                    )
                    time.sleep(2)
                    value_lower = value_str.lower().replace("_", " ").replace("-", " ")
                    # Exact match first
                    for r in visible_results:
                        try:
                            r_text = r.inner_text().strip()
                            r_lower = r_text.lower().replace("_", " ").replace("-", " ")
                            if r_lower == value_lower or r_text == value_str:
                                r.click()
                                print(f"         ✅ [Dropdown] Exact match: '{r_text}'")
                                clicked = True
                                break
                        except:
                            pass
                    # Partial match
                    if not clicked:
                        for r in visible_results:
                            try:
                                r_text = r.inner_text().strip()
                                r_lower = (
                                    r_text.lower().replace("_", " ").replace("-", " ")
                                )
                                if value_lower in r_lower or r_lower in value_lower:
                                    r.click()
                                    print(
                                        f"         ✅ [Dropdown] Partial match: '{r_text}'"
                                    )
                                    clicked = True
                                    break
                            except:
                                pass
                    # Fallback: Click first result
                    # NOTE: Tránh gọi visible_results[0].inner_text() / click trực tiếp (dễ treo khi option nhiều).
                    if not clicked and visible_results:
                        try:
                            clicked_js = page.evaluate(
                                """(valueLower) => {
  const normalize = (s) => (s || "")
    .toString()
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/-/g, " ")
    .replace(/\\s+/g, " ")
    .trim();

  const target = normalize(valueLower);

  const selectors = [
    ".multiselect__element",
    ".multiselect__option",
    ".active-result",
    ".select2-results__option",
    ".chosen-results li",
    "option"
  ];

  const els = selectors
    .map(sel => Array.from(document.querySelectorAll(sel)))
    .reduce((a,b) => a.concat(b), []);

  const visible = (el) => {
    try {
      const r = el.getBoundingClientRect();
      if (!r) return false;
      if (r.width <= 0 || r.height <= 0) return false;
      const style = window.getComputedStyle(el);
      return style && style.visibility !== "hidden" && style.display !== "none";
    } catch (e) { return false; }
  };

  // Prefer exact match first
  for (const el of els) {
    if (!visible(el)) continue;
    const txt = normalize(el.innerText || el.textContent || el.getAttribute("title") || "");
    if (txt === target) {
      el.click();
      return true;
    }
  }

  // Then contains match
  for (const el of els) {
    if (!visible(el)) continue;
    const txt = normalize(el.innerText || el.textContent || el.getAttribute("title") || "");
    if (txt.includes(target) || target.includes(txt)) {
      el.click();
      return true;
    }
  }

  return false;
}""",
                                value_lower,
                            )

                            if clicked_js:
                                print(
                                    "         ⚠️ [Dropdown] Clicked option via JS match"
                                )
                                clicked = True
                            else:
                                page.keyboard.press("Enter")
                                clicked = True
                        except:
                            page.keyboard.press("Enter")
                            clicked = True
                elif not clicked:
                    # Không có kết quả nào → thử Enter
                    print(f"         ⚠️ No search results found, pressing Enter")
                    page.keyboard.press("Enter")
                    clicked = True

                if clicked:
                    print(f"         ✅ [Dropdown] Đã chọn: '{value_str}'")
            else:
                # Fallback gõ mù
                print(f"         ⌨️ Gõ phím trực tiếp: '{value_str}'")
                page.keyboard.type(value_str)
                time.sleep(1.0)
                page.keyboard.press("Enter")

            # Nhấn Tab để đóng dropdown
            time.sleep(0.5)
            page.keyboard.press("Tab")
            return True

        except Exception as e:
            print(f"         ❌ Lỗi dropdown: {e}")
            return False

    # ============================
    # VUE MULTISELECT HELPERS
    # ============================
    def _open_vue_multiselect(
        self, page, wrapper_or_input, timeout_ms: int = 3000
    ) -> bool:
        """
        Reliably open a Vue multiselect dropdown.

        Vue multiselect ignores synthetic MouseEvent dispatched from JS because
        it checks e.isTrusted.  Playwright's locator.click() DOES produce trusted
        events, but only when the element is *interactable* (visible + not covered).

        The trick: click the .multiselect__select arrow-button (always covers the
        full right-edge of the wrapper and is never zero-width), then verify the
        content-wrapper changed to display:block.

        Args:
            wrapper_or_input: either the .multiselect div (role=combobox) or the
                              hidden input[placeholder] inside it.
            timeout_ms: how long to wait for the dropdown to open.

        Returns:
            True if listbox became visible, False otherwise.
        """
        try:
            # Resolve to the [role=combobox] wrapper regardless of what was passed
            tag = wrapper_or_input.evaluate("el => el.tagName.toLowerCase()")
            if tag == "input":
                combobox = wrapper_or_input.locator(
                    "xpath=ancestor::*[@role='combobox'][1]"
                ).first
                if combobox.count() == 0:
                    combobox = wrapper_or_input.locator(
                        "xpath=ancestor::div[contains(@class,'multiselect')][1]"
                    ).first
            else:
                combobox = wrapper_or_input

            if combobox.count() == 0:
                combobox = wrapper_or_input  # last resort

            # Strategy A: click the arrow button (.multiselect__select)
            arrow = combobox.locator(".multiselect__select").first
            if arrow.count() > 0:
                try:
                    arrow.scroll_into_view_if_needed()
                    arrow.click(force=True)
                except Exception:
                    pass

            # Wait for content-wrapper display:block (Vue sets this on open)
            deadline = time.time() + timeout_ms / 1000
            while time.time() < deadline:
                try:
                    display = combobox.locator(
                        ".multiselect__content-wrapper"
                    ).first.evaluate("el => el.style.display")
                    # Vue v-show clears inline style on open → display becomes "".
                    # The wrapper is visible when display is anything other than "none".
                    if display != "none":
                        return True
                except Exception:
                    pass
                time.sleep(0.1)

            # Strategy B: click the tags area (some builds need this)
            try:
                tags = combobox.locator(".multiselect__tags").first
                if tags.count() > 0:
                    tags.click(force=True)
                deadline2 = time.time() + 1.5
                while time.time() < deadline2:
                    try:
                        display = combobox.locator(
                            ".multiselect__content-wrapper"
                        ).first.evaluate("el => el.style.display")
                        if display != "none":
                            return True
                    except Exception:
                        pass
                    time.sleep(0.1)
            except Exception:
                pass

            # Strategy C: focus the hidden input and press ArrowDown (Vue opens on ArrowDown)
            try:
                hidden_input = combobox.locator("input.multiselect__input").first
                if hidden_input.count() > 0:
                    hidden_input.evaluate("el => el.focus && el.focus()")
                    page.keyboard.press("ArrowDown")
                    time.sleep(0.4)
                    try:
                        display = combobox.locator(
                            ".multiselect__content-wrapper"
                        ).first.evaluate("el => el.style.display")
                        if display != "none":
                            return True
                    except Exception:
                        pass
            except Exception:
                pass

            return False
        except Exception as e:
            print(f"         ⚠️ [open_vue_multiselect] {e}")
            return False

    def _fill_vue_multiselect(
        self,
        page,
        combobox_scope,
        search_value: str,
        listbox_scope=None,
        timeout_s: float = 6.0,
    ) -> bool:
        """
        Type into a Vue multiselect that is already open and select a matching option.

        Why page.keyboard.type() instead of JS el.value + synthetic Event:
          - Vue's @input handler is bound to the native input's InputEvent.
          - Playwright keyboard.type() creates genuine, trusted InputEvents.
          - JS-dispatched synthetic Events are NOT trusted (isTrusted=false) and
            may be ignored by Vue 2 / vue-multiselect's internal watcher.

        Args:
            page:          Playwright page.
            combobox_scope: The div[role=combobox] element (or panel_root locator
                           that contains exactly ONE multiselect).
            search_value:  Text to type for filtering.
            listbox_scope: Where to look for the option list (defaults to page-wide
                           .multiselect__content-wrapper:visible).
            timeout_s:     How long to wait for real options to appear.

        Returns:
            True if an option was successfully clicked, False otherwise.
        """
        try:
            # 1. Find the multiselect input (may be 0-width but still focusable)
            ms_input = combobox_scope.locator("input.multiselect__input").first
            if ms_input.count() == 0:
                ms_input = combobox_scope.locator(
                    "input[placeholder*='Type' i], input[placeholder*='search' i]"
                ).first
            if ms_input.count() == 0:
                print(
                    "         ⚠️ [fill_vue_multiselect] Cannot find multiselect input"
                )
                return False

            # 2. Focus the input (required before keyboard.type)
            try:
                ms_input.evaluate("el => el.focus && el.focus()")
                time.sleep(0.15)
            except Exception:
                pass

            # 3. Clear existing value via keyboard (select-all → delete)
            try:
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                time.sleep(0.1)
            except Exception:
                pass

            # 4. Build search candidates: original → strip SS_ prefix → key tokens
            raw = str(search_value).strip()
            parts = [p for p in raw.split("_") if p]
            no_prefix = [p for p in parts if p.lower() not in ("ss",)]

            candidates: list[str] = []
            for c in [
                raw,
                " ".join(no_prefix),
                no_prefix[0] if no_prefix else "",
                parts[-1] if parts else "",
            ]:
                c = str(c).strip()
                if c and c not in candidates:
                    candidates.append(c)

            # 5. Determine listbox scope
            if listbox_scope is None:
                listbox_scope = page

            SENTINELS = re.compile(
                r"(no elements found|list is empty|consider changing)", re.IGNORECASE
            )

            def _real_options(scope):
                opts = scope.locator(
                    "span.multiselect__option, li.multiselect__element"
                ).all()
                return [
                    o
                    for o in opts
                    if o.is_visible() and not SENTINELS.search(o.inner_text())
                ]

            # 6. Try each candidate search term
            for term in candidates:
                if not term:
                    continue

                # Type via keyboard (produces real InputEvents Vue can see)
                try:
                    # Clear first
                    ms_input.evaluate(
                        "el => { if(el) { el.value=''; el.dispatchEvent(new Event('input',{bubbles:true})); } }"
                    )
                    time.sleep(0.05)
                    page.keyboard.type(term, delay=30)
                except Exception as _type_err:
                    print(
                        f"         ⚠️ keyboard.type failed: {_type_err}, falling back to JS"
                    )
                    try:
                        ms_input.evaluate(
                            "(el, v) => { el.focus&&el.focus(); el.value=v; "
                            "el.dispatchEvent(new InputEvent('input',{bubbles:true,data:v})); "
                            "el.dispatchEvent(new Event('change',{bubbles:true})); }",
                            term,
                        )
                    except Exception:
                        pass

                # 7. Poll for real options
                deadline = time.time() + timeout_s
                real_opts = []
                while time.time() < deadline:
                    real_opts = _real_options(listbox_scope)
                    if real_opts:
                        break
                    time.sleep(0.25)

                if not real_opts:
                    continue  # Try next candidate

                # 8. Click best match (exact first, then partial)
                term_lower = term.lower()
                raw_lower = raw.lower()

                best = None
                for opt in real_opts:
                    t = opt.inner_text().strip().lower()
                    if t == raw_lower or t == term_lower:
                        best = opt
                        break
                if not best:
                    for opt in real_opts:
                        t = opt.inner_text().strip().lower()
                        if term_lower in t or raw_lower in t:
                            best = opt
                            break
                if not best and real_opts:
                    best = real_opts[0]

                if best:
                    # Guard: re-check inner_text now that Vue has finished rendering.
                    # During the poll, inner_text() may return "" (async slot), letting
                    # sentinel items slip through _real_options. Recheck here before click.
                    try:
                        final_text = best.inner_text().strip()
                        if SENTINELS.search(final_text):
                            continue  # skip sentinel; try next search candidate
                    except Exception:
                        pass
                    try:
                        best.click(force=True)
                        print(
                            f"         ✅ [fill_vue_multiselect] Clicked: '{best.inner_text().strip()}'"
                        )
                        time.sleep(0.3)
                        return True
                    except Exception as _click_err:
                        print(f"         ⚠️ option click failed: {_click_err}")

            print(f"         ❌ [fill_vue_multiselect] No match for '{search_value}'")
            return False

        except Exception as e:
            print(f"         ❌ [fill_vue_multiselect] {e}")
            return False

    def _select_book_id_in_chapter_template_multiselect(
        self, page, book_id: str
    ) -> bool:
        """
        Select a BookID in the #searchChapterTemplate Vue multiselect on the
        Import/Export Chapters tab of the PVE detail page.

        HTML:  input#searchChapterTemplate.multiselect__input
               aria-controls="listbox-searchChapterTemplate"

        Reuses _open_vue_multiselect + _fill_vue_multiselect so the same
        trusted-event / polling logic is applied as for all other Vue multiselects.
        """
        try:
            inp = page.locator("#searchChapterTemplate").first
            if inp.count() == 0:
                print("   ⚠️ #searchChapterTemplate input not found")
                return False

            # Open via the arrow button (trusted click, Vue checks isTrusted)
            opened = self._open_vue_multiselect(page, inp, timeout_ms=3000)
            if not opened:
                print("   ⚠️ Could not open #searchChapterTemplate multiselect; trying anyway")

            # Find wrapper so _fill_vue_multiselect can scope the input correctly
            wrapper = page.locator(".multiselect:has(#searchChapterTemplate)").first
            if wrapper.count() == 0:
                wrapper = inp  # fallback: pass the input directly

            # Scope the listbox search to the dedicated listbox element
            listbox_scope = page.locator("#listbox-searchChapterTemplate")

            ok = self._fill_vue_multiselect(
                page,
                wrapper,
                book_id,
                listbox_scope=listbox_scope,
                timeout_s=5.0,
            )
            if ok:
                print(f"   ✅ Chapter template: selected BookID '{book_id}'")
            else:
                print(f"   ⚠️ Chapter template: no match found for '{book_id}'")
            return ok
        except Exception as e:
            print(f"   ❌ _select_book_id_in_chapter_template_multiselect: {e}")
            return False

