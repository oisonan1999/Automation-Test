# automation/form_handler/field_filler.py - split from form_handler.py
# Fill element by type: toggle, radio, inline-edit (normal pages)
import time
import re
import random
from playwright.sync_api import Page


class FieldFillerMixin:
    """Fill element by type: toggle, radio, inline-edit (normal pages)"""

    def _try_select_radio_by_value(self, page, label_text, target_value):
        """
        Tìm radio group gần label_text và click vào radio option matching target_value.
        VD: label="Energy restart mode", value="Daily" → tìm radio group gần "Energy restart mode" và click "Daily"
        """
        try:
            label_lower = label_text.lower().strip()
            value_lower = target_value.lower().strip()

            # Strategy 1: Tìm label/legend/span chứa label_text, sau đó tìm radio buttons gần đó
            label_candidates = (
                page.locator("label, legend, span, strong, b, h5, div")
                .filter(has_text=re.compile(re.escape(label_text), re.IGNORECASE))
                .all()
            )
            label_candidates = [c for c in label_candidates if c.is_visible()]
            label_candidates.sort(key=lambda el: len(el.inner_text().strip()))

            for label_el in label_candidates:
                label_actual = label_el.inner_text().strip()
                if len(label_actual) > len(label_text) * 3:
                    continue  # Too long, not the right label

                # Tìm parent container
                container = None
                for xpath in [
                    "xpath=ancestor::div[contains(@class,'form-group')]",
                    "xpath=ancestor::div[contains(@class,'control-group')]",
                    "xpath=ancestor::fieldset",
                    "xpath=ancestor::div[contains(@class,'row')]",
                    "xpath=ancestor::div[contains(@class,'radio')]",
                    "xpath=../..",
                ]:
                    try:
                        c = label_el.locator(xpath).first
                        if c.count() > 0:
                            # Check if this container has radio buttons
                            radios = c.locator("input[type='radio']").all()
                            if radios:
                                container = c
                                break
                    except:
                        pass

                if not container:
                    continue

                # Tìm radio buttons trong container
                all_radios = container.locator("input[type='radio']").all()
                for radio in all_radios:
                    if not radio.is_visible():
                        continue
                    # Check parent/label text of this radio
                    try:
                        parent = radio.locator("xpath=..").first
                        parent_text = parent.inner_text().strip().lower()
                        radio_id = radio.get_attribute("id") or ""
                        radio_value = (radio.get_attribute("value") or "").lower()

                        # Match by: parent text, value attribute, or linked label
                        if (
                            value_lower == parent_text
                            or value_lower in parent_text
                            or value_lower == radio_value
                        ):
                            if not radio.is_checked():
                                radio.click(force=True)
                            print(
                                f"         🔘 Radio option '{target_value}' clicked (parent text match)"
                            )
                            return True

                        # Check linked label
                        if radio_id:
                            linked_label = page.locator(
                                f"label[for='{radio_id}']"
                            ).first
                            if linked_label.count() > 0:
                                linked_text = linked_label.inner_text().strip().lower()
                                if (
                                    value_lower == linked_text
                                    or value_lower in linked_text
                                ):
                                    if not radio.is_checked():
                                        radio.click(force=True)
                                    print(
                                        f"         🔘 Radio option '{target_value}' clicked (label for match)"
                                    )
                                    return True
                    except:
                        pass

            # Strategy 2: Global search - find ALL visible radio buttons, match by text/value
            print(
                f"         🔍 [RadioByValue] Strategy 2: Global radio search for '{target_value}'..."
            )
            all_radios = page.locator("input[type='radio']:visible").all()
            for radio in all_radios:
                try:
                    parent = radio.locator("xpath=..").first
                    parent_text = parent.inner_text().strip().lower()
                    radio_value = (radio.get_attribute("value") or "").lower()
                    radio_id = radio.get_attribute("id") or ""

                    if (
                        value_lower == parent_text
                        or value_lower in parent_text
                        or value_lower == radio_value
                    ):
                        # Verify this radio is near the label (within 500px vertical distance)
                        # by checking if label_text exists somewhere above
                        if not radio.is_checked():
                            radio.click(force=True)
                        print(
                            f"         🔘 [Global] Radio option '{target_value}' selected"
                        )
                        return True

                    if radio_id:
                        linked_label = page.locator(f"label[for='{radio_id}']").first
                        if linked_label.count() > 0:
                            linked_text = linked_label.inner_text().strip().lower()
                            if value_lower == linked_text or value_lower in linked_text:
                                if not radio.is_checked():
                                    radio.click(force=True)
                                print(
                                    f"         🔘 [Global] Radio option '{target_value}' selected (by label)"
                                )
                                return True
                except:
                    pass

            print(
                f"         ❌ [RadioByValue] Could not find radio option '{target_value}' near '{label_text}'"
            )
            return False

        except Exception as e:
            print(f"         ⚠️ [RadioByValue] Error: {e}")
            return False

    def _try_click_radio_by_label(self, page, label_text, value):
        """
        Tìm và click RADIO BUTTON dựa trên label text.
        QUAN TRỌNG: Phải tìm EXACT MATCH hoặc match tốt nhất để tránh nhầm.
        """
        try:
            label_lower = label_text.lower().strip()

            # ========================================
            # STRATEGY 1: Tìm tất cả radio buttons visible trên trang
            # Sau đó check text gần nhất với mỗi radio
            # ========================================
            all_radios = page.locator("input[type='radio']").all()
            best_match = None
            best_score = 0

            for radio in all_radios:
                if not radio.is_visible():
                    continue

                # Lấy text của parent element (thường chứa label text)
                try:
                    parent = radio.locator("xpath=..").first
                    parent_text = parent.inner_text().strip().lower()

                    # Tính điểm match
                    # EXACT MATCH = 100 điểm
                    # CONTAINS = 50 điểm
                    # PARTIAL = 10 điểm
                    score = 0
                    if parent_text == label_lower:
                        score = 100
                    elif label_lower in parent_text:
                        # Ưu tiên match ngắn hơn (tránh "Auto Generate a new currency" khi tìm "Use another currency")
                        score = 50 - len(parent_text) / 10
                    elif any(word in parent_text for word in label_lower.split()):
                        score = 10

                    if score > best_score:
                        best_score = score
                        best_match = radio

                except:
                    pass

            # Nếu tìm được match tốt (score >= 50), click vào
            if best_match and best_score >= 50:
                if not best_match.is_checked():
                    best_match.click(force=True)
                    print(f"         🔘 Radio clicked (score={best_score})")
                return True

            # ========================================
            # STRATEGY 2: Tìm qua label element với EXACT text match
            # ========================================
            # Tìm label có text CHÍNH XÁC (không phải contains)
            all_labels = page.locator("label").all()
            for lbl in all_labels:
                if not lbl.is_visible():
                    continue
                lbl_text = lbl.inner_text().strip().lower()

                # EXACT MATCH
                if lbl_text == label_lower:
                    # Tìm radio bên trong hoặc liên kết
                    radio_inside = lbl.locator("input[type='radio']").first
                    if radio_inside.count() > 0:
                        if not radio_inside.is_checked():
                            lbl.click()
                        return True

                    for_attr = lbl.get_attribute("for")
                    if for_attr:
                        radio_by_id = page.locator(f"#{for_attr}").first
                        if radio_by_id.count() > 0 and not radio_by_id.is_checked():
                            lbl.click()
                            return True

            return False
        except Exception as e:
            print(f"         ⚠️ Radio search error: {e}")
            return False

    # ============================
    # 6. HELPERS
    # ============================
    def _try_set_form_toggle_by_label(self, page, label_text, value):
        """
        Bật/tắt toggle trên form chính (VD: Daily Reward switch trên Tournament Info).
        Không dùng link sidebar a#daily_reward.
        """
        label_lower = label_text.lower().strip()
        want_on = str(value).lower().strip() in (
            "true",
            "1",
            "on",
            "yes",
            "enable",
        )
        scope = self._main_form_scope(page)
        safe = re.compile(rf"^\s*{re.escape(label_text)}\s*$", re.IGNORECASE)

        # ── Priority path: scan <label> elements directly, use 'for' attribute ──
        # This avoids iterating parent divs (div.col-auto, div.form-check) that also
        # match the regex but whose ancestor::row contains multiple checkboxes.
        try:
            for _lbl in page.locator("label").all():
                try:
                    if not _lbl.is_visible():
                        continue
                    if _lbl.inner_text().strip().lower() != label_lower:
                        continue
                    _for_id = _lbl.get_attribute("for")
                    if _for_id:
                        _inp = page.locator(f"#{_for_id}").first
                        if _inp.count() > 0:
                            _checked = _inp.is_checked()
                            if want_on and not _checked:
                                _inp.click(force=True)
                            elif not want_on and _checked:
                                _inp.click(force=True)
                            print(
                                f"         🎚️ Toggle '{label_text}' → "
                                f"{'ON' if want_on else 'OFF'} (label[for=#{_for_id}])"
                            )
                            return True
                    # No 'for': click the label itself — browser natively toggles its input
                    _lbl.click(force=True)
                    print(
                        f"         🎚️ Toggle '{label_text}' → "
                        f"{'ON' if want_on else 'OFF'} (label click)"
                    )
                    return True
                except Exception:
                    continue
        except Exception:
            pass

        for label_el in (
            scope.locator("label, span, strong, b, div").filter(has_text=safe).all()
        ):
            try:
                if not label_el.is_visible():
                    continue
                if label_el.inner_text().strip().lower() != label_lower:
                    continue
                # Fast path A: if label_el itself is a form-check/form-group container,
                # search within it directly (avoids ancestor::row escaping to wrong scope)
                try:
                    _self_cls = (label_el.get_attribute("class") or "").lower()
                    if "form-check" in _self_cls or "form-group" in _self_cls:
                        _inner_toggles = label_el.locator(
                            "input[type='checkbox'], .toggle input, "
                            ".bootstrap-switch input, [role='switch']"
                        ).all()
                        for _it in _inner_toggles:
                            try:
                                if not _it.is_visible(timeout=300):
                                    continue
                            except Exception:
                                pass
                            checked = _it.is_checked()
                            if want_on and not checked:
                                _it.click(force=True)
                            elif not want_on and checked:
                                _it.click(force=True)
                            print(
                                f"         🎚️ Toggle '{label_text}' → "
                                f"{'ON' if want_on else 'OFF'} (form-check self-container)"
                            )
                            return True
                except Exception:
                    pass
                # Fast path B: if label has a 'for' attribute, click the associated input directly
                try:
                    for_id = label_el.get_attribute("for")
                    if for_id:
                        target_input = scope.locator(f"#{for_id}").first
                        if target_input.count() == 0:
                            # scope might not contain it; fall back to page-level search
                            target_input = page.locator(f"#{for_id}").first
                        if target_input.count() > 0:
                            checked = target_input.is_checked()
                            if want_on and not checked:
                                target_input.click(force=True)
                            elif not want_on and checked:
                                target_input.click(force=True)
                            print(
                                f"         🎚️ Toggle '{label_text}' → "
                                f"{'ON' if want_on else 'OFF'} (by for=#{for_id})"
                            )
                            return True
                except Exception:
                    pass
                for xpath in (
                    "xpath=ancestor::div[contains(@class,'form-group')][1]",
                    "xpath=ancestor::div[contains(@class,'control-group')][1]",
                    "xpath=ancestor::div[contains(@class,'form-check')][1]",
                    "xpath=ancestor::div[contains(@class,'row')][1]",
                ):
                    try:
                        row = label_el.locator(xpath).first
                        if row.count() == 0 or not row.is_visible():
                            continue
                        toggles = row.locator(
                            "input[type='checkbox'], .toggle input, "
                            ".bootstrap-switch input, [role='switch']"
                        ).all()
                        for tog in toggles:
                            if not tog.is_visible():
                                continue
                            checked = tog.is_checked()
                            if want_on and not checked:
                                tog.click(force=True)
                            elif not want_on and checked:
                                tog.click(force=True)
                            print(
                                f"         🎚️ Toggle '{label_text}' → "
                                f"{'ON' if want_on else 'OFF'} (checkbox/switch)"
                            )
                            return True
                        # Bootstrap toggle: click label sibling .toggle-group
                        toggle_ui = row.locator(
                            ".toggle, .toggle-group, .bootstrap-switch, label.toggle"
                        ).first
                        if toggle_ui.count() > 0 and toggle_ui.is_visible():
                            toggle_ui.click(force=True)
                            print(
                                f"         🎚️ Toggle '{label_text}' → clicked UI toggle"
                            )
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _handle_inline_edit_field(self, page, label_text, value):
        """
        Handle fields with Edit buttons (e.g., Lock Time Offset, Buffer Time, Player-Base Gathering Time).
        These fields show as read-only text with an ✏️ Edit button.
        Flow: Click Edit → type new value → click Save/OK next to it.
        """
        try:
            label_lower = label_text.lower().strip()
            print(f"         ✏️ Trying inline edit for '{label_text}'...")

            # Strategy 1: Tìm container nhỏ nhất chứa label text VÀ có nút Edit
            # Duyệt từ container nhỏ đến lớn
            candidates = (
                page.locator("div, tr, fieldset, span, td, li, p")
                .filter(has_text=re.compile(re.escape(label_text), re.IGNORECASE))
                .all()
            )

            # Sort theo kích thước text (nhỏ nhất trước = container chính xác nhất)
            visible_candidates = []
            for c in candidates:
                if c.is_visible():
                    try:
                        text_len = len(c.inner_text().strip())
                        if text_len < 1000:  # Bỏ qua container quá lớn
                            visible_candidates.append((text_len, c))
                    except:
                        pass

            visible_candidates.sort(key=lambda x: x[0])

            for text_len, container in visible_candidates:
                # Tìm nút Edit trong container
                edit_btn = container.locator(
                    "button:has-text('Edit'), a:has-text('Edit'), "
                    "button:has-text('✏'), a:has-text('✏'), "
                    "button[title*='edit' i], a[title*='edit' i], "
                    ".btn-edit, [class*='edit-btn']"
                ).first

                if edit_btn.count() == 0 or not edit_btn.is_visible():
                    continue

                print(
                    f"         ✏️ Found Edit button near '{label_text}' (container size={text_len})"
                )
                edit_btn.scroll_into_view_if_needed()
                time.sleep(0.3)
                edit_btn.click()
                time.sleep(1.5)  # Chờ input xuất hiện hoặc popup mở

                # Sau khi click Edit, tìm input editable trong container
                # Có thể input mới xuất hiện hoặc field cũ trở nên editable
                editable_input = None

                # Check 1: Tìm trong cùng container
                inputs_in_container = container.locator(
                    "input[type='text']:visible, input[type='number']:visible, "
                    "input:not([type='radio']):not([type='checkbox']):not([type='hidden']):visible"
                ).all()
                for inp in inputs_in_container:
                    if inp.is_visible() and inp.is_editable():
                        editable_input = inp
                        break

                # Check 2: Tìm modal/popup mới xuất hiện
                if not editable_input:
                    try:
                        modal = page.locator(
                            ".modal.show, .swal2-popup, .popover.show"
                        ).last
                        if modal.is_visible():
                            modal_input = modal.locator(
                                "input[type='text']:visible, input[type='number']:visible"
                            ).first
                            if modal_input.count() > 0 and modal_input.is_visible():
                                editable_input = modal_input
                    except:
                        pass

                # Check 3: Tìm input mới xuất hiện gần vị trí nút Edit
                if not editable_input:
                    try:
                        edit_box = edit_btn.bounding_box()
                        if edit_box:
                            all_inputs = page.locator("input:visible").all()
                            for inp in all_inputs:
                                if inp.is_editable():
                                    inp_box = inp.bounding_box()
                                    if inp_box:
                                        # Input gần nút Edit (trong khoảng 200px dọc)
                                        y_diff = abs(inp_box["y"] - edit_box["y"])
                                        if y_diff < 200:
                                            editable_input = inp
                                            break
                    except:
                        pass

                if editable_input:
                    # Fill value
                    try:
                        editable_input.fill("")
                        time.sleep(0.2)
                        editable_input.fill(str(value))
                        print(f"         ✅ Filled inline field: '{value}'")
                    except:
                        editable_input.evaluate(
                            "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); }",
                            str(value),
                        )

                    time.sleep(0.5)

                    # Tìm và click nút Save/OK/Confirm gần đó
                    save_btn = None

                    # Tìm trong container
                    save_btn_candidates = container.locator(
                        "button:has-text('Save'), a:has-text('Save'), "
                        "button:has-text('OK'), button:has-text('Apply'), "
                        "button:has-text('✓'), button:has-text('Confirm'), "
                        "button.btn-success, button.btn-primary"
                    ).all()
                    for btn in save_btn_candidates:
                        if btn.is_visible() and btn != edit_btn:
                            # Không click nhầm nút Edit (đã biến thành Cancel?)
                            btn_text = btn.inner_text().strip().lower()
                            if "edit" not in btn_text and "cancel" not in btn_text:
                                save_btn = btn
                                break

                    # Tìm trong modal nếu có
                    if not save_btn:
                        try:
                            modal = page.locator(".modal.show, .swal2-popup").last
                            if modal.is_visible():
                                modal_save = modal.locator(
                                    "button:has-text('Save'), button:has-text('OK'), button.btn-primary"
                                ).first
                                if modal_save.is_visible():
                                    save_btn = modal_save
                        except:
                            pass

                    if save_btn:
                        save_btn.click()
                        print(f"         💾 Clicked inline Save for '{label_text}'")
                        time.sleep(2)
                    else:
                        # Try Enter to confirm
                        editable_input.press("Enter")
                        print(f"         ⏎ Pressed Enter to confirm '{label_text}'")
                        time.sleep(1)

                    # Chờ page ổn định
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except:
                        pass

                    return True
                else:
                    print(
                        f"         ⚠️ Edit button clicked but no editable input found for '{label_text}'"
                    )
                    # Đóng popup nếu có
                    try:
                        self._safe_press_escape(page)
                    except:
                        pass
                    continue

            return False
        except Exception as e:
            print(f"         ⚠️ Inline edit error for '{label_text}': {e}")
            return False

    def _has_nearby_edit_button(self, page, element, label_text):
        """
        Kiểm tra xem field có nút Edit gần đó không.
        Trả về True nếu phát hiện có nút Edit (báo hiệu cần inline edit flow).
        """
        try:
            # Strategy 1: Kiểm tra element có readonly và có Edit button trong cùng container
            is_readonly = element.get_attribute("readonly") is not None
            is_disabled = not element.is_enabled()

            # Nếu field có thể edit bình thường, không cần Edit button
            if not is_readonly and not is_disabled:
                return False

            # Tìm container cha chứa cả input và potential Edit button
            containers = []

            # Thử các parent levels
            for xpath in [
                "xpath=..",  # Parent trực tiếp
                "xpath=../..",  # Grandparent
                "xpath=../../..",  # Great-grandparent
                "xpath=ancestor::div[@class='form-group']",
                "xpath=ancestor::tr",  # Nếu trong table
                "xpath=ancestor::fieldset",
            ]:
                try:
                    container = element.locator(xpath).first
                    if container.count() > 0:
                        containers.append(container)
                except:
                    pass

            # Strategy 2: Tìm container chứa label text
            try:
                label_containers = (
                    page.locator("div, tr, fieldset, td")
                    .filter(has_text=re.compile(re.escape(label_text), re.IGNORECASE))
                    .all()
                )
                # Chỉ lấy container nhỏ (< 500 chars) để tránh container quá lớn
                for c in label_containers:
                    if c.is_visible():
                        text_len = len(c.inner_text().strip())
                        if 10 < text_len < 500:  # Container hợp lý
                            containers.append(c)
            except:
                pass

            # Kiểm tra từng container có Edit button không
            for container in containers:
                try:
                    # Tìm nút Edit
                    edit_btn = container.locator(
                        "button:has-text('Edit'), a:has-text('Edit'), "
                        "button:has-text('✏'), a:has-text('✏'), "
                        "button[title*='edit' i], a[title*='edit' i], "
                        ".btn-edit, [class*='edit-btn'], button[class*='edit'], "
                        "i.fa-edit, i.fa-pencil"  # Icon buttons
                    ).first

                    if edit_btn.count() > 0 and edit_btn.is_visible():
                        print(f"         🔍 Detected Edit button near '{label_text}'")
                        return True
                except:
                    continue

            # Strategy 3: Tìm Edit button gần vị trí element (300px)
            try:
                el_box = element.bounding_box()
                if el_box:
                    all_edit_btns = page.locator(
                        "button:has-text('Edit'), a:has-text('Edit'), "
                        "button:has-text('✏'), i.fa-edit, i.fa-pencil"
                    ).all()

                    for btn in all_edit_btns:
                        if btn.is_visible():
                            btn_box = btn.bounding_box()
                            if btn_box:
                                # Kiểm tra khoảng cách
                                x_diff = abs(btn_box["x"] - el_box["x"])
                                y_diff = abs(btn_box["y"] - el_box["y"])

                                # Edit button thường nằm cùng hàng (y gần) và bên phải (x > x_el)
                                if y_diff < 100 and x_diff < 300:
                                    print(
                                        f"         🔍 Detected Edit button by proximity near '{label_text}'"
                                    )
                                    return True
            except:
                pass

            return False

        except Exception as e:
            print(f"         ⚠️ Error checking edit button for '{label_text}': {e}")
            return False

    def _fill_element_smartly(self, page, element, value):
        try:
            # --- 0. MULTI-VALUE (list) for multiselect fields ---
            # AI emits a JSON list (e.g. ["SS_A", "SS_B"]) for vue-multiselect / select2
            # multiselect fields that accept >1 value. Each item must be selected in turn
            # so every value is added as a separate tag. A single-element list is unwrapped.
            # NOTE: datetime/schedule fields join lists into a string BEFORE reaching here,
            # so a list arriving at this point is a genuine multi-value dropdown intent.
            if isinstance(value, list):
                items = [
                    re.sub(r"[\[\]'\"]", "", str(v)).strip()
                    for v in value
                    if v is not None and str(v).strip()
                ]
                if len(items) == 0:
                    return True
                if len(items) == 1:
                    value = items[0]  # unwrap → fall through to normal single-value flow
                else:
                    print(
                        f"         🧷 Multi-value multiselect: {len(items)} values {items}"
                    )
                    all_ok = True
                    for _idx, _item in enumerate(items, 1):
                        try:
                            ok_i = self._fill_element_smartly(page, element, _item)
                        except Exception as _mv_e:
                            print(
                                f"         ⚠️ Multi-value item {_idx}/{len(items)} '{_item}' error: {_mv_e}"
                            )
                            ok_i = False
                        all_ok = all_ok and bool(ok_i)
                        # Let Vue re-render the tag list before selecting the next value
                        time.sleep(0.6)
                    return all_ok

            tag_name = element.evaluate("el => el.tagName").lower()
            el_type = element.get_attribute("type")
            class_attr = element.get_attribute("class") or ""
            is_visible = element.is_visible()

            # --- 1. RADIO / CHECKBOX (Ưu tiên số 1) ---
            if el_type in ["checkbox", "radio"]:
                val_str = str(value).lower()
                is_true = val_str in ["true", "1", "on", "yes", "checked"]
                # Radio mặc định là check nếu giá trị không phải là phủ định
                should_check = is_true or (
                    el_type == "radio" and val_str not in ["false", "0", "off", "no"]
                )

                # Sử dụng force=True để click xuyên qua lớp phủ CSS
                if should_check and not element.is_checked():
                    element.click(force=True)
                    print(f"         ✓ Checked {el_type} (Forced)")
                elif not should_check and element.is_checked():
                    element.click(force=True)
                    print(f"         ✓ Unchecked {el_type} (Forced)")

                # [FIX]: Blur để trigger sự kiện change
                try:
                    element.blur()
                except:
                    pass
                time.sleep(0.5)
                return True

            # --- 2. CHỜ ENABLED (Fix cho Currency) ---
            if not element.is_enabled():
                print("         ⏳ Element đang khóa. Chờ mở...")
                try:
                    element.wait_for(state="enabled", timeout=3000)
                except:
                    pass

            # --- 2.5. DATETIME INPUT (Flatpickr, Datepicker, etc.) ---
            is_datetime_picker = (
                "flatpickr" in class_attr
                or "datepicker" in class_attr
                or "datetimepicker" in class_attr
                or "timepicker" in class_attr
            )

            if is_datetime_picker and tag_name == "input":
                print(f"         📅 Xử lý DateTime picker cho '{value}'...")
                value_str = str(value)

                # Strategy 1: Dùng flatpickr JS API (el._flatpickr.setDate + dateFormat từ config)
                try:
                    result = element.evaluate(f"""
                        el => {{
                            if (!el._flatpickr) return 'no_flatpickr';
                            const cfg = el._flatpickr.config;
                            const fmt = (cfg && cfg.dateFormat) ? cfg.dateFormat : null;
                            try {{
                                if (fmt) {{
                                    el._flatpickr.setDate('{value_str}', true, fmt);
                                }} else {{
                                    el._flatpickr.setDate('{value_str}', true);
                                }}
                            }} catch(e1) {{
                                el._flatpickr.setDate('{value_str}', true);
                            }}
                            return 'flatpickr_api:' + (fmt || 'unknown');
                        }}
                        """)
                    if result and result.startswith("flatpickr_api"):
                        time.sleep(0.4)
                        element.evaluate(
                            "el => { el.dispatchEvent(new Event('input', {bubbles: true})); "
                            "el.dispatchEvent(new Event('change', {bubbles: true})); }"
                        )
                        print(
                            f"         ✅ [DateTime/flatpickr API] Đã set: '{value_str}' ({result})"
                        )
                        return True
                except Exception as e1:
                    print(f"         ⚠️ flatpickr API error: {e1}")

                # Strategy 2: Xóa readonly, fill, khôi phục, trigger events
                try:
                    element.evaluate("el => el.removeAttribute('readonly')")
                    time.sleep(0.1)
                    element.fill("")
                    element.fill(value_str)
                    time.sleep(0.2)
                    element.blur()
                    time.sleep(0.2)
                    element.evaluate(
                        "el => { el.dispatchEvent(new Event('input', {bubbles: true})); "
                        "el.dispatchEvent(new Event('change', {bubbles: true})); }"
                    )
                    print(
                        f"         ✅ [DateTime/remove-readonly] Đã điền: '{value_str}'"
                    )
                    return True
                except Exception as e2:
                    print(
                        f"         ⚠️ DateTime picker error: {e2}, trying JS value fallback..."
                    )

                # Strategy 3: Gán value bằng JS thuần
                try:
                    element.evaluate(
                        f"el => {{ el.removeAttribute('readonly'); el.value = '{value_str}'; }}"
                    )
                    element.evaluate(
                        "el => { el.dispatchEvent(new Event('input', {bubbles: true})); "
                        "el.dispatchEvent(new Event('change', {bubbles: true})); }"
                    )
                    print(f"         ✅ [DateTime/JS value] Đã gán: '{value_str}'")
                    return True
                except Exception as e3:
                    print(f"         ❌ DateTime all strategies failed: {e3}")
                    return False

            # --- 3. HIDDEN SELECT (Chosen/Select2/Vue Multiselect) ---
            is_hidden_select = tag_name == "select" and not is_visible
            is_lib = (
                "select2" in class_attr
                or "chosen" in class_attr
                or "multiselect" in class_attr
            )

            # [FIX] Nếu element là wrapper trực tiếp (DIV.multiselect, DIV.chosen, SPAN.select2)
            is_multiselect_div = tag_name == "div" and "multiselect" in class_attr
            is_chosen_div = tag_name == "div" and "chosen-container" in class_attr
            is_select2_span = tag_name == "span" and "select2-container" in class_attr

            if (
                is_hidden_select
                or is_lib
                or is_multiselect_div
                or is_chosen_div
                or is_select2_span
            ):
                print(f"         🕵️ Xử lý Dropdown nâng cao cho '{value}'...")

                # Nếu element chính là wrapper, dùng trực tiếp
                if is_multiselect_div:
                    return self._handle_js_dropdown(page, element, value, "multiselect")
                elif is_chosen_div:
                    return self._handle_js_dropdown(page, element, value, "chosen")
                elif is_select2_span:
                    return self._handle_js_dropdown(page, element, value, "select2")

                # [FIX] Hidden SELECT hoặc SELECT có class lib → Tìm wrapper trước khi fallback JS Force
                if is_hidden_select or is_lib:
                    print("         🔍 SELECT ẩn/lib → Tìm wrapper...")
                    wrapper = self._find_custom_dropdown_wrapper(element)
                    if wrapper and wrapper.is_visible():
                        wrapper_class = wrapper.get_attribute("class") or ""
                        if "chosen" in wrapper_class:
                            print("         ✅ Found Chosen wrapper for hidden SELECT")
                            return self._handle_js_dropdown(
                                page, wrapper, value, "chosen"
                            )
                        elif "select2" in wrapper_class:
                            print("         ✅ Found Select2 wrapper for hidden SELECT")
                            return self._handle_js_dropdown(
                                page, wrapper, value, "select2"
                            )
                        elif "multiselect" in wrapper_class:
                            print(
                                "         ✅ Found Multiselect wrapper for hidden SELECT"
                            )
                            return self._handle_js_dropdown(
                                page, wrapper, value, "multiselect"
                            )
                        else:
                            print(
                                f"         ✅ Found wrapper (class={wrapper_class[:50]}) → default chosen"
                            )
                            return self._handle_js_dropdown(
                                page, wrapper, value, "chosen"
                            )
                    else:
                        # [FIX] Tìm wrapper rộng hơn: parent > sibling
                        print(
                            "         🔍 Wrapper not found by ID/sibling. Trying broader search..."
                        )
                        try:
                            parent = element.locator("xpath=..")
                            broader_wrapper = parent.locator(
                                "div.chosen-container, span.select2-container, div.multiselect"
                            ).first
                            if (
                                broader_wrapper.count() > 0
                                and broader_wrapper.is_visible()
                            ):
                                bw_class = broader_wrapper.get_attribute("class") or ""
                                lib = (
                                    "chosen"
                                    if "chosen" in bw_class
                                    else (
                                        "select2"
                                        if "select2" in bw_class
                                        else "multiselect"
                                    )
                                )
                                print(
                                    f"         ✅ Found wrapper via broader search ({lib})"
                                )
                                return self._handle_js_dropdown(
                                    page, broader_wrapper, value, lib
                                )
                        except:
                            pass

                    # [FIX] Thử select_option trước khi JS Force
                    print(
                        "         ⚠️ Không tìm thấy wrapper. Thử select_option trực tiếp..."
                    )
                    try:
                        element.select_option(value=str(value), timeout=2000)
                        print(f"         ✅ Selected by value: '{value}'")
                        # Trigger UI update
                        element.evaluate(
                            "el => { el.dispatchEvent(new Event('change', {bubbles: true})); "
                            "if(typeof jQuery !== 'undefined') { jQuery(el).trigger('chosen:updated').trigger('change'); } }"
                        )
                        return True
                    except:
                        pass
                    try:
                        element.select_option(label=str(value), timeout=2000)
                        print(f"         ✅ Selected by label: '{value}'")
                        element.evaluate(
                            "el => { el.dispatchEvent(new Event('change', {bubbles: true})); "
                            "if(typeof jQuery !== 'undefined') { jQuery(el).trigger('chosen:updated').trigger('change'); } }"
                        )
                        return True
                    except:
                        pass

                # Fallback JS Force (Chỉ dùng khi cùng đường)
                print("         ⚠️ Không thấy Wrapper. Dùng JS Force...")
                element.evaluate(f"el => el.value = '{value}'")
                element.evaluate(
                    "el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur')); }"
                )
                # Trigger update UI
                element.evaluate(
                    "el => { if(typeof jQuery !== 'undefined') { jQuery(el).trigger('chosen:updated'); jQuery(el).trigger('change'); } }"
                )
                return True

            # --- 4. INPUT THƯỜNG ---
            if not is_visible:
                # Không visible thì trước đây bị return False → làm fail các field required
                # (vd: Conditional inputs đang hidden nhưng vẫn validate).
                print(f"         ⚠️ Element {tag_name} ẩn. Thử điền bằng JS...")

                try:
                    value_str = "" if value is None else str(value)

                    # Set value/checked + dispatch events để trigger validation/UI updates
                    element.evaluate(
                        """(el, v) => {
                          try {
                            const tag = (el.tagName || '').toUpperCase();
                            const type = (el.getAttribute('type') || '').toLowerCase();

                            if (tag === 'SELECT') {
                              const target = (v ?? '').toString().trim();

                              // 1) Try match option by value
                              let opt = Array.from(el.options || []).find(o => (o.value || '').trim() === target);

                              // 2) Try match option by visible text (handles "Win against any rarity" -> value "win:none")
                              if (!opt) {
                                const norm = s => (s || '').toString().trim().replace(/\\s+/g,' ').toLowerCase();
                                const targetNorm = norm(target);
                                opt = Array.from(el.options || []).find(o => norm(o.textContent) === targetNorm);
                              }

                              if (opt) {
                                el.value = opt.value;
                              } else {
                                // fallback
                                el.value = target;
                              }
                            } else if (type === 'checkbox' || type === 'radio') {
                              el.checked = (v === 'true' || v === '1' || v === 'on' || v === 'yes' || v === 'checked');
                            } else {
                              el.value = (v ?? '').toString();
                            }

                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            el.dispatchEvent(new Event('blur', { bubbles: true }));
                          } catch (e) {}
                        }""",
                        value_str,
                    )
                    return True
                except Exception:
                    return False

            element.scroll_into_view_if_needed()

            # [FIX CRITICAL] Xử lý SELECT: Kiểm tra có phải custom dropdown không
            # Ngay cả khi SELECT visible, nó có thể được wrap bởi Chosen/Select2
            if tag_name == "select":
                print(
                    f"         🔍 Detect SELECT element. Checking for custom dropdown wrapper..."
                )

                # [FIX] For VISIBLE selects, try native select_option FIRST.
                # Global wrapper search (_find_custom_dropdown_wrapper step 4) can return
                # false-positives by distance (e.g. nearby Gate/Currency chosen container),
                # causing stray clicks that fill the wrong field (e.g. Linked RBE).
                # Only fall back to wrapper search if native select_option fully fails.
                native_selected = False
                native_select_err = None
                try:
                    element.select_option(label=str(value), timeout=1500)
                    print(
                        f"         ✅ [Native SELECT] Selected by label (exact): '{value}'"
                    )
                    native_selected = True
                except Exception as _e1:
                    try:
                        element.select_option(value=str(value), timeout=1500)
                        print(
                            f"         ✅ [Native SELECT] Selected by value (exact): '{value}'"
                        )
                        native_selected = True
                    except Exception as _e2:
                        # Try fuzzy option match before falling back to wrapper
                        try:
                            _options = element.locator("option").all()
                            _value_lower = str(value).lower().strip()
                            _match = None
                            for _opt in _options:
                                _ot = _opt.inner_text().strip()
                                _ov = _opt.get_attribute("value") or ""
                                if _ot.lower() == _value_lower:
                                    _match = (_ot, _ov, "exact")
                                    break
                                if not _match and _value_lower in _ot.lower():
                                    _match = (_ot, _ov, "contains")
                                if not _match and _ot.lower() in _value_lower:
                                    _match = (_ot, _ov, "reverse")
                            if _match:
                                _ot, _ov, _mt = _match
                                print(
                                    f"         🎯 [Native SELECT] Fuzzy match ({_mt}): '{_ot}'"
                                )
                                try:
                                    element.select_option(value=_ov, timeout=1500)
                                    native_selected = True
                                except:
                                    element.evaluate(
                                        f"el => {{ el.value = '{_ov}'; el.dispatchEvent(new Event('change', {{bubbles: true}})); }}"
                                    )
                                    native_selected = True
                                print(
                                    f"         ✅ [Native SELECT] Filled '{_ot}' (value='{_ov}')"
                                )
                        except Exception as _e3:
                            native_select_err = _e3

                if native_selected:
                    # [FIX] Trigger change + chosen:updated + listenChange cho mọi framework
                    element.evaluate(
                        "el => { "
                        "  el.dispatchEvent(new Event('change', {bubbles: true})); "
                        "  el.dispatchEvent(new Event('input', {bubbles: true})); "
                        "  if(typeof jQuery !== 'undefined') { "
                        "    jQuery(el).trigger('chosen:updated').trigger('change').trigger('liszt:updated'); "
                        "  } "
                        "}"
                    )
                    # [FIX] Force Chosen wrapper UI update nếu có
                    try:
                        _wrapper = self._find_custom_dropdown_wrapper(element)
                        if _wrapper and _wrapper.is_visible():
                            _wclass = _wrapper.get_attribute("class") or ""
                            if "chosen" in _wclass:
                                print(
                                    f"         🔄 Updating Chosen wrapper UI after native select"
                                )
                                element.evaluate(
                                    "el => { if(typeof jQuery !== 'undefined') { jQuery(el).trigger('chosen:updated'); } }"
                                )
                                time.sleep(0.3)
                    except:
                        pass
                    return True

                # Native select_option failed → now check for custom wrapper (Chosen/Select2)
                print(
                    f"         ⚠️ Native select_option failed ({native_select_err}). Checking for custom wrapper..."
                )
                wrapper = self._find_custom_dropdown_wrapper(element)

                if wrapper and wrapper.is_visible():
                    # Có wrapper → Đây là custom dropdown
                    wrapper_class = wrapper.get_attribute("class") or ""
                    lib = "chosen"
                    if "select2" in wrapper_class:
                        lib = "select2"
                    elif "multiselect" in wrapper_class:
                        lib = "multiselect"

                    print(
                        f"         ✅ Found custom dropdown wrapper ({lib}). Using handler..."
                    )
                    return self._handle_js_dropdown(page, wrapper, value, lib)
                else:
                    # Không có wrapper → SELECT bình thường nhưng đã thất bại ở trên
                    print(
                        f"         ℹ️ Native SELECT (no wrapper) - all strategies exhausted."
                    )
                    return False
            else:
                # Input thường (text, textarea, etc.)
                element.fill("")
                element.fill(str(value))
                print(f"         ✅ Filled: '{value}'")

            # [QUAN TRỌNG]: Ép buộc lưu dữ liệu bằng cách Tab ra ngoài
            element.press("Tab")
            # Đề phòng Tab không ăn, gọi thêm blur
            try:
                element.blur()
            except:
                pass

            return True

        except Exception as e:
            print(f"         ❌ Lỗi thao tác: {e}")
            return False

