# automation/form_handler/datetime_handler.py - split from form_handler.py
# Schedule/flatpickr datetime fill + format auto-fix
import time
import re
import random
from playwright.sync_api import Page


class DateTimeHandlerMixin:
    """Schedule/flatpickr datetime fill + format auto-fix"""

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

                            # Skip readonly input nếu không có dấu hiệu datetime picker...
                            # ...nhưng KHÔNG skip nếu input có vẻ là Start/End của schedule
                            if is_readonly and not any(
                                kw in inp_class.lower()
                                for kw in [
                                    "flatpickr",
                                    "datepicker",
                                    "datetime",
                                    "timepicker",
                                ]
                            ):
                                combined = (
                                    inp_id.lower()
                                    + " "
                                    + inp_name.lower()
                                    + " "
                                    + inp_placeholder.lower()
                                )
                                looks_start_end = any(
                                    x in combined for x in ["start", "end"]
                                )
                                if not looks_start_end:
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
                                self._safe_press_escape(page)
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
            # STRATEGY 0: SECTION-AWARE SEARCH
            # Handle labels like "Active Phase Schedules In UTC" → section="Active Phase", find datetime inputs in that section
            # ========================================
            section_prefixes = [
                "PreEvent Phase",
                "Pre-Event Phase",
                "Pre Event Phase",
                "Active Phase",
                "Post Event Settings",
                "Post Event",
            ]
            section_name = None
            field_name = None
            for prefix in section_prefixes:
                if label_text.lower().startswith(prefix.lower()):
                    section_name = prefix
                    field_name = label_text[len(prefix) :].strip()
                    break

            if section_name:
                print(
                    f"         🔍 [ScheduleSmart] Section-aware: section='{section_name}', field='{field_name}'"
                )
                section_datetime_inputs = self._find_datetime_inputs_in_section(
                    page, section_name
                )
                if section_datetime_inputs:
                    print(
                        f"         📍 [ScheduleSmart] Found {len(section_datetime_inputs)} datetime inputs in section '{section_name}'"
                    )
                    # Use section datetime inputs directly
                    return self._fill_schedule_datetime_values(
                        page, section_datetime_inputs, values
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
                        # Không ép visible: schedule start/end trong modal có thể hidden/readonly
                        # nhưng vẫn set được qua JS trong _fill_single_datetime_input.
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
                    "input.flatpickr-input, input.datetimepicker, input.datepicker"
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
                # ========================================
                # STRATEGY 3: SECTION-AWARE FALLBACK (when no label/flatpickr match)
                # If label starts with a section prefix, find ALL datetime inputs in that section
                # ========================================
                if section_name:
                    print(
                        f"         🔍 [ScheduleSmart] Strategy 3: Section-aware fallback for '{section_name}'..."
                    )
                    section_datetime_inputs = self._find_datetime_inputs_in_section(
                        page, section_name
                    )
                    if section_datetime_inputs:
                        print(
                            f"         📍 [ScheduleSmart] Found {len(section_datetime_inputs)} datetime inputs in section '{section_name}'"
                        )
                        return self._fill_schedule_datetime_values(
                            page, section_datetime_inputs, values
                        )

                print(
                    f"         ❌ [ScheduleSmart] No datetime inputs found for '{label_text}'"
                )
                return False

            print(
                f"         📍 [ScheduleSmart] Found {len(datetime_inputs)} datetime inputs total"
            )

            # 🆕 FIX: Nếu có nhiều values (Start, End) mà chỉ tìm được <2 inputs
            # (thực tế hay xảy ra với "Schedule in UTC" vì End input có thể nằm
            # ngoài container label hiện tại hoặc bị hidden/readonly theo timing),
            # thì fallback sang handler điền multiple datetime fields.
            if len(values) > 1 and len(datetime_inputs) < len(values):
                print(
                    f"         ⚠️ [ScheduleSmart] Not enough datetime inputs "
                    f"({len(datetime_inputs)}) for {len(values)} values; falling back to "
                    f"_fill_multiple_datetime_fields('{label_text}')"
                )
                if self._fill_multiple_datetime_fields(page, label_text, values):
                    return True

            return self._fill_schedule_datetime_values(page, datetime_inputs, values)

        except Exception as e:
            print(f"         ❌ [ScheduleSmart] Error: {e}")
            return False

    def _fill_schedule_datetime_values(self, page, datetime_inputs, values):
        """
        Helper: Điền values vào datetime_inputs.
        Multiple values → fill sequentially; Single value → fill next empty slot.
        """
        if len(values) > 1:
            # Multiple values: fill inputs in order
            for idx, (inp, val) in enumerate(zip(datetime_inputs, values)):
                self._fill_single_datetime_input(page, inp, val, idx)
        else:
            # Single value: find the first EMPTY input and fill it
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
                    print(f"         📅 [ScheduleSmart] Filling first slot: '{val}'")
                    self._fill_single_datetime_input(page, datetime_inputs[0], val, 0)
        return True

    def _find_datetime_inputs_in_section(self, page, section_name):
        """
        Tìm tất cả datetime inputs trong một section cụ thể (VD: "Active Phase", "PreEvent Phase").
        Dùng cho schedule fields khi label có section prefix.
        Trả về list các input elements.
        """
        try:
            section_lower = section_name.lower().strip()

            # Tìm section container bằng header text
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
                    container_text = ""
                    try:
                        container_text = container.inner_text()[:300].lower()
                    except:
                        continue
                    if section_lower not in container_text:
                        continue

                    # Verify section header exists (not just mentioned in content)
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

                    print(
                        f"         📍 [SectionDT] Found section container: '{section_name}'"
                    )

                    # Tìm datetime inputs trong container
                    datetime_inputs = []

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
                                "tournamentid",
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

                    # Priority 3: Tìm thêm các input có label "Start Date" hoặc "End Date" trong container
                    if not datetime_inputs:
                        labels_in_section = container.locator(
                            "label, span, strong"
                        ).all()
                        for lbl in labels_in_section:
                            if not lbl.is_visible():
                                continue
                            lbl_text = lbl.inner_text().strip().lower()
                            if any(
                                kw in lbl_text
                                for kw in ["date time", "date", "start", "end"]
                            ):
                                # Tìm input liên kết
                                for_attr = lbl.get_attribute("for")
                                if for_attr:
                                    target = page.locator(f"#{for_attr}").first
                                    if target.count() > 0 and target.is_visible():
                                        datetime_inputs.append(target)
                                        continue
                                # Sibling input
                                sibling = lbl.locator("xpath=following::input[1]").first
                                if sibling.count() > 0 and sibling.is_visible():
                                    # Verify sibling is within same container
                                    try:
                                        sib_box = sibling.bounding_box()
                                        cont_box = container.bounding_box()
                                        if sib_box and cont_box:
                                            if (
                                                sib_box["y"] >= cont_box["y"]
                                                and sib_box["y"]
                                                <= cont_box["y"] + cont_box["height"]
                                            ):
                                                datetime_inputs.append(sibling)
                                    except:
                                        datetime_inputs.append(sibling)

                    if datetime_inputs:
                        # Deduplicate by bounding box
                        seen = set()
                        unique_inputs = []
                        for inp in datetime_inputs:
                            try:
                                box = inp.bounding_box()
                                key = (
                                    (round(box["x"]), round(box["y"]))
                                    if box
                                    else id(inp)
                                )
                            except:
                                key = id(inp)
                            if key not in seen:
                                seen.add(key)
                                unique_inputs.append(inp)
                        return unique_inputs

            # Fallback: Proximity-based search
            print(
                f"         🔍 [SectionDT] Fallback: Proximity search for '{section_name}'..."
            )
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

                # Find all datetime-like inputs below this header but within 600px
                all_inputs = page.locator(
                    "input.flatpickr-input, input.datetimepicker, input.datepicker, "
                    "input[type='text'], input[type='date'], input[type='datetime-local']"
                ).all()

                section_inputs = []
                for inp in all_inputs:
                    if not inp.is_visible():
                        continue
                    inp_box = inp.bounding_box()
                    if not inp_box:
                        continue
                    # Input phải nằm DƯỚI header (y lớn hơn) và trong khoảng 600px
                    if (
                        inp_box["y"] > header_box["y"]
                        and inp_box["y"] - header_box["y"] < 600
                    ):
                        inp_class = (inp.get_attribute("class") or "").lower()
                        inp_id = (inp.get_attribute("id") or "").lower()
                        inp_name = (inp.get_attribute("name") or "").lower()
                        inp_placeholder = (
                            inp.get_attribute("placeholder") or ""
                        ).lower()

                        # Skip unrelated
                        skip_names = [
                            "id",
                            "name",
                            "title",
                            "description",
                            "eventid",
                            "factionwarid",
                            "tournamentid",
                        ]
                        if any(
                            inp_name == skip or inp_id == skip for skip in skip_names
                        ):
                            continue

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
                        if is_datetime:
                            section_inputs.append(inp)

                if section_inputs:
                    print(
                        f"         📍 [SectionDT] Proximity found {len(section_inputs)} datetime inputs under '{section_name}'"
                    )
                    return section_inputs

            return []
        except Exception as e:
            print(f"         ⚠️ [SectionDT] Error: {e}")
            return []

    def _fix_datetime_12h_format(self, val):
        """Fix datetime values for 12-hour format before filling.
        - '00:00 AM' → '12:00 AM' (midnight)
        - '00:30 PM' → '12:30 PM' (noon)
        - Hour 00 is not valid in %I (12-hour), must be 12.
        """
        # Fix 00:MM AM/PM → 12:MM AM/PM
        fixed = re.sub(
            r"(\s)00:(\d{2})(\s*)(AM|PM)", r"\g<1>12:\2\3\4", val, flags=re.IGNORECASE
        )
        if fixed != val:
            print(f"         🔧 Auto-fixed 12h format: '{val}' → '{fixed}'")
        return fixed

    def _detect_input_datetime_format(self, current_value):
        """
        Phát hiện định dạng datetime từ giá trị hiện tại trong input.
        Trả về chuỗi mô tả format hoặc None nếu không xác định được.
        """
        if not current_value or not current_value.strip():
            return None
        v = current_value.strip()

        # Format: "H:MM - MM/DD/YYYY" (time-dash-date)
        if re.match(r"^\d{1,2}:\d{2}\s*-\s*\d{2}/\d{2}/\d{4}$", v):
            return "TIME_DASH_DATE"
        # Format: "MM/DD/YYYY, HH:MM AM/PM" (comma-separated datetime with AM/PM)
        if re.match(r"^\d{2}/\d{2}/\d{4},\s*\d{1,2}:\d{2}\s*[AP]M$", v, re.IGNORECASE):
            return "DATE_COMMA_TIME_AMPM"
        # Format: "MM/DD/YYYY, HH:MM" (comma-separated datetime)
        if re.match(r"^\d{2}/\d{2}/\d{4},\s*\d{1,2}:\d{2}$", v):
            return "DATE_COMMA_TIME"
        # Format: "MM/DD/YYYY HH:MM AM/PM"
        if re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}\s*[AP]M$", v, re.IGNORECASE):
            return "DATE_TIME_AMPM"
        # Format: "MM/DD/YYYY HH:MM"
        if re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{1,2}:\d{2}$", v):
            return "DATE_TIME"
        # Format: "MM/DD/YYYY" only
        if re.match(r"^\d{2}/\d{2}/\d{4}$", v):
            return "DATE_ONLY"
        # Format: "HH:MM AM/PM" only
        if re.match(r"^\d{1,2}:\d{2}\s*[AP]M$", v, re.IGNORECASE):
            return "TIME_AMPM_ONLY"
        # Format: "HH:MM" only
        if re.match(r"^\d{1,2}:\d{2}$", v):
            return "TIME_ONLY"
        return None

    def _reformat_datetime_to_format(self, new_value, target_format):
        """
        Parse new_value linh hoạt rồi reformat theo target_format phát hiện từ ô input.
        Trả về chuỗi đã format, hoặc new_value gốc nếu parse thất bại.
        """
        from datetime import datetime as _dt

        new_value = new_value.strip()

        # Thử parse "H:MM - MM/DD/YYYY" trước
        m = re.match(r"^(\d{1,2}:\d{2})\s*-\s*(\d{2}/\d{2}/\d{4})$", new_value)
        parsed = None
        if m:
            try:
                parsed = _dt.strptime(f"{m.group(2)} {m.group(1)}", "%m/%d/%Y %H:%M")
            except Exception:
                pass

        if not parsed:
            for fmt in [
                "%m/%d/%Y %I:%M %p",  # 02/27/2026 03:30 AM
                "%m/%d/%Y, %I:%M %p",  # 02/27/2026, 03:30 AM
                "%m/%d/%Y %H:%M",  # 02/27/2026 03:30
                "%m/%d/%Y, %H:%M",  # 02/27/2026, 03:30
                "%m/%d/%Y",  # 02/27/2026
                "%Y-%m-%d %H:%M:%S",  # 2026-02-27 03:30:00
                "%Y-%m-%d %H:%M",  # 2026-02-27 03:30
                "%Y-%m-%d",  # 2026-02-27
                "%I:%M %p",  # 03:30 AM
                "%H:%M",  # 03:30
            ]:
                try:
                    parsed = _dt.strptime(new_value, fmt)
                    break
                except Exception:
                    pass

        if not parsed:
            return new_value  # Không parse được, giữ nguyên

        if target_format == "TIME_DASH_DATE":
            return f"{parsed.strftime('%H:%M')} - {parsed.strftime('%m/%d/%Y')}"
        elif target_format == "DATE_COMMA_TIME_AMPM":
            return f"{parsed.strftime('%m/%d/%Y')}, {parsed.strftime('%I:%M %p')}"
        elif target_format == "DATE_COMMA_TIME":
            return f"{parsed.strftime('%m/%d/%Y')}, {parsed.strftime('%H:%M')}"
        elif target_format == "DATE_TIME_AMPM":
            return parsed.strftime("%m/%d/%Y %I:%M %p")
        elif target_format == "DATE_TIME":
            return f"{parsed.strftime('%m/%d/%Y')} {parsed.strftime('%H:%M')}"
        elif target_format == "DATE_ONLY":
            return parsed.strftime("%m/%d/%Y")
        elif target_format == "TIME_AMPM_ONLY":
            return parsed.strftime("%I:%M %p")
        elif target_format == "TIME_ONLY":
            return parsed.strftime("%H:%M")
        return new_value

    def _fill_single_datetime_input(self, page, inp, val, idx):
        """Helper: điền 1 giá trị datetime vào 1 input"""
        try:
            # [FIX] Sanitize: strip brackets, quotes from value
            val = re.sub(r"[\[\]'\"]", "", str(val)).strip()
            # [FIX] Auto-fix 00:xx AM/PM → 12:xx AM/PM for 12-hour format
            val = self._fix_datetime_12h_format(val)

            # [FIX] Đọc format cũ từ ô input, reformat value theo đúng format đó
            try:
                current_value = inp.input_value().strip()
                if current_value:
                    detected_fmt = self._detect_input_datetime_format(current_value)
                    if detected_fmt:
                        reformatted = self._reformat_datetime_to_format(
                            val, detected_fmt
                        )
                        if reformatted != val:
                            print(
                                f"            🔄 Format detected '{detected_fmt}', reformatting: '{val}' → '{reformatted}'"
                            )
                            val = reformatted
                        else:
                            print(
                                f"            ℹ️ Format detected '{detected_fmt}', value already matches: '{val}'"
                            )
                    else:
                        print(
                            f"            ℹ️ Existing value '{current_value}' format undetected, filling as-is"
                        )
                else:
                    print(f"            ℹ️ Empty input slot, filling as-is: '{val}'")
            except Exception as e:
                print(f"            ⚠️ Could not read current input value: {e}")

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
                _def_modal = (
                    page.locator(".modal.show, .modal.in, .swal2-popup:visible")
                    .filter(has_text=re.compile(r"Defining\s+Schedules", re.IGNORECASE))
                    .last
                )
                _is_def_open = _def_modal.count() > 0 and _def_modal.is_visible()
                if not _is_def_open:
                    self._safe_press_escape(page)
                else:
                    print(
                        "         ⏭️ Defining Schedules modal is open; skipping Escape to keep it for End Time entry."
                    )
            except:
                pass
            time.sleep(0.2)
        except Exception as e:
            print(f"         ⚠️ Error filling datetime input {idx+1}: {e}")

    def _auto_fix_datetime_on_page(self, page, error_msg):
        """
        Parse error message to find the bad datetime value, fix it,
        then find and update the matching input on the page.

        Example error: "time data '02/24/2026 00:00 AM' does not match format '%m/%d/%Y %I:%M %p'"
        Fix: '00:00 AM' → '12:00 AM', '00:00 PM' → '12:00 PM'
        """
        try:
            # Extract the bad datetime value from error message
            match = re.search(r"time data '([^']+)'", error_msg)
            if not match:
                print("      ⚠️ Could not parse bad datetime from error message.")
                return False

            bad_value = match.group(1)
            fixed_value = self._fix_datetime_format(bad_value)

            if fixed_value == bad_value:
                print(f"      ⚠️ No fix found for datetime: '{bad_value}'")
                return False

            print(f"      🔧 Fixing datetime: '{bad_value}' → '{fixed_value}'")

            # Find all datetime/flatpickr inputs on the page and fix matching values
            datetime_inputs = page.locator(
                "input.flatpickr-input, input.datetimepicker, input.datepicker, "
                "input[type='text'][class*='flatpickr'], input[type='text'][class*='date']"
            ).all()

            fixed_count = 0
            for inp in datetime_inputs:
                try:
                    if not inp.is_visible():
                        continue
                    current_val = inp.get_attribute("value") or inp.input_value()
                    if current_val and current_val.strip() == bad_value.strip():
                        # Fix this input
                        inp.evaluate(
                            "(el, v) => {"
                            "  el.removeAttribute('readonly');"
                            "  el.value = v;"
                            "  el.setAttribute('value', v);"
                            "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                            "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                            "  if(el._flatpickr) { el._flatpickr.setDate(v, true); }"
                            "}",
                            fixed_value,
                        )
                        fixed_count += 1
                        print(
                            f"      ✅ Fixed input value: '{bad_value}' → '{fixed_value}'"
                        )
                except:
                    pass

            # Also try fixing via broader input search
            if fixed_count == 0:
                all_inputs = page.locator("input[type='text']").all()
                for inp in all_inputs:
                    try:
                        if not inp.is_visible():
                            continue
                        current_val = inp.get_attribute("value") or ""
                        if current_val.strip() == bad_value.strip():
                            inp.evaluate(
                                "(el, v) => {"
                                "  el.value = v;"
                                "  el.dispatchEvent(new Event('input', {bubbles: true}));"
                                "  el.dispatchEvent(new Event('change', {bubbles: true}));"
                                "  if(el._flatpickr) { el._flatpickr.setDate(v, true); }"
                                "}",
                                fixed_value,
                            )
                            fixed_count += 1
                            print(
                                f"      ✅ Fixed input (broad): '{bad_value}' → '{fixed_value}'"
                            )
                    except:
                        pass

            return fixed_count > 0

        except Exception as e:
            print(f"      ⚠️ Auto-fix datetime error: {e}")
            return False

    def _fix_datetime_format(self, value):
        """
        Fix common datetime format issues:
        - '00:00 AM' → '12:00 AM' (12-hour format requires 01-12, not 00)
        - '00:xx PM' → '12:xx PM'
        - Ensure proper spacing before AM/PM
        """
        fixed = value

        # Fix '00:' at the time part → '12:' (in 12-hour format, midnight/noon = 12, not 00)
        # Pattern: date part + space + 00:MM + space + AM/PM
        fixed = re.sub(
            r"(\d{2}/\d{2}/\d{4})\s+00:(\d{2})\s*(AM|PM)",
            r"\1 12:\2 \3",
            fixed,
            flags=re.IGNORECASE,
        )

        # Also handle ISO-like format: 2026-02-24 00:00 AM
        fixed = re.sub(
            r"(\d{4}-\d{2}-\d{2})\s+00:(\d{2})\s*(AM|PM)",
            r"\1 12:\2 \3",
            fixed,
            flags=re.IGNORECASE,
        )

        return fixed

    # --- HÀM NÂNG CẤP: QUÉT TAB DỰA TRÊN TEXT ---
