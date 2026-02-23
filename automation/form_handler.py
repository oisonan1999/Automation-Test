# automation/form_handler.py - Form logic: smart filling, dropdown, radio, datetime, save
# Table/checkbox operations tách ra table_handler.py
import time
import re
import random
from playwright.sync_api import Page


class FormHandlerMixin:
    """Chứa logic tương tác với Form: điền form, dropdown, radio, datetime, save"""

    # ============================
    # SMART FORM FILLER (FULL FEATURES)
    # ============================
    def _smart_update_form(self, page, data):
        """
        Hàm chính: Duyệt qua data và điền từng trường.
        """
        print(f"      📝 Updating Form Data: {data}")

        # Chờ form ổn định
        try:
            page.wait_for_load_state("domcontentloaded")
            time.sleep(1)
        except:
            pass

        for label, value in data.items():
            print(f"         ↳ Processing '{label}' -> '{value}'")
            try:
                value_lower = str(value).lower().strip()

                # ========================================
                # SPECIAL CASE 1: RADIO BUTTON BY LABEL TEXT
                # CHỈ khi value là signal của radio: "select", "true", "on", "1", "yes", "checked"
                # VD: "Use another currency": "select" -> Click radio có label này
                # ========================================
                is_radio_signal = value_lower in [
                    "select",
                    "true",
                    "on",
                    "1",
                    "yes",
                    "checked",
                    "click",
                ]
                if is_radio_signal:
                    if self._try_click_radio_by_label(page, label, value):
                        print(f"         ✅ Radio '{label}' clicked successfully")
                        time.sleep(3)  # Chờ UI update (VD: hiện Currency dropdown)
                        continue

                # ========================================
                # SPECIAL CASE 2: DATETIME VALUES for schedule-type fields
                # Dùng cho fields như "Schedules In UTC", "Schedule in UTC" có datetime inputs
                # Hỗ trợ cả multiple (comma-separated) và single datetime values
                # ========================================
                # [FIX] Handle value là list hoặc string chứa brackets/quotes
                if isinstance(value, list):
                    datetime_values = [
                        re.sub(r"[\[\]'\"]", "", str(v)).strip()
                        for v in value
                        if str(v).strip()
                    ]
                    value_str = ", ".join(datetime_values)
                else:
                    value_str = re.sub(r"[\[\]'\"]", "", str(value)).strip()
                    datetime_values = None  # will be parsed below

                is_schedule_field = any(
                    keyword in label.lower() for keyword in ["schedule"]
                )
                is_datetime_value = bool(
                    re.match(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", value_str.strip())
                )

                if is_schedule_field and ("," in value_str or is_datetime_value):
                    # Tách các giá trị datetime (hoặc wrap single value)
                    if datetime_values is None:
                        if "," in value_str:
                            datetime_values = [
                                v.strip() for v in value_str.split(",") if v.strip()
                            ]
                        else:
                            datetime_values = [value_str.strip()]
                    # [FIX] Dọn lại mỗi value: strip brackets, quotes
                    datetime_values = [
                        re.sub(r"[\[\]'\"]", "", v).strip() for v in datetime_values
                    ]

                    print(
                        f"         🗓️ Detected datetime value(s) for schedule field: {datetime_values}"
                    )
                    if self._fill_schedule_datetime_smart(page, label, datetime_values):
                        print(f"         ✅ Filled schedule datetime for '{label}'")
                        time.sleep(3)
                        continue

                # Bước 1: Tìm Element
                target_element = self._find_input_element(page, label)

                if target_element:
                    # [FIX] Kiểm tra xem field có nút Edit không TRƯỚC KHI cố gắng điền
                    # Nếu có, gọi inline edit handler trước
                    if self._has_nearby_edit_button(page, target_element, label):
                        print(
                            f"         ✏️ Detected Edit button for '{label}', using inline edit..."
                        )
                        success = self._handle_inline_edit_field(page, label, value)
                        if success:
                            print(f"         ✅ Inline edit completed for '{label}'")
                            time.sleep(3)
                            continue
                        else:
                            # Nếu inline edit thất bại, thử điền bình thường
                            print(
                                f"         ⚠️ Inline edit failed, trying normal fill..."
                            )

                    # Bước 2: Điền dữ liệu (Logic thông minh nằm ở đây)
                    success = self._fill_element_smartly(page, target_element, value)
                    if not success:
                        print(f"         ❌ Action Failed for '{label}'")
                    else:
                        # CRITICAL: Trigger change event để reveal conditional fields
                        # VD: Đổi "Leaderboard Type" -> hiện "Bracket Preset"
                        try:
                            target_element.evaluate(
                                "el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('input', {bubbles: true})); }"
                            )
                            print(f"         🔔 Triggered change event for '{label}'")
                        except:
                            pass
                        # Chờ 3s sau mỗi field để dropdown/data load xong và conditional fields appear
                        time.sleep(3)
                else:
                    # RETRY LOGIC: Field có thể chưa xuất hiện (conditional field)
                    # Thử lại sau 2s (có thể đang chờ previous field trigger)
                    print(f"         ⏳ Field '{label}' not found. Retrying in 2s...")
                    time.sleep(2)
                    target_element = self._find_input_element(page, label)

                    if target_element:
                        print(f"         ✅ Found '{label}' on retry!")
                        success = self._fill_element_smartly(
                            page, target_element, value
                        )
                        if success:
                            try:
                                target_element.evaluate(
                                    "el => { el.dispatchEvent(new Event('change', {bubbles: true})); }"
                                )
                            except:
                                pass
                            time.sleep(3)
                        else:
                            print(f"         ❌ Retry fill failed for '{label}'")
                    else:
                        print(
                            f"         ❌ Cannot find field '{label}' even after retry. Trying inline edit..."
                        )
                        # Try inline edit handling (for fields with Edit buttons like Lock Time Offset)
                        if self._handle_inline_edit_field(page, label, value):
                            print(f"         ✅ Inline edit handled for '{label}'")
                            time.sleep(3)
                            continue
                        # Debug: In ra các label/legend hiển thị để debug
                        try:
                            all_labels = page.locator("label, legend").all()
                            visible_labels = [l for l in all_labels if l.is_visible()]
                            label_texts = [
                                l.inner_text().strip()[:50] for l in visible_labels[:10]
                            ]
                            print(f"            Available labels: {label_texts}")
                        except:
                            pass
            except Exception as e:
                print(f"         ❌ Error filling '{label}': {e}")

    def _fill_multiple_datetime_fields(self, page, label_text, values):
        """
        Điền nhiều giá trị datetime vào nhiều inputs có cùng label.
        VD: "Schedules In UTC" có 2 datetime pickers (Start, End).
        """
        try:
            print(
                f"         🔍 Searching for multiple datetime fields for '{label_text}'..."
            )

            # ========================================
            # STRATEGY 1: Tìm flatpickr/datepicker inputs trong fieldset/form-group chứa label
            # ========================================
            # Tìm label element chứa text chính xác nhất (ưu tiên label, legend)
            label_candidates = (
                page.locator("label, legend")
                .filter(has_text=re.compile(re.escape(label_text), re.IGNORECASE))
                .all()
            )

            # Sort: ưu tiên label/legend ngắn nhất (exact match)
            label_candidates = [c for c in label_candidates if c.is_visible()]
            label_candidates.sort(key=lambda el: len(el.inner_text().strip()))

            for label_el in label_candidates:
                try:
                    label_actual_text = label_el.inner_text().strip()
                    print(f"         🏷️ Trying label: '{label_actual_text}'")

                    # Tìm parent container gần nhất (fieldset > form-group > row)
                    container = None
                    for xpath in [
                        "xpath=ancestor::fieldset",
                        "xpath=ancestor::div[contains(@class,'form-group')]",
                        "xpath=ancestor::div[contains(@class,'control-group')]",
                        "xpath=ancestor::div[contains(@class,'schedule')]",
                        "xpath=ancestor::div[contains(@class,'datetime')]",
                    ]:
                        try:
                            c = label_el.locator(xpath).first
                            if c.count() > 0:
                                container = c
                                break
                        except:
                            pass

                    if not container:
                        # Fallback: parent 3 levels up
                        container = label_el.locator("xpath=../../..").first

                    if not container or container.count() == 0:
                        continue

                    # [FIX CRITICAL] Tìm datetime inputs: flatpickr, datepicker, datetimepicker
                    # VÀ filter bỏ readonly inputs
                    datetime_inputs = []

                    # Priority 1: flatpickr inputs (class chứa flatpickr hoặc có data-flatpickr)
                    flatpickr_inputs = container.locator(
                        "input.flatpickr-input, input[data-toggle='flatpickr'], input[data-toggle='datetimepicker'], "
                        "input.datetimepicker, input.datepicker, input.timepicker"
                    ).all()
                    for inp in flatpickr_inputs:
                        if inp.is_visible():
                            # Flatpickr thường set readonly → vẫn thêm nhưng dùng JS
                            datetime_inputs.append(inp)

                    # Priority 2: Nếu không tìm thấy flatpickr, tìm tất cả visible text/date inputs
                    # NHƯNG filter bỏ readonly (trừ flatpickr) và filter bỏ input có ID không liên quan
                    if not datetime_inputs:
                        all_inputs = container.locator(
                            "input[type='text'], input[type='date'], input[type='datetime-local']"
                        ).all()

                        for inp in all_inputs:
                            if not inp.is_visible():
                                continue
                            # [FIX] Bỏ qua readonly inputs (trừ khi có class flatpickr)
                            is_readonly = inp.get_attribute("readonly")
                            inp_class = inp.get_attribute("class") or ""
                            inp_id = inp.get_attribute("id") or ""
                            inp_name = inp.get_attribute("name") or ""

                            # Skip nếu là readonly VÀ không phải datepicker
                            if is_readonly and not any(
                                kw in inp_class.lower()
                                for kw in [
                                    "flatpickr",
                                    "datepicker",
                                    "datetime",
                                    "timepicker",
                                ]
                            ):
                                print(
                                    f"            ⏭️ Skip readonly input: id='{inp_id}', name='{inp_name}'"
                                )
                                continue

                            # Skip nếu ID/name rõ ràng không phải datetime
                            skip_ids = [
                                "factionwarid",
                                "eventid",
                                "name",
                                "title",
                                "description",
                            ]
                            if any(skip in inp_id.lower() for skip in skip_ids):
                                print(
                                    f"            ⏭️ Skip non-datetime input: id='{inp_id}'"
                                )
                                continue
                            if any(skip in inp_name.lower() for skip in skip_ids):
                                print(
                                    f"            ⏭️ Skip non-datetime input: name='{inp_name}'"
                                )
                                continue

                            # [FIX] Chỉ chọn input có placeholder/class liên quan datetime
                            inp_placeholder = (
                                inp.get_attribute("placeholder") or ""
                            ).lower()
                            is_likely_datetime = any(
                                kw
                                in inp_class.lower()
                                + inp_placeholder
                                + inp_id.lower()
                                + inp_name.lower()
                                for kw in [
                                    "date",
                                    "time",
                                    "schedule",
                                    "flatpickr",
                                    "picker",
                                    "utc",
                                    "calendar",
                                ]
                            )

                            if is_likely_datetime or inp.is_editable():
                                datetime_inputs.append(inp)

                    # [FIX] Cuối cùng: chỉ giữ editable inputs (hoặc flatpickr readonly)
                    final_inputs = []
                    for inp in datetime_inputs:
                        inp_class = inp.get_attribute("class") or ""
                        is_flatpickr = any(
                            kw in inp_class.lower()
                            for kw in ["flatpickr", "datepicker", "datetimepicker"]
                        )
                        if inp.is_editable() or is_flatpickr:
                            final_inputs.append(inp)
                    datetime_inputs = final_inputs

                    print(
                        f"         📍 Found {len(datetime_inputs)} datetime inputs in container"
                    )

                    if len(datetime_inputs) >= len(values):
                        for idx, (inp, val) in enumerate(zip(datetime_inputs, values)):
                            print(f"         📅 Filling input {idx+1}: '{val}'")
                            inp.scroll_into_view_if_needed()
                            time.sleep(0.3)

                            inp_class = inp.get_attribute("class") or ""
                            is_flatpickr = "flatpickr" in inp_class.lower()
                            is_readonly = inp.get_attribute("readonly") is not None

                            if is_flatpickr or is_readonly:
                                # Flatpickr readonly → Dùng JS để set value
                                print(
                                    f"            🔧 Using JS for flatpickr/readonly input"
                                )
                                inp.evaluate(
                                    "(el, v) => {"
                                    "  el.removeAttribute('readonly');"
                                    "  el.value = v;"
                                    "  el.setAttribute('value', v);"
                                    "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                                    "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                                    "  // Nếu có flatpickr instance, update nó"
                                    "  if(el._flatpickr) { el._flatpickr.setDate(v, true); }"
                                    "}",
                                    str(val),
                                )
                            else:
                                # Input bình thường → fill trực tiếp
                                try:
                                    inp.fill("")
                                    time.sleep(0.1)
                                    inp.fill(str(val))
                                except:
                                    # Fallback JS
                                    inp.evaluate(
                                        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }",
                                        str(val),
                                    )

                            time.sleep(0.3)

                            # Trigger events & close any open picker
                            try:
                                inp.evaluate(
                                    "el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }"
                                )
                            except:
                                pass
                            # Click elsewhere to close picker
                            try:
                                page.keyboard.press("Escape")
                            except:
                                pass
                            time.sleep(0.2)

                        return True
                    else:
                        print(
                            f"         ⚠️ Not enough inputs ({len(datetime_inputs)}) for {len(values)} values"
                        )

                except Exception as e:
                    print(f"         ⚠️ Container search error: {e}")
                    continue

            # ========================================
            # STRATEGY 2: Tìm TẤT CẢ flatpickr inputs trên trang (global search)
            # Khi container search thất bại
            # ========================================
            print("         🔍 Strategy 2: Global flatpickr search...")
            all_flatpickr = page.locator(
                "input.flatpickr-input:visible, input.datetimepicker:visible, input.datepicker:visible"
            ).all()

            # Filter bỏ những input đã có giá trị hợp lệ (có thể là field khác)
            # Giữ lại input trống hoặc có giá trị cũ
            editable_flatpickr = []
            for inp in all_flatpickr:
                inp_id = inp.get_attribute("id") or ""
                # Bỏ qua input ID không liên quan
                skip_ids = ["factionwarid", "eventid"]
                if any(skip in inp_id.lower() for skip in skip_ids):
                    continue
                editable_flatpickr.append(inp)

            print(f"         📍 Found {len(editable_flatpickr)} global datetime inputs")

            if len(editable_flatpickr) >= len(values):
                # Heuristic: Lấy N inputs cuối (thường là schedule inputs)
                target_inputs = editable_flatpickr[-len(values) :]
                for idx, (inp, val) in enumerate(zip(target_inputs, values)):
                    print(f"         📅 [Global] Filling input {idx+1}: '{val}'")
                    inp.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    inp.evaluate(
                        "(el, v) => {"
                        "  el.removeAttribute('readonly');"
                        "  el.value = v;"
                        "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                        "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                        "  if(el._flatpickr) { el._flatpickr.setDate(v, true); }"
                        "}",
                        str(val),
                    )
                    time.sleep(0.2)
                    try:
                        page.keyboard.press("Escape")
                    except:
                        pass

                return True

            return False

        except Exception as e:
            print(f"         ❌ Error filling multiple datetime fields: {e}")
            return False

    def _fill_schedule_datetime_smart(self, page, label_text, values):
        """
        Hàm thông minh để điền datetime cho schedule fields.
        Hỗ trợ cả multiple values (fill tất cả) và single value (fill vào slot tiếp theo trống).
        Kết hợp logic _fill_multiple_datetime_fields nhưng thông minh hơn cho single values.
        """
        try:
            print(
                f"         🔍 [ScheduleSmart] Finding datetime inputs for '{label_text}'..."
            )

            # ========================================
            # STRATEGY 1: Tìm label container chứa schedule text
            # ========================================
            label_candidates = (
                page.locator(
                    "label, legend, span.control-label, h5, strong, div.col-form-label"
                )
                .filter(has_text=re.compile(re.escape(label_text), re.IGNORECASE))
                .all()
            )
            label_candidates = [c for c in label_candidates if c.is_visible()]
            label_candidates.sort(key=lambda el: len(el.inner_text().strip()))

            datetime_inputs = []

            for label_el in label_candidates:
                try:
                    label_actual = label_el.inner_text().strip()
                    print(
                        f"         🏷️ [ScheduleSmart] Trying label: '{label_actual[:60]}'"
                    )

                    # Tìm parent container
                    container = None
                    for xpath in [
                        "xpath=ancestor::fieldset",
                        "xpath=ancestor::div[contains(@class,'form-group')]",
                        "xpath=ancestor::div[contains(@class,'control-group')]",
                        "xpath=ancestor::div[contains(@class,'schedule')]",
                        "xpath=ancestor::div[contains(@class,'datetime')]",
                        "xpath=ancestor::div[contains(@class,'row')]",
                    ]:
                        try:
                            c = label_el.locator(xpath).first
                            if c.count() > 0:
                                container = c
                                break
                        except:
                            pass

                    if not container:
                        container = label_el.locator("xpath=../../..").first

                    if not container or container.count() == 0:
                        continue

                    # Tìm datetime inputs trong container
                    # Priority 1: flatpickr / datepicker
                    fp_inputs = container.locator(
                        "input.flatpickr-input, input[data-toggle='flatpickr'], "
                        "input[data-toggle='datetimepicker'], input.datetimepicker, "
                        "input.datepicker, input.timepicker"
                    ).all()
                    for inp in fp_inputs:
                        if inp.is_visible():
                            datetime_inputs.append(inp)

                    # Priority 2: inputs with datetime-related attributes
                    if not datetime_inputs:
                        all_inputs = container.locator(
                            "input[type='text'], input[type='date'], input[type='datetime-local'], input:not([type])"
                        ).all()
                        for inp in all_inputs:
                            if not inp.is_visible():
                                continue
                            inp_class = (inp.get_attribute("class") or "").lower()
                            inp_id = (inp.get_attribute("id") or "").lower()
                            inp_name = (inp.get_attribute("name") or "").lower()
                            inp_placeholder = (
                                inp.get_attribute("placeholder") or ""
                            ).lower()

                            # Skip clearly unrelated inputs
                            skip_names = [
                                "id",
                                "name",
                                "title",
                                "description",
                                "eventid",
                                "factionwarid",
                            ]
                            if any(inp_name == skip for skip in skip_names):
                                continue
                            if any(inp_id == skip for skip in skip_names):
                                continue

                            # Check if datetime-related
                            all_attrs = inp_class + inp_id + inp_name + inp_placeholder
                            is_datetime = any(
                                kw in all_attrs
                                for kw in [
                                    "date",
                                    "time",
                                    "schedule",
                                    "flatpickr",
                                    "picker",
                                    "utc",
                                    "calendar",
                                ]
                            )
                            if is_datetime or inp.is_editable():
                                datetime_inputs.append(inp)

                    if datetime_inputs:
                        break  # Tìm được inputs, dừng loop
                except Exception as e:
                    print(f"         ⚠️ [ScheduleSmart] Container search error: {e}")
                    continue

            # ========================================
            # STRATEGY 2: Global flatpickr search (fallback)
            # ========================================
            if not datetime_inputs:
                print(
                    "         🔍 [ScheduleSmart] Strategy 2: Global flatpickr search..."
                )
                all_fp = page.locator(
                    "input.flatpickr-input:visible, input.datetimepicker:visible, input.datepicker:visible"
                ).all()
                for inp in all_fp:
                    inp_id = (inp.get_attribute("id") or "").lower()
                    if any(skip in inp_id for skip in ["factionwarid", "eventid"]):
                        continue
                    datetime_inputs.append(inp)
                print(
                    f"         📍 [ScheduleSmart] Found {len(datetime_inputs)} global datetime inputs"
                )

            if not datetime_inputs:
                print(
                    f"         ❌ [ScheduleSmart] No datetime inputs found for '{label_text}'"
                )
                return False

            print(
                f"         📍 [ScheduleSmart] Found {len(datetime_inputs)} datetime inputs total"
            )

            # ========================================
            # FILL LOGIC: Multiple values → fill sequentially; Single value → fill next empty slot
            # ========================================
            if len(values) > 1:
                # Multiple values: fill inputs in order
                for idx, (inp, val) in enumerate(zip(datetime_inputs, values)):
                    self._fill_single_datetime_input(page, inp, val, idx)
            else:
                # Single value: find the first EMPTY input and fill it
                # Nếu tất cả đều trống, fill vào cái đầu tiên
                # Nếu cái đầu đã có giá trị, fill vào cái tiếp theo
                val = values[0]
                filled = False
                for idx, inp in enumerate(datetime_inputs):
                    try:
                        current_val = inp.input_value().strip()
                        if not current_val:
                            print(
                                f"         📅 [ScheduleSmart] Slot {idx+1} is empty, filling: '{val}'"
                            )
                            self._fill_single_datetime_input(page, inp, val, idx)
                            filled = True
                            break
                    except:
                        pass

                if not filled:
                    # All slots have values → fill the LAST one (override end time)
                    if len(datetime_inputs) >= 2:
                        print(
                            f"         📅 [ScheduleSmart] All slots filled, overriding last slot: '{val}'"
                        )
                        self._fill_single_datetime_input(
                            page, datetime_inputs[-1], val, len(datetime_inputs) - 1
                        )
                    else:
                        print(
                            f"         📅 [ScheduleSmart] Filling first slot: '{val}'"
                        )
                        self._fill_single_datetime_input(
                            page, datetime_inputs[0], val, 0
                        )

            return True

        except Exception as e:
            print(f"         ❌ [ScheduleSmart] Error: {e}")
            return False

    def _fill_single_datetime_input(self, page, inp, val, idx):
        """Helper: điền 1 giá trị datetime vào 1 input"""
        try:
            # [FIX] Sanitize: strip brackets, quotes from value
            val = re.sub(r"[\[\]'\"]", "", str(val)).strip()
            print(f"         📅 Filling datetime input {idx+1}: '{val}'")
            inp.scroll_into_view_if_needed()
            time.sleep(0.3)

            inp_class = (inp.get_attribute("class") or "").lower()
            is_flatpickr = "flatpickr" in inp_class
            is_readonly = inp.get_attribute("readonly") is not None

            if is_flatpickr or is_readonly:
                # Flatpickr/readonly → JS set
                print(f"            🔧 Using JS for flatpickr/readonly input")
                inp.evaluate(
                    "(el, v) => {"
                    "  el.removeAttribute('readonly');"
                    "  el.value = v;"
                    "  el.setAttribute('value', v);"
                    "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                    "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                    "  if(el._flatpickr) { el._flatpickr.setDate(v, true); }"
                    "}",
                    str(val),
                )
            else:
                # Normal input
                try:
                    inp.fill("")
                    time.sleep(0.1)
                    inp.fill(str(val))
                except:
                    inp.evaluate(
                        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }",
                        str(val),
                    )

            time.sleep(0.3)

            # Trigger events & close picker
            try:
                inp.evaluate(
                    "el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.dispatchEvent(new Event('blur', {bubbles: true})); }"
                )
            except:
                pass
            try:
                page.keyboard.press("Escape")
            except:
                pass
            time.sleep(0.2)
        except Exception as e:
            print(f"         ⚠️ Error filling datetime input {idx+1}: {e}")

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
    def _save_form(self, page, mode="save"):
        """
        Hợp nhất:
        1. Ưu tiên tìm nút theo context (Clone, Create, Save...)
        2. Fallback về logic tìm text linh hoạt.
        3. Hỗ trợ scope Modal.
        """

        def handle_dialog(dialog):
            print(f"      🚨 Browser Alert detected: {dialog.message}")
            dialog.accept()  # Bấm OK để tắt alert đi

        # Xóa listener cũ (nếu có) để tránh duplicate
        try:
            page.remove_listener("dialog", handle_dialog)
        except:
            pass

        page.on("dialog", handle_dialog)

        print(f"   💾 Action: Save/Submit (Mode: {mode})...")

        try:
            # 1. Xác định phạm vi (Scope) - Ưu tiên Modal nếu đang mở
            # Bootstrap 4/5 uses .modal.show; Bootstrap 2 uses .modal.in
            scope = page
            for modal_sel in [
                ".modal.show",
                ".modal.in",
                ".modal[aria-hidden='false']",
            ]:
                if page.locator(modal_sel).count() > 0:
                    scope = page.locator(modal_sel).last
                    print(f"      📍 Scope: Modal detected ({modal_sel})")
                    break

            target_btn = None

            # =========================================================
            # CHIẾN THUẬT 1: TÌM NÚT THEO THỨ TỰ ƯU TIÊN CAO
            # Hỗ trợ mode="save" / mode="clone" / mode="continue"
            # =========================================================
            if mode == "clone":
                # Mode "clone": Bấm nút Clone trong modal (ưu tiên tuyệt đối)
                priority_buttons = [
                    "Clone",
                    "Submit",
                    "Confirm",
                    "OK",
                ]
            elif mode == "save":
                # Mode "save": Chỉ bấm Save (KHÔNG bấm Save & Continue)
                priority_buttons = [
                    "Save",
                    "Update",
                    "Submit",
                    "Confirm",
                    "OK",
                ]
            else:
                # Mode "continue" (default): Ưu tiên Save & Continue
                priority_buttons = [
                    "Save & Continue",
                    "Save and Continue",
                    "Continue",
                    "Save",
                    "Update",
                    "Clone",
                    "Create",
                    "Submit",
                    "Confirm",
                    "OK",
                    "Yes",
                ]

            for btn_text in priority_buttons:
                if mode == "save" and btn_text.lower() == "save":
                    # EXACT MATCH: Tìm button "Save" nhưng KHÔNG match "Save & Continue"
                    all_btns = scope.locator(
                        "button, a.btn, input[type='submit']"
                    ).all()
                    for candidate_btn in all_btns:
                        if candidate_btn.is_visible():
                            try:
                                txt = candidate_btn.inner_text().strip()
                                # Remove icons/emojis, check if remaining text is just "Save"
                                txt_clean = re.sub(r"[^\w\s&]", "", txt).strip()
                                if (
                                    re.match(r"^save$", txt_clean, re.IGNORECASE)
                                    and "continue" not in txt.lower()
                                ):
                                    target_btn = candidate_btn
                                    print(
                                        f"      🎯 Found exact 'Save' button (mode=save)"
                                    )
                                    break
                            except:
                                pass
                    if target_btn:
                        break
                else:
                    btn = (
                        scope.locator("button, a.btn, input[type='submit']")
                        .filter(
                            has_text=re.compile(
                                f"^\\s*{re.escape(btn_text)}\\s*$|{re.escape(btn_text)}",
                                re.IGNORECASE,
                            )
                        )
                        .last
                    )
                    if btn.count() > 0 and btn.is_visible():
                        print(f"      🎯 Found button: '{btn_text}'")
                        target_btn = btn
                        break

            # =========================================================
            # CHIẾN THUẬT 2: TÌM THEO CLASS
            # =========================================================
            if not target_btn or not target_btn.is_visible():
                class_selectors = [
                    "button.btn-primary",
                    "button.btn-success",
                    "button.btn-info",
                    "input[type='submit']",
                ]
                for sel in class_selectors:
                    btn = scope.locator(sel).last
                    if btn.count() > 0 and btn.is_visible():
                        target_btn = btn
                        print(f"      ⚠️ Fallback class match: {sel}")
                        break

            # =========================================================
            # THỰC HIỆN CLICK
            # =========================================================
            if target_btn and target_btn.is_visible():
                target_btn.scroll_into_view_if_needed()
                time.sleep(0.5)
                target_btn.click(force=True)
                print("      ✅ Clicked successfully.")

                # Gọi hàm wait của bạn (nếu class có method này)
                if hasattr(self, "_wait_after_save"):
                    self._wait_after_save(page)
                else:
                    # Logic wait mặc định nếu chưa có hàm riêng
                    try:
                        page.wait_for_load_state("networkidle", timeout=3000)
                    except:
                        time.sleep(2)

                return "Success"

            print("      ❌ Không tìm thấy nút Save/Action nào khả thi.")
            return "Fail"

        except Exception as e:
            print(f"      ⚠️ Save Error: {e}")
            return "Error"
        finally:
            # Gỡ listener để không ảnh hưởng các bước sau
            try:
                page.remove_listener("dialog", handle_dialog)
            except:
                pass

    def _wait_after_save(self, page):
        """Hàm phụ: Chờ thông báo thành công hoặc Popup đóng lại"""
        time.sleep(1)
        try:
            # Chờ Toast Message xanh lá hiện lên
            page.locator(".toast-success, .alert-success").wait_for(
                state="visible", timeout=2000
            )
            print("      ✅ Thành công (Toast detected).")
        except:
            pass

        try:
            # Chờ Modal đóng lại (nếu vừa bấm trong modal)
            page.locator(".modal-backdrop").wait_for(state="hidden", timeout=2000)
        except:
            pass

    def close_popup(self, page):
        try:
            page.keyboard.press("Escape")
            btn = page.locator("button:has-text('Close')").first
            if btn.is_visible():
                btn.click()
        except:
            pass

    # --- HÀM NÂNG CẤP: QUÉT TAB DỰA TRÊN TEXT ---
    def scan_all_tabs(self, page, data_dict):
        print(f"   🕵️ Deep Scan: Duyệt toàn bộ các Tab để cập nhật: {data_dict}")

        # --- FIX QUAN TRỌNG: CHẶN SCAN RỖNG ---
        # Nếu không có dữ liệu cần điền, Return ngay, KHÔNG Save
        if not data_dict:
            print("      ⚠️ Scan Data is empty. Doing nothing to preserve state.")
            return

        # --- BƯỚC 1: CHỜ ỔN ĐỊNH TRANG ---
        # Rất quan trọng: Chờ sau khi click Edit để trang load xong sidebar
        time.sleep(2)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass
        if not data_dict:
            print(
                "      ⚠️ Scan Data is empty. Skipping scan to prevent premature Save."
            )
            return

        # --- BƯỚC 2: THỬ ĐIỀN NGAY TẠI CHỖ (Try-First)
        # Nếu form đang mở sẵn đúng tab (thường là Grabbag Info), điền luôn!
        print("      👉 Thử điền form trên màn hình hiện tại trước...")
        done_count = self._smart_update_form(page, data_dict, strict_mode=True)

        # Chỉ Save nếu thực sự đã điền đủ dữ liệu
        if done_count > 0 and done_count == len(data_dict):
            print("      🎉 Đã điền xong tất cả dữ liệu ngay tại trang đầu.")
            self._save_form(page)
            return

        # --- BƯỚC 3: TÌM SIDEBAR (BỘ LỌC NGHIÊM NGẶT) ---
        # Chỉ tìm các element bên trái (x < 300) và không quá cao (y > 80) để tránh Top Menu
        sidebar_keywords = [
            "Grabbag Info",
            "Bag Token",
            "Display Info",
            "Odds",
            "Pulls & Pools",
        ]
        potential_tabs = []

        # Tìm theo keyword
        for kw in sidebar_keywords:
            found = page.locator(
                f"a:has-text('{kw}'), div[role='button']:has-text('{kw}'), li:has-text('{kw}')"
            ).all()
            potential_tabs.extend([el for el in found if el.is_visible()])

        # Nếu không thấy keyword, tìm theo class
        if not potential_tabs:
            potential_tabs = page.locator(
                ".sidebar a, .nav-pills a, .list-group-item"
            ).all()

        unique_tabs = []
        seen_texts = set()

        for tab in potential_tabs:
            try:
                txt = tab.inner_text().strip()
                if txt and txt not in seen_texts:
                    box = tab.bounding_box()
                    if box:
                        # QUY TẮC VÀNG: Tab phải nằm bên trái và dưới Header
                        is_sidebar = box["x"] < 300 and box["y"] > 80
                        if is_sidebar:
                            unique_tabs.append(tab)
                            seen_texts.add(txt)
                        else:
                            # print(f"      🚫 Bỏ qua tab '{txt}' vì vị trí không giống sidebar (x={box['x']}, y={box['y']})")
                            pass
            except:
                pass

        print(f"      📍 Phát hiện {len(unique_tabs)} tabs sidebar hợp lệ.")

        # --- BƯỚC 4: DUYỆT TAB ---
        for i, tab in enumerate(unique_tabs):
            try:
                tab_name = tab.inner_text().split("\n")[0].strip()
                # Kiểm tra tab này có active không
                classes = tab.get_attribute("class") or ""
                is_active = "active" in classes or "selected" in classes

                print(f"      👉 Tab [{i+1}]: {tab_name}")
                if not is_active:
                    tab.click()
                    time.sleep(1.0)  # Chờ tab load

                # Điền form
                count = self._smart_update_form(page, data_dict, strict_mode=True)

                # Nếu điền được gì đó -> Bấm Save & Continue
                if count > 0:
                    res = self._save_form(page)
                    if res == "Continue":
                        print("         ⏭️ Auto-advancing...")
                        time.sleep(3)

            except Exception as e:
                print(f"         ⚠️ Skip tab: {e}")

    # ============================
    # CHECK FIELDS IN TABS (Kiểm tra field có giá trị hay không)
    # ============================
    def check_fields_in_tabs(self, page, tabs_dict):
        """
        Duyệt qua từng tab trong sidebar, kiểm tra các field có giá trị hay không.
        - Nếu field CÓ giá trị → FAIL (unexpected value present)
        - Nếu field KHÔNG có giá trị → PASS (empty as expected)

        Args:
            tabs_dict: dict dạng {"Tab Name": ["Field1", "Field2"], ...}
                       hoặc list ["Field1", "Field2"] (áp dụng cho tab hiện tại)

        Returns:
            list of report_logs [{step, status, details}]
        """
        logs = []

        # Normalize input: nếu là list thuần thì wrap vào dict với tab "_current_"
        if isinstance(tabs_dict, list):
            tabs_dict = {"_current_": tabs_dict}

        if not tabs_dict:
            print("      ⚠️ check_fields_in_tabs: No tabs/fields provided.")
            return logs

        print(f"   🔎 Check Fields In Tabs: {tabs_dict}")
        time.sleep(1.5)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass

        for tab_name, field_names in tabs_dict.items():
            # ── Bước 1: Chuyển sang tab nếu không phải _current_
            if tab_name != "_current_":
                try:
                    print(f"      🗂️ Switching to tab: '{tab_name}'")
                    tab_el = None

                    # Tìm tab trong sidebar (bên trái)
                    tab_candidates = (
                        page.locator("a, li, div[role='button'], button, span")
                        .filter(has_text=re.compile(re.escape(tab_name), re.IGNORECASE))
                        .all()
                    )
                    visible_tabs = [el for el in tab_candidates if el.is_visible()]
                    for el in visible_tabs:
                        box = el.bounding_box()
                        if box and box["x"] < 350:  # Nằm bên trái = sidebar
                            tab_el = el
                            break

                    if tab_el:
                        tab_el.click()
                        time.sleep(1.5)
                        print(f"         ✅ Clicked tab '{tab_name}'")
                    else:
                        print(f"         ⚠️ Tab '{tab_name}' not found in sidebar")
                        logs.append(
                            {
                                "step": f"Tab: {tab_name}",
                                "status": "WARN",
                                "details": "Tab not found in sidebar",
                            }
                        )
                except Exception as e:
                    print(f"         ❌ Error switching to tab '{tab_name}': {e}")
                    logs.append(
                        {
                            "step": f"Tab: {tab_name}",
                            "status": "FAIL",
                            "details": str(e),
                        }
                    )
                    continue

            # ── Bước 2: Kiểm tra từng field trong tab đó
            if isinstance(field_names, str):
                field_names = [field_names]

            for field_name in field_names:
                try:
                    value = self._get_field_current_value(page, field_name)
                    has_value = value is not None and str(value).strip() not in (
                        "",
                        "None",
                        "__empty__",
                    )

                    # Logic: có giá trị → FAIL, không có → PASS
                    status = "FAIL" if has_value else "PASS"
                    detail_msg = (
                        f"Field '{field_name}' in [{tab_name}] has value: '{value}'"
                        if has_value
                        else f"Field '{field_name}' in [{tab_name}] is empty"
                    )
                    icon = "❌" if has_value else "✅"
                    print(f"         {icon} {detail_msg} → {status}")
                    logs.append(
                        {
                            "step": f"Check: {field_name}",
                            "status": status,
                            "details": detail_msg,
                        }
                    )
                except Exception as e:
                    print(f"         ⚠️ Cannot check field '{field_name}': {e}")
                    logs.append(
                        {
                            "step": f"Check: {field_name}",
                            "status": "WARN",
                            "details": f"Could not inspect field: {e}",
                        }
                    )

        return logs

    def _get_field_current_value(self, page, field_name):
        """
        Tìm field theo label và đọc giá trị hiện tại của nó.
        Hỗ trợ: input text, select/dropdown, toggle/checkbox, textarea.
        Trả về None nếu không tìm thấy field.
        """
        label_lower = field_name.lower().strip()
        safe_re = re.compile(re.escape(field_name), re.IGNORECASE)

        # Tìm label element trước
        label_candidates = (
            page.locator("label, legend, th, span, div, b, strong, td, p")
            .filter(has_text=safe_re)
            .all()
        )
        visible_labels = [el for el in label_candidates if el.is_visible()]

        # Ưu tiên label khớp chính xác
        exact = [
            el
            for el in visible_labels
            if el.inner_text().strip().lower() == label_lower
        ]
        candidates = exact if exact else visible_labels

        for label_el in candidates:
            try:
                # === Chiến lược 1: Tìm input trong cùng container (td, div.row, div.form-group) ===
                parent = label_el
                for _ in range(5):  # Đi lên tối đa 5 cấp
                    try:
                        parent = parent.locator("xpath=..").first
                        # Tìm input/select/textarea trong container này
                        for sel in [
                            "input[type='text']:visible",
                            "input[type='number']:visible",
                            "input[type='email']:visible",
                            "input:not([type='hidden']):not([type='submit']):not([type='button']):visible",
                            "select:visible",
                            "textarea:visible",
                        ]:
                            els = parent.locator(sel).all()
                            for el in els:
                                if not el.is_visible():
                                    continue
                                tag = el.evaluate("e => e.tagName.toLowerCase()")
                                if tag == "select":
                                    val = el.evaluate(
                                        "e => e.options[e.selectedIndex]?.text?.trim() || ''"
                                    )
                                else:
                                    val = el.input_value()
                                if val is not None:
                                    return val if val.strip() else None
                        # Tìm toggle/checkbox
                        toggles = parent.locator(
                            "input[type='checkbox']:visible, .toggle:visible, [role='switch']:visible"
                        ).all()
                        for tog in toggles:
                            is_checked = tog.is_checked()
                            if is_checked:
                                return "checked"
                            # unchecked = effectively empty
                            return None
                    except:
                        break

                # === Chiến lược 2: Tìm sibling input sau label ===
                try:
                    sibling_input = page.locator(
                        f"label:has-text('{field_name}') + input, "
                        f"label:has-text('{field_name}') ~ input, "
                        f"label:has-text('{field_name}') + select, "
                        f"label:has-text('{field_name}') ~ select"
                    ).first
                    if sibling_input.count() > 0 and sibling_input.is_visible():
                        tag = sibling_input.evaluate("e => e.tagName.toLowerCase()")
                        if tag == "select":
                            val = sibling_input.evaluate(
                                "e => e.options[e.selectedIndex]?.text?.trim() || ''"
                            )
                        else:
                            val = sibling_input.input_value()
                        return val if val and val.strip() else None
                except:
                    pass

            except Exception as e:
                print(f"            ⚠️ label candidate error: {e}")
                continue

        # Fallback: không tìm thấy gì
        return None

    def _find_input_element(self, page, label_text):
        print(f"         🔍 Searching for field: '{label_text}'")
        label_lower = label_text.lower().strip()
        # Tạo version không space/underscore để fuzzy match
        label_normalized = re.sub(r"[\s_-]+", "", label_lower)

        # ========================================
        # PRIORITY 0: Direct ID/Name Match (Highest Priority)
        # Tìm element có ID hoặc name khớp với label (underscore/hyphen format)
        # VD: "Boost Result Value2" -> ID "boost_result_value2"
        # ========================================
        label_id_format = label_lower.replace(" ", "_").replace("-", "_")
        direct_by_id = page.locator(
            f"#{label_id_format}, [name='{label_id_format}']"
        ).first
        if direct_by_id.count() > 0 and direct_by_id.is_visible():
            print(f"         🎯 DIRECT MATCH by ID/name: '{label_id_format}'")
            return direct_by_id

        # Try with hyphens too
        label_id_hyphen = label_lower.replace(" ", "-").replace("_", "-")
        direct_by_id_hyphen = page.locator(
            f"#{label_id_hyphen}, [name='{label_id_hyphen}']"
        ).first
        if direct_by_id_hyphen.count() > 0 and direct_by_id_hyphen.is_visible():
            print(f"         🎯 DIRECT MATCH by ID/name (hyphen): '{label_id_hyphen}'")
            return direct_by_id_hyphen

        # ========================================
        # SECTION-AWARE SEARCH: Handle "Section Name Field Name" patterns
        # VD: "PreEvent Phase Start Date Time(UTC)" → section="PreEvent Phase", field="Start Date Time(UTC)"
        # VD: "Active Phase End Date Time (UTC)" → section="Active Phase", field="End Date Time (UTC)"
        # ========================================
        section_result = self._try_section_aware_search(page, label_text)
        if section_result:
            return section_result

        # ========================================
        # SPECIAL CASE: "New Event ID", "New ID", "New Section ID"
        # Form Clone có input với placeholder chứa "suffix" hoặc label chứa "New"
        # ========================================
        if "new" in label_lower and "id" in label_lower:
            # Case 1: Tìm input có placeholder chứa "suffix"
            suffix_input = page.locator("input[placeholder*='suffix' i]").first
            if suffix_input.count() > 0 and suffix_input.is_visible():
                print(f"         🎯 Found suffix input for '{label_text}'")
                return suffix_input

            # Case 2: Tìm input có placeholder chứa "new" hoặc name chứa "new"
            new_input = page.locator(
                "input[placeholder*='new' i], input[name*='new' i]"
            ).first
            if new_input.count() > 0 and new_input.is_visible():
                print(
                    f"         🎯 Found new input by placeholder/name for '{label_text}'"
                )
                return new_input

            # Case 3: Fallback - Tìm input trong row chứa label "New ... ID"
            row = (
                page.locator("tr, div.form-group, div.row, div.col")
                .filter(has_text=re.compile(r"New.*ID", re.IGNORECASE))
                .first
            )
            if row.count() > 0:
                input_in_row = row.locator(
                    "input[type='text']:visible"
                ).last  # Lấy cái cuối (suffix)
                if input_in_row.count() > 0:
                    print(f"         🎯 Found input in row for '{label_text}'")
                    return input_in_row

        safe_label = re.compile(re.escape(label_text), re.IGNORECASE)

        # [FIX] PREMIER STRATEGY: Trước hết tìm label + parent container + element trong container đó
        # Đây là cách đáng tin cậy nhất để tránh bỏ qua hoặc chọn nhầm
        try:
            label_candidates = (
                page.locator("label, legend, span, h5, th, strong, div, b")
                .filter(has_text=safe_label)
                .all()
            )
            visible_candidates = [c for c in label_candidates if c.is_visible()]

            # [FIX] Sort candidates: exact match first, then by text length (shorter = more precise)
            def _premier_sort_key(el):
                try:
                    txt = el.inner_text().strip().lower()
                    is_exact = txt == label_lower
                    tag = el.evaluate("el => el.tagName")
                    is_label_tag = tag in ["LABEL", "LEGEND"]
                    return (0 if is_exact else 1, 0 if is_label_tag else 1, len(txt))
                except:
                    return (2, 2, 9999)

            visible_candidates.sort(key=_premier_sort_key)

            print(
                f"         📋 Found {len(visible_candidates)} visible label candidates"
            )

            # [NEW] Sắp xếp candidates theo độ match
            for label_el in visible_candidates:
                label_actual_text = label_el.inner_text().strip()

                # [DEBUG] Log which label was checked
                if label_actual_text.lower() == label_lower:
                    print(f"         ✅ Exact label match: '{label_actual_text}'")
                else:
                    print(f"         ~ Partial match: '{label_actual_text[:50]}...'")

                # [CRITICAL] TRỪ CASE: Label chứa radio (skip nếu không exact match)
                has_radio = label_el.locator("input[type='radio']").count() > 0
                if has_radio and label_actual_text.lower() != label_lower:
                    print(f"         ⏭️ Skip (radio label without exact match)")
                    continue

                # [NEW STRATEGY] Tìm parent container (form-group)
                # LUÔN tìm input/select TRONG container này trước, không dùng fallback
                parent_containers = None
                container_source = None
                for xpath in [
                    "xpath=ancestor::div[contains(@class,'form-group')]",
                    "xpath=ancestor::div[contains(@class,'control-group')]",
                    "xpath=ancestor::fieldset",
                    "xpath=ancestor::div[contains(@class,'row')]",
                ]:
                    try:
                        container = label_el.locator(xpath).first
                        if container.count() > 0 and container.is_visible():
                            parent_containers = container
                            container_source = xpath
                            print(f"         🔗 Found parent container: {xpath}")
                            break
                    except:
                        pass

                if parent_containers:
                    # [CRITICAL] Tìm input/select TRONG container này
                    # Không dùng sibling/following, chỉ dùng child elements
                    elements = parent_containers.locator(
                        "select, input:not([type='radio']):not([type='button']):not([type='hidden']), textarea"
                    ).all()

                    print(
                        f"         📦 Found {len(elements)} input/select elements in container"
                    )

                    if len(elements) > 0:
                        # [FIX] Tìm element VISIBLE đầu tiên, KHÔNG lấy mù elements[0]
                        element = None
                        for _el in elements:
                            if _el.is_visible():
                                # [FIX] Validate: element name/id phải liên quan đến label
                                _el_name = (_el.get_attribute("name") or "").lower()
                                _el_id = (_el.get_attribute("id") or "").lower()
                                _el_tag = _el.evaluate("el => el.tagName")
                                _label_norm = label_lower.replace(" ", "_").replace(
                                    "-", "_"
                                )
                                _label_words = [
                                    w for w in _label_norm.split("_") if len(w) > 2
                                ]

                                # Check if element is related to label
                                _is_related = False
                                # Direct name/id match
                                if _label_norm in _el_name or _label_norm in _el_id:
                                    _is_related = True
                                elif _el_name in _label_norm and _el_name:
                                    _is_related = True
                                elif _el_id in _label_norm and _el_id:
                                    _is_related = True
                                else:
                                    # Word-level match
                                    for _w in _label_words:
                                        if _w in _el_name or _w in _el_id:
                                            _is_related = True
                                            break
                                        # Singular form (schedules -> schedule)
                                        if _w.endswith("s") and (
                                            _w[:-1] in _el_name or _w[:-1] in _el_id
                                        ):
                                            _is_related = True
                                            break

                                # Nếu container nhỏ (form-group/control-group), accept thậm chí không related
                                _is_tight_container = container_source in [
                                    "xpath=ancestor::div[contains(@class,'form-group')]",
                                    "xpath=ancestor::div[contains(@class,'control-group')]",
                                    "xpath=ancestor::fieldset",
                                ]

                                if _is_related or _is_tight_container:
                                    element = _el
                                    break
                                else:
                                    print(
                                        f"         ⏭️ Skip visible but unrelated element: tag={_el_tag}, name='{_el_name}', id='{_el_id}'"
                                    )

                        if not element:
                            # Fallback: nếu tất cả visible elements đều không related, thử lấy first visible
                            for _el in elements:
                                if _el.is_visible():
                                    element = _el
                                    print(
                                        f"         ⚠️ Using first visible element as fallback"
                                    )
                                    break

                        if not element:
                            print(
                                f"         ⚠️ All {len(elements)} elements in container are hidden, skip"
                            )
                            continue

                        print(f"         ✅ Found element in same form-group container")

                        # Validate: Kiểm tra element name/id có liên quan đến label không
                        el_name = element.get_attribute("name") or ""
                        el_id = element.get_attribute("id") or ""
                        el_type = element.evaluate("el => el.tagName") or "UNKNOWN"

                        print(
                            f"         🔍 Element: tag={el_type}, name='{el_name}', id='{el_id}'"
                        )

                        # Nếu element là select, check name/id để tránh nhầm lẫn
                        if el_type == "SELECT":
                            el_name_norm = el_name.lower().replace("-", "_")
                            el_id_norm = el_id.lower().replace("-", "_")
                            label_norm = label_lower.replace(" ", "_").replace("-", "_")

                            # [FIX] More strict validation - check if any significant word from label appears in element name/id
                            # VD: "Leaderboard Types" -> words: ["leaderboard", "types", "type"]
                            label_words = label_norm.split("_")
                            # Remove common words that don't add meaning
                            meaningful_words = [
                                w
                                for w in label_words
                                if len(w) > 2 and w not in ["the", "and", "for"]
                            ]

                            # Also check singular form (types -> type)
                            expanded_words = meaningful_words.copy()
                            for word in meaningful_words:
                                if word.endswith("s"):
                                    expanded_words.append(word.rstrip("s"))

                            # Check if ANY meaningful word from label appears in element name/id
                            is_related = False
                            for word in expanded_words:
                                if word in el_name_norm or word in el_id_norm:
                                    is_related = True
                                    break

                            # [DEBUG] Log validation details
                            print(
                                f"         🔬 Validation: label_norm='{label_norm}', meaningful_words={meaningful_words}"
                            )
                            print(
                                f"         🔬 Element: name_norm='{el_name_norm}', id_norm='{el_id_norm}'"
                            )
                            print(f"         ✓ Related: {is_related}")

                            # [FIX] Nếu name/id không match NHƯNG chỉ có 1 element duy nhất trong container
                            # → Cho phép vì có thể đây là field đúng (tránh bỏ qua)
                            if not is_related:
                                if len(elements) == 1:
                                    print(
                                        f"         ⚠️ Element name/id không match label, NHƯNG chỉ có 1 element → Accept"
                                    )
                                    is_related = True  # Override
                                else:
                                    print(
                                        f"         ⚠️ Element name/id không match label, skip container này"
                                    )
                                    continue

                        # Element tìm thấy trong container - check if visible
                        if not element.is_visible():
                            # Hidden SELECT - tìm wrapper
                            if el_type == "SELECT":
                                wrapper = self._find_custom_dropdown_wrapper(element)
                                if wrapper:
                                    print(
                                        f"         ✅ Found wrapper for hidden SELECT"
                                    )
                                    return wrapper

                        print(f"         ✅ Returning element from container search")
                        return element
        except Exception as e:
            print(f"         ⚠️ Container-based search error: {e}")

        # [OLD CODE] Fallback đến label candidates search
        candidates = (
            page.locator("label, legend, span, h5, th, strong, div, b")
            .filter(has_text=safe_label)
            .all()
        )
        visible_candidates = [c for c in candidates if c.is_visible()]

        # [NEW] FUZZY MATCHING: Nếu không tìm thấy exact match, tìm fuzzy match
        # VD: "New SectionID" sẽ match với "New Section ID"
        if not visible_candidates:
            all_labels = page.locator("label, legend, span, h5, th, strong").all()
            for lbl in all_labels:
                if lbl.is_visible():
                    lbl_text = lbl.inner_text().strip().lower()
                    lbl_normalized = re.sub(r"[\s_-]+", "", lbl_text)
                    if lbl_normalized == label_normalized:
                        visible_candidates.append(lbl)
                        print(
                            f"         🔍 Fuzzy Match: '{label_text}' matched with '{lbl.inner_text()}'"
                        )

        # SORT: Ưu tiên EXACT MATCH (text ngắn nhất khớp với label_text)
        # Sau đó ưu tiên thẻ LABEL hoặc LEGEND
        def sort_key(el):
            text = el.inner_text().strip().lower()
            is_exact = text == label_lower
            tag = el.evaluate("el => el.tagName")
            is_label_or_legend = tag in ["LABEL", "LEGEND"]
            text_len = len(text)
            # Ưu tiên: exact match -> label/legend tag -> text ngắn nhất
            return (0 if is_exact else 1, 0 if is_label_or_legend else 1, text_len)

        visible_candidates.sort(key=sort_key)

        print(f"         📋 Found {len(visible_candidates)} label candidates")

        for label_el in visible_candidates:
            # ========================================
            # [FIX] SKIP: Label chứa RADIO BUTTON
            # Tránh việc tìm "Currency" mà click nhầm vào radio "Auto Generate a new currency"
            # ========================================
            has_radio = label_el.locator("input[type='radio']").count() > 0
            if has_radio:
                # Chỉ skip nếu text KHÔNG khớp chính xác
                label_text_actual = label_el.inner_text().strip().lower()
                if label_text_actual != label_text.lower():
                    print(
                        f"         ⏭️ Skip radio label: '{label_el.inner_text().strip()[:30]}...'"
                    )
                    continue

            # [NEW] SPECIAL: Nếu là LEGEND tag, tìm trong parent fieldset
            tag = label_el.evaluate("el => el.tagName")
            if tag == "LEGEND":
                try:
                    # Tìm fieldset chứa legend này
                    fieldset = label_el.locator("xpath=ancestor::fieldset").first
                    if fieldset.count() > 0:
                        # Tìm multiselect wrapper trong fieldset
                        multiselect = fieldset.locator("div.multiselect").first
                        if multiselect.count() > 0 and multiselect.is_visible():
                            print(
                                f"         🎯 Found multiselect in fieldset for legend '{label_text}'"
                            )
                            return multiselect

                        # Tìm select/input trong fieldset
                        field = fieldset.locator(
                            "select, input:not([type='radio']), textarea"
                        ).first
                        if field.count() > 0:
                            # Nếu select ẩn, tìm wrapper
                            if (
                                not field.is_visible()
                                and field.evaluate("el => el.tagName") == "SELECT"
                            ):
                                wrapper = self._find_custom_dropdown_wrapper(field)
                                if wrapper:
                                    return wrapper
                            return field
                except:
                    pass

            # A. Check 'for' attribute (HIGHEST PRIORITY)
            for_attr = label_el.get_attribute("for")
            if for_attr:
                print(f"         🔗 Label has for='{for_attr}'")
                target = page.locator(f"#{for_attr}").first
                if target.count() > 0:
                    # [FIX] Skip nếu target là radio
                    target_type = target.get_attribute("type")
                    if target_type == "radio":
                        print(f"         ⏭️ Skip radio target for '{for_attr}'")
                        continue

                    # [FIX CRITICAL] Validate target match với label text
                    # Tránh trường hợp tìm nhầm element không liên quan
                    # VD: Label "Leaderboard Types" có for="tag" nhưng tag là field khác
                    try:
                        # Kiểm tra xem target có phải là field đúng không bằng cách:
                        # 1. So sánh name attribute với label text
                        # 2. So sánh id với label text (normalized)
                        target_id = target.get_attribute("id") or ""
                        target_name = target.get_attribute("name") or ""

                        # Normalize label và target để so sánh
                        label_normalized = label_lower.replace(" ", "_").replace(
                            "-", "_"
                        )
                        id_normalized = target_id.replace("-", "_").lower()
                        name_normalized = target_name.replace("-", "_").lower()

                        # Check if target ID/name relates to label
                        is_related = (
                            label_normalized in id_normalized
                            or id_normalized in label_normalized
                            or label_normalized in name_normalized
                            or name_normalized in label_normalized
                        )

                        if not is_related:
                            # ID/name không liên quan → Có thể tìm nhầm
                            print(
                                f"         ⚠️ Target id/name ('{target_id}'/'{target_name}') doesn't match label '{label_text}'"
                            )
                            print(f"         🔍 Searching for better match...")

                            # Tìm element có ID/name khớp với label
                            # VD: "Leaderboard Types" → tìm id="leaderboard_type" hoặc name="leaderboard_type"
                            better_match = None

                            # Pattern 1: leaderboard_type, leaderboard-type, leaderboardtype
                            id_patterns = [
                                label_normalized,
                                label_normalized.rstrip("s"),  # "types" -> "type"
                                label_lower.replace(" ", "_"),
                                label_lower.replace(" ", "-"),
                                label_lower.replace(" ", ""),
                            ]

                            # [FIX] Thu thập TẤT CẢ candidates match pattern
                            all_candidates = []

                            for pattern in id_patterns:
                                # Try by ID - collect all matches
                                candidates_by_id = page.locator(
                                    f"#{pattern}, [id*='{pattern}']"
                                ).all()
                                for cand in candidates_by_id:
                                    if cand.is_visible():
                                        all_candidates.append(("id", pattern, cand))

                                # Try by name - collect all matches
                                candidates_by_name = page.locator(
                                    f"[name='{pattern}'], [name*='{pattern}']"
                                ).all()
                                for cand in candidates_by_name:
                                    if cand.is_visible():
                                        all_candidates.append(("name", pattern, cand))

                            if all_candidates:
                                print(
                                    f"         📋 Found {len(all_candidates)} potential matches"
                                )

                                # [STRATEGY 1] Chọn candidate TRONG CÙNG CONTAINER với label
                                label_containers = []
                                try:
                                    for container_xpath in [
                                        "xpath=ancestor::div[contains(@class,'form-group')]",
                                        "xpath=ancestor::div[contains(@class,'control-group')]",
                                        "xpath=ancestor::fieldset",
                                        "xpath=ancestor::div[contains(@class,'row')]",
                                        "xpath=../..",  # 2 levels up
                                    ]:
                                        container = label_el.locator(
                                            container_xpath
                                        ).first
                                        if container.count() > 0:
                                            label_containers.append(container)
                                except:
                                    pass

                                # Check candidates trong container
                                for match_type, pattern, cand in all_candidates:
                                    for label_container in label_containers:
                                        try:
                                            # Check if candidate is child of label's container
                                            container_inputs = label_container.locator(
                                                "select, input"
                                            ).all()
                                            for ci in container_inputs:
                                                try:
                                                    if ci.evaluate(
                                                        "(el, other) => el.isSameNode(other)",
                                                        cand,
                                                    ):
                                                        better_match = cand
                                                        print(
                                                            f"         ✅ Found match in same container by {match_type}: '{pattern}'"
                                                        )
                                                        break
                                                except:
                                                    pass
                                            if better_match:
                                                break
                                        except:
                                            pass
                                    if better_match:
                                        break

                                # [STRATEGY 2] Nếu không tìm được trong container, chọn GẦN NHẤT với label
                                if not better_match:
                                    try:
                                        label_box = label_el.bounding_box()
                                        if label_box:
                                            min_distance = float("inf")
                                            closest_candidate = None

                                            for (
                                                match_type,
                                                pattern,
                                                cand,
                                            ) in all_candidates:
                                                try:
                                                    cand_box = cand.bounding_box()
                                                    if cand_box:
                                                        # Tính khoảng cách
                                                        distance = abs(
                                                            cand_box["x"]
                                                            - label_box["x"]
                                                        ) + abs(
                                                            cand_box["y"]
                                                            - label_box["y"]
                                                        )

                                                        # Ưu tiên field DƯỚI hoặc PHẢI label
                                                        is_below_or_right = (
                                                            cand_box["y"]
                                                            >= label_box["y"] - 50
                                                        )

                                                        if (
                                                            distance < min_distance
                                                            and is_below_or_right
                                                        ):
                                                            min_distance = distance
                                                            closest_candidate = (
                                                                match_type,
                                                                pattern,
                                                                cand,
                                                            )
                                                except:
                                                    pass

                                            if closest_candidate:
                                                match_type, pattern, cand = (
                                                    closest_candidate
                                                )
                                                better_match = cand
                                                print(
                                                    f"         ✅ Found closest match by {match_type} ({min_distance:.0f}px): '{pattern}'"
                                                )
                                    except:
                                        pass

                                # [STRATEGY 3] Fallback: Lấy candidate đầu tiên
                                if not better_match and all_candidates:
                                    match_type, pattern, cand = all_candidates[0]
                                    better_match = cand
                                    print(
                                        f"         ⚠️ Using first match by {match_type}: '{pattern}'"
                                    )

                            if better_match:
                                target = better_match
                            else:
                                print(
                                    f"         ⚠️ No better match found, using original target #{for_attr}"
                                )

                    except Exception as validate_err:
                        print(f"         ⚠️ Validation error: {validate_err}")
                        # Continue with original target

                    print(
                        f"         ✅ Found target by for attribute: #{target.get_attribute('id') or for_attr}"
                    )

                    # Nếu target bị ẩn (Select), thử tìm wrapper ngay lập tức
                    if not target.is_visible():
                        tag_name = target.evaluate("el => el.tagName")
                        if tag_name == "SELECT":
                            print(
                                f"         🔍 Target is hidden SELECT, looking for wrapper..."
                            )
                            wrapper = self._find_custom_dropdown_wrapper(target)
                            if wrapper:
                                print(f"         ✅ Found custom dropdown wrapper")
                                return wrapper
                    return target

            # B. Check Input lồng bên trong (SKIP RADIO)
            nested = label_el.locator(
                "input:not([type='radio']), select, textarea"
            ).first
            if nested.count() > 0:
                if (
                    not nested.is_visible()
                    and nested.evaluate("el => el.tagName") == "SELECT"
                ):
                    wrapper = self._find_custom_dropdown_wrapper(nested)
                    if wrapper:
                        return wrapper
                return nested

            # C. Check Sibling (Input/Select2/Chosen/Multiselect nằm ngay sau Label)
            # [FIX]: Loại bỏ radio khỏi xpath, thêm multiselect
            sibling = label_el.locator(
                "xpath=following::input[not(@type='radio')] | following::select | following::textarea | following::span[contains(@class,'select2-container')] | following::div[contains(@class,'chosen-container')] | following::div[contains(@class,'multiselect')]"
            ).first

            if sibling.count() > 0:
                # Nếu tìm thấy wrapper hiển thị ngay -> Trả về
                if sibling.is_visible():
                    return sibling

                # Nếu tìm thấy select ẩn -> Tìm wrapper của nó
                tag = None
                try:
                    tag = sibling.evaluate("el => el.tagName")
                except:
                    pass

                if tag == "SELECT" and not sibling.is_visible():
                    wrapper = self._find_custom_dropdown_wrapper(sibling)
                    if wrapper:
                        return wrapper
                return sibling

            try:
                parent = label_el.locator("xpath=..")
                cousin = parent.locator("input, select, textarea").first
                if cousin.count() > 0:
                    return cousin
            except:
                pass

        placeholder = page.locator(f"[placeholder='{label_text}']").first
        if placeholder.count() > 0:
            return placeholder

        # [NEW] Fallback: Tìm dropdown wrapper gần với label text
        # Dùng cho trường hợp không tìm được bằng cách thông thường
        try:
            # Tìm tất cả dropdown wrappers hiển thị
            wrappers = page.locator(
                "div.multiselect, div.chosen-container, span.select2-container"
            ).all()
            visible_wrappers = [w for w in wrappers if w.is_visible()]

            if visible_wrappers:
                # Tìm wrapper gần nhất với text label
                for wrapper in visible_wrappers:
                    try:
                        # Check xem có text label gần wrapper này không
                        parent = wrapper.locator(
                            "xpath=ancestor::div[@class='form-group'] | ancestor::fieldset | ancestor::div[contains(@class,'col')]"
                        ).first
                        if parent.count() > 0:
                            parent_text = parent.inner_text().lower()
                            if label_lower in parent_text:
                                print(
                                    f"         🎯 Found wrapper by proximity for '{label_text}'"
                                )
                                return wrapper
                    except:
                        pass
        except:
            pass

        # [NEW] Fallback 2: Tìm select element hiển thị có label gần
        # [IMPROVED] Hạn chế scope để tránh bỏ qua field đúng
        try:
            selects = page.locator("select:visible").all()
            # [FIX] Sort selects by proximity to visible labels (làm giảm false matches)
            label_candidates_boxes = []
            for cand in visible_candidates:
                try:
                    box = cand.bounding_box()
                    if box:
                        label_candidates_boxes.append(box)
                except:
                    pass

            for sel in selects:
                try:
                    # [CRITICAL] Nếu select có name/id khác biệt xa so với label, BỎ QUA
                    # VD: Label "Leaderboard Types" không nên match select có name="rbe_id"
                    sel_name = sel.get_attribute("name") or ""
                    sel_id = sel.get_attribute("id") or ""

                    # Check if select name/id is related to label
                    sel_name_normalized = sel_name.lower().replace("-", "_")
                    sel_id_normalized = sel_id.lower().replace("-", "_")
                    label_normalized = label_lower.replace(" ", "_")

                    # Build list of acceptable name patterns
                    acceptable_patterns = [
                        label_normalized,  # "leaderboard_types"
                        label_normalized.rstrip("s"),  # "leaderboard_type"
                        label_lower.replace(" ", "_"),  # "leaderboard_types"
                        label_lower.replace(" ", "-").lower(),  # "leaderboard-types"
                    ]

                    is_related = False
                    for pattern in acceptable_patterns:
                        if (
                            pattern in sel_name_normalized
                            or pattern in sel_id_normalized
                        ):
                            is_related = True
                            break

                    if not is_related:
                        # Select name/id không liên quan đến label -> BỎ QUA
                        print(
                            f"         ⏭️ Skip unrelated select (name='{sel_name}', id='{sel_id}')"
                        )
                        continue

                    # Tìm label gần select này
                    parent = sel.locator(
                        "xpath=ancestor::div[@class='form-group'] | ancestor::div[contains(@class,'col')]"
                    ).first
                    if parent.count() > 0:
                        parent_text = parent.inner_text().lower()
                        if label_lower in parent_text:
                            print(
                                f"         🎯 Found select by proximity for '{label_text}'"
                            )
                            return sel
                except:
                    pass
        except:
            pass

        print(f"         ❌ Could not find input for '{label_text}'")
        print(f"         💡 Available labels on page:")
        try:
            all_page_labels = page.locator("label:visible").all()[:10]  # First 10
            for lbl in all_page_labels:
                lbl_text = lbl.inner_text().strip()
                lbl_for = lbl.get_attribute("for")
                print(f"            - '{lbl_text[:50]}' (for='{lbl_for}')")
        except:
            pass

        return None

    # ============================
    # SECTION-AWARE FIELD SEARCH
    # ============================
    def _try_section_aware_search(self, page, label_text):
        """
        Tách label thành Section + Field name nếu có prefix section.
        VD: "PreEvent Phase Start Date Time(UTC)" → section="PreEvent Phase", field="Start Date Time(UTC)"
        VD: "Active Phase End Date Time (UTC)" → section="Active Phase", field="End Date Time (UTC)"
        """
        section_prefixes = [
            "PreEvent Phase",
            "Pre-Event Phase",
            "Pre Event Phase",
            "Active Phase",
            "Post Event Settings",
            "Post Event",
        ]

        for prefix in section_prefixes:
            if label_text.lower().startswith(prefix.lower()):
                # Tách field name (phần còn lại sau prefix)
                field_name = label_text[len(prefix) :].strip()
                if field_name:
                    print(
                        f"         🔍 Section-aware: section='{prefix}', field='{field_name}'"
                    )
                    result = self._find_field_in_section(page, prefix, field_name)
                    if result:
                        return result
        return None

    def _find_field_in_section(self, page, section_name, field_name):
        """
        Tìm input trong một section cụ thể (dùng khi có nhiều section
        có cùng label name, VD: PreEvent Phase vs Active Phase đều có
        "Start Date Time (UTC)")
        """
        try:
            section_lower = section_name.lower().strip()
            field_lower = field_name.lower().strip()

            # ========================================
            # STRATEGY 1: Tìm fieldset/div có header chứa section name
            # ========================================
            container_selectors = [
                "fieldset",
                "div.card",
                "div.panel",
                "div[class*='phase']",
                "div[class*='section']",
                "div.form-section",
                "div.card-body",
            ]

            for sel in container_selectors:
                containers = page.locator(sel).all()

                for container in containers:
                    if not container.is_visible():
                        continue

                    # Kiểm tra xem container có chứa section name trong header không
                    container_text = ""
                    try:
                        container_text = container.inner_text()[:200].lower()
                    except:
                        continue

                    if section_lower not in container_text:
                        continue

                    # Verify là header section (không phải chỉ mentioned trong content)
                    has_section_header = False
                    try:
                        headers = container.locator(
                            "legend, h2, h3, h4, h5, strong, b, .card-header, .panel-heading"
                        ).all()
                        for h in headers:
                            if (
                                h.is_visible()
                                and section_lower in h.inner_text().lower()
                            ):
                                has_section_header = True
                                break
                    except:
                        pass

                    if not has_section_header:
                        continue

                    print(f"         📍 Found section container: '{section_name}'")

                    # Tìm field trong container này
                    field_regex = re.compile(re.escape(field_name), re.IGNORECASE)

                    # Tìm label trong container
                    labels = (
                        container.locator("label, legend, span, strong, b")
                        .filter(has_text=field_regex)
                        .all()
                    )
                    visible_labels = [l for l in labels if l.is_visible()]
                    visible_labels.sort(key=lambda el: len(el.inner_text().strip()))

                    for lbl in visible_labels:
                        lbl_text = lbl.inner_text().strip()
                        if len(lbl_text) > len(field_name) * 3:
                            continue

                        # Tìm input liên kết
                        for_attr = lbl.get_attribute("for")
                        if for_attr:
                            target = page.locator(f"#{for_attr}").first
                            if target.count() > 0:
                                if not target.is_visible():
                                    wrapper = self._find_custom_dropdown_wrapper(target)
                                    if wrapper:
                                        return wrapper
                                print(
                                    f"         ✅ [Section] Found by 'for' attr: #{for_attr}"
                                )
                                return target

                        # Input lồng bên trong label
                        nested = lbl.locator(
                            "input:not([type='radio']), select, textarea"
                        ).first
                        if nested.count() > 0:
                            return nested

                        # Sibling input
                        sibling = lbl.locator(
                            "xpath=following::input[not(@type='radio')][1] | following::select[1]"
                        ).first
                        if sibling.count() > 0 and sibling.is_visible():
                            # Verify sibling is within same section container
                            try:
                                sib_box = sibling.bounding_box()
                                cont_box = container.bounding_box()
                                if sib_box and cont_box:
                                    if (
                                        sib_box["y"] >= cont_box["y"]
                                        and sib_box["y"]
                                        <= cont_box["y"] + cont_box["height"]
                                    ):
                                        print(
                                            f"         ✅ [Section] Found sibling input for '{field_name}'"
                                        )
                                        return sibling
                            except:
                                return sibling

                    # Fallback: Tìm datetime inputs trong section (theo thứ tự Start/End)
                    datetime_inputs = container.locator(
                        "input.flatpickr-input, input[data-toggle='flatpickr'], "
                        "input[data-toggle='datetimepicker'], input.datetimepicker, "
                        "input.datepicker, input[type='datetime-local']"
                    ).all()
                    visible_dt = [i for i in datetime_inputs if i.is_visible()]

                    # Cũng tìm thêm text inputs có khả năng là datetime
                    if not visible_dt:
                        text_inputs = container.locator("input[type='text']").all()
                        for inp in text_inputs:
                            if inp.is_visible():
                                inp_class = (inp.get_attribute("class") or "").lower()
                                inp_placeholder = (
                                    inp.get_attribute("placeholder") or ""
                                ).lower()
                                inp_id = (inp.get_attribute("id") or "").lower()
                                if any(
                                    kw in inp_class + inp_placeholder + inp_id
                                    for kw in [
                                        "date",
                                        "time",
                                        "calendar",
                                        "picker",
                                        "utc",
                                    ]
                                ):
                                    visible_dt.append(inp)

                    if visible_dt:
                        if "start" in field_lower and len(visible_dt) >= 1:
                            print(
                                f"         ✅ [Section] Found START datetime in '{section_name}'"
                            )
                            return visible_dt[0]
                        elif "end" in field_lower and len(visible_dt) >= 2:
                            print(
                                f"         ✅ [Section] Found END datetime in '{section_name}'"
                            )
                            return visible_dt[1]
                        elif len(visible_dt) == 1:
                            return visible_dt[0]

            # ========================================
            # STRATEGY 2: Proximity-based search (tìm theo vị trí Y)
            # Tìm section header trên trang, rồi tìm field phía dưới nó
            # ========================================
            print(f"         🔍 [Section] Strategy 2: Proximity search...")
            section_headers = (
                page.locator("legend, h2, h3, h4, h5, strong, b, span")
                .filter(has_text=re.compile(re.escape(section_name), re.IGNORECASE))
                .all()
            )

            for header in section_headers:
                if not header.is_visible():
                    continue
                header_box = header.bounding_box()
                if not header_box:
                    continue

                # Tìm tất cả labels phía dưới section header
                all_labels = (
                    page.locator("label, legend, span, strong")
                    .filter(has_text=re.compile(re.escape(field_name), re.IGNORECASE))
                    .all()
                )

                for lbl in all_labels:
                    if not lbl.is_visible():
                        continue
                    lbl_box = lbl.bounding_box()
                    if not lbl_box:
                        continue

                    # Label phải nằm DƯỚI section header (y lớn hơn)
                    # và không quá xa (trong khoảng 500px)
                    if (
                        lbl_box["y"] > header_box["y"]
                        and lbl_box["y"] - header_box["y"] < 500
                    ):
                        # Tìm input gần label này
                        for_attr = lbl.get_attribute("for")
                        if for_attr:
                            target = page.locator(f"#{for_attr}").first
                            if target.count() > 0:
                                print(
                                    f"         ✅ [Proximity] Found field '{field_name}' under '{section_name}'"
                                )
                                return target

                        sibling = lbl.locator(
                            "xpath=following::input[not(@type='radio')][1] | following::select[1]"
                        ).first
                        if sibling.count() > 0 and sibling.is_visible():
                            print(
                                f"         ✅ [Proximity] Found sibling for '{field_name}'"
                            )
                            return sibling

            return None
        except Exception as e:
            print(f"         ⚠️ Section search error: {e}")
            return None

    # ============================
    # INLINE EDIT FIELD HANDLER
    # ============================
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
                        page.keyboard.press("Escape")
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

    def _fill_element_smartly(self, page, element, value):
        try:
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
                try:
                    # Clear giá trị cũ
                    element.fill("")
                    time.sleep(0.2)

                    # Điền giá trị mới
                    element.fill(str(value))
                    time.sleep(0.3)

                    # Trigger blur để đóng picker và apply value
                    element.blur()
                    time.sleep(0.3)

                    # Trigger change event
                    element.evaluate(
                        "el => { el.dispatchEvent(new Event('change', {bubbles: true})); }"
                    )

                    print(f"         ✅ [DateTime] Đã điền: '{value}'")
                    return True
                except Exception as e:
                    print(f"         ⚠️ DateTime picker error: {e}, trying fallback...")
                    # Fallback: Dùng JS set value trực tiếp
                    element.evaluate(f"el => el.value = '{value}'")
                    element.evaluate(
                        "el => { el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }"
                    )
                    return True

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
                print(f"         ❌ Element {tag_name} ẩn. Không thể điền.")
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

    def _handle_js_dropdown(self, page, container, value, lib_type="chosen"):
        try:
            value_str = str(value).strip()
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
            # 2. CHỜ DROPDOWN OPTIONS LOAD XONG (Improved with more selectors)
            # ========================================
            print(f"         ⏳ Waiting for dropdown options to load...")
            wait_start = time.time()
            max_wait = 3  # Chờ tối đa 3 giây
            options_loaded = False

            while time.time() - wait_start < max_wait:
                try:
                    if lib_type == "chosen":
                        # [FIX] More comprehensive selectors for Chosen dropdowns
                        options = container.locator(
                            ".chosen-drop .active-result, .chosen-drop li.active-result, "
                            ".chosen-results li"
                        ).all()
                        # Also check dropdown visibility
                        dropdown = container.locator(".chosen-drop").first
                        if dropdown.count() > 0:
                            is_open = "chosen-with-drop" in (
                                container.get_attribute("class") or ""
                            )
                            if not is_open:
                                print(f"         🔄 Dropdown not open yet, waiting...")
                    elif lib_type == "multiselect":
                        options = page.locator(
                            ".multiselect__element, .multiselect__option"
                        ).all()
                    else:
                        options = page.locator(".select2-results__option").all()

                    visible_options = [opt for opt in options if opt.is_visible()]
                    if len(visible_options) > 0:
                        print(
                            f"         ✅ Dropdown loaded ({len(visible_options)} options visible)"
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
                        page.evaluate(
                            """
                            () => {
                                if (typeof jQuery === 'undefined') return;
                                // Try all selects in visible modals first
                                jQuery('.modal.in select, .modal.show select').each(function() {
                                    var $el = jQuery(this);
                                    if ($el.data('select2')) {
                                        try { $el.select2('open'); } catch(e) {}
                                    }
                                });
                                // Fallback: try all selects with select2
                                jQuery('select').each(function() {
                                    var $el = jQuery(this);
                                    if ($el.data('select2')) {
                                        try { $el.select2('open'); } catch(e) {}
                                    }
                                });
                            }
                        """
                        )
                        time.sleep(0.8)
                        # Re-check if options are now visible
                        opts_now = [
                            o
                            for o in page.locator(".select2-results__option").all()
                            if o.is_visible()
                        ]
                        if opts_now:
                            options_loaded = True
                            print(
                                f"         ✅ Select2 opened via jQuery API ({len(opts_now)} options)"
                            )
                    except Exception as _e:
                        print(f"         ⚠️ jQuery Select2 open error: {_e}")

            # ========================================
            # 3. STRATEGY A: Tìm và click TRỰC TIẾP option khớp text (không cần search)
            #    Ưu tiên exact match trước, partial match sau
            #    [FIX] Improved for simple dropdowns with no search (e.g., Bracketed/Normal)
            # ========================================
            clicked_exact = False
            try:
                all_visible_opts = []
                if lib_type == "chosen":
                    # [FIX] More comprehensive selectors for Chosen dropdown options
                    all_visible_opts = [
                        o
                        for o in container.locator(
                            ".chosen-drop .active-result, .chosen-drop li.active-result, "
                            ".chosen-results li"
                        ).all()
                        if o.is_visible()
                    ]
                    # [NEW] Also try global search if container search fails
                    if not all_visible_opts:
                        all_visible_opts = [
                            o
                            for o in page.locator(
                                ".chosen-drop:visible .active-result, .chosen-drop:visible li"
                            ).all()
                            if o.is_visible()
                        ]
                elif lib_type == "multiselect":
                    all_visible_opts = [
                        o
                        for o in page.locator(
                            ".multiselect__element span, .multiselect__option"
                        ).all()
                        if o.is_visible()
                    ]
                else:
                    all_visible_opts = [
                        o
                        for o in page.locator(".select2-results__option").all()
                        if o.is_visible()
                    ]

                print(
                    f"         📋 Found {len(all_visible_opts)} visible options for direct selection"
                )

                value_lower = value_str.lower().replace("_", " ").replace("-", " ")

                # Exact match (bao gồm cả underscore/space variants)
                for opt in all_visible_opts:
                    opt_text = opt.inner_text().strip()
                    opt_lower = opt_text.lower().replace("_", " ").replace("-", " ")
                    if opt_lower == value_lower or opt_text == value_str:
                        opt.click(force=True)  # [FIX] Use force=True for reliability
                        print(
                            f"         ✅ [Dropdown] Exact match clicked: '{opt_text}'"
                        )
                        clicked_exact = True
                        break

                # Partial match (contains)
                if not clicked_exact:
                    for opt in all_visible_opts:
                        opt_text = opt.inner_text().strip()
                        opt_lower = opt_text.lower().replace("_", " ").replace("-", " ")
                        if value_lower in opt_lower or opt_lower in value_lower:
                            opt.click(
                                force=True
                            )  # [FIX] Use force=True for reliability
                            print(
                                f"         ✅ [Dropdown] Partial match clicked: '{opt_text}'"
                            )
                            clicked_exact = True
                            break
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
                            page.evaluate(
                                f"""() => {{
                                    const sel = document.getElementById('{original_id}');
                                    if (sel) {{
                                        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        if (typeof jQuery !== 'undefined') {{
                                            jQuery(sel).trigger('change');
                                        }}
                                    }}
                                }}"""
                            )
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
                time.sleep(1.0)

                wait_start = time.time()
                visible_results = []
                while time.time() - wait_start < 3:
                    try:
                        if lib_type == "chosen":
                            results = container.locator(".active-result").all()
                        elif lib_type == "multiselect":
                            results = page.locator(
                                ".multiselect__element, .multiselect__option"
                            ).all()
                        else:
                            results = page.locator(
                                ".select2-results__option:not(.select2-results__option--load-more)"
                            ).all()

                        visible_results = [r for r in results if r.is_visible()]
                        if len(visible_results) > 0:
                            print(
                                f"         📋 Found {len(visible_results)} search results"
                            )
                            break
                    except:
                        pass
                    time.sleep(0.3)

                # [FIX] Nếu search không ra kết quả → clear search và thử lại với term ngắn hơn
                if not visible_results and "_" in value_str:
                    shorter_term = value_str.split("_")[0]  # Chỉ lấy từ đầu tiên
                    print(f"         🔄 No results, retrying with: '{shorter_term}'")
                    search_box.fill(shorter_term)
                    time.sleep(1.0)
                    wait_start = time.time()
                    while time.time() - wait_start < 2:
                        try:
                            if lib_type == "chosen":
                                results = container.locator(".active-result").all()
                            elif lib_type == "multiselect":
                                results = page.locator(
                                    ".multiselect__element, .multiselect__option"
                                ).all()
                            else:
                                results = page.locator(
                                    ".select2-results__option:not(.select2-results__option--load-more)"
                                ).all()
                            visible_results = [r for r in results if r.is_visible()]
                            if len(visible_results) > 0:
                                print(
                                    f"         📋 Found {len(visible_results)} results with shorter term"
                                )
                                break
                        except:
                            pass
                        time.sleep(0.3)

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
                    if not clicked and visible_results:
                        try:
                            visible_results[0].click()
                            r_text = visible_results[0].inner_text().strip()
                            print(
                                f"         ⚠️ [Dropdown] Clicked first result: '{r_text}'"
                            )
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

    def _switch_to_tab(self, page, tab_name):
        print(f"      🧭 Switching to Tab: '{tab_name}'")
        # Tìm trong sidebar hoặc nav-link
        tab = (
            page.locator(f".nav-link, .list-group-item, .sidebar a")
            .filter(has_text=tab_name)
            .last
        )
        if tab.is_visible():
            tab.click()
            time.sleep(1.0)  # Chờ content bên phải render
        else:
            print(f"      ⚠️ Tab '{tab_name}' not found.")

    def _clean_key(self, key):
        """Loại bỏ các từ khóa hành động thừa để tăng tỷ lệ tìm kiếm thành công"""
        # Xóa các từ: Toggle, Input, Select, Edit, Sửa, Chọn...
        trash_words = [
            "toggle",
            "input",
            "select",
            "edit",
            "sửa",
            "chọn",
            "tick",
            "check",
        ]
        clean_key = key.lower()
        for word in trash_words:
            clean_key = clean_key.replace(word, "")
        return clean_key.strip()
