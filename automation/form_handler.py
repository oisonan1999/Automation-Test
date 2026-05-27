# automation/form_handler.py - Form logic: smart filling, dropdown, radio, datetime, save
# Table/checkbox operations tách ra table_handler.py
import time
import re
import random
from playwright.sync_api import Page


class FormHandlerMixin:
    """Chứa logic tương tác với Form: điền form, dropdown, radio, datetime, save"""

    def _safe_press_escape(self, page):
        """
        Press Escape để đóng picker/modal nhỏ.
        Nhưng KHÔNG bấm Escape nếu modal "Defining Schedules" đang mở,
        vì nút "Close" trong modal đó chính là Save/confirm sau khi điền End time.
        """
        try:
            modal = (
                page.locator(".modal.show, .modal.in, .swal2-popup:visible")
                .filter(has_text=re.compile(r"Defining\s+Schedules", re.IGNORECASE))
                .last
            )
            if modal.count() > 0 and modal.is_visible():
                print("         ⏭️ Defining Schedules modal is open; skipping Escape.")
                return False
        except Exception:
            pass

        try:
            page.keyboard.press("Escape")
            return True
        except Exception:
            return False

    # ============================
    # SMART FORM FILLER (FULL FEATURES)
    # ============================
    def _smart_update_form(self, page, data):
        """
        Hàm chính: Duyệt qua data và điền từng trường.
        """
        print(f"      📝 Updating Form Data: {data}")

        # Chờ form ổn định + chờ loader vld-icon/skeleton/aria-busy tắt hẳn
        # (Match 1 panel dùng vld-icon spinner; nếu điền quá sớm select2/fields chưa mount)
        try:
            page.wait_for_load_state("domcontentloaded")
        except:
            pass

        time.sleep(0.8)

        try:
            timeout_s = 30
            start_t = time.time()
            while time.time() - start_t < timeout_s:
                try:
                    vld_visible = page.locator(".vld-icon:visible").count() > 0
                except:
                    vld_visible = False
                try:
                    skeleton_visible = page.locator(".b-skeleton:visible").count() > 0
                except:
                    skeleton_visible = False
                try:
                    aria_busy_visible = (
                        page.locator("[aria-busy='true']:visible").count() > 0
                    )
                except:
                    aria_busy_visible = False

                # Break when ALL loaders are gone
                if not vld_visible and not skeleton_visible and not aria_busy_visible:
                    break
                time.sleep(0.5)
        except:
            pass

        # Give a tiny settle time for select2 mount
        time.sleep(0.6)

        # ============================
        # SPECIAL: Clamp "Defining Schedules" Start/End Time to RBE restriction
        # ============================
        # If the "Defining Schedules" modal is open, the UI may reject CSS schedule
        # outside the parent RBE schedule range.
        defining_modal = None
        defining_modal_visible = False
        try:
            defining_modal = (
                page.locator(".modal.show, .modal.in, .swal2-popup:visible")
                .filter(has_text=re.compile(r"Defining\s+Schedules", re.IGNORECASE))
                .last
            )
            defining_modal_visible = (
                defining_modal.count() > 0 and defining_modal.is_visible()
            )
        except:
            defining_modal_visible = False

        if defining_modal_visible and isinstance(data, dict):
            try:
                # Find Start/End keys in update_form data
                start_key = None
                end_key = None
                for k in data.keys():
                    kl = str(k).lower().strip()
                    if start_key is None and "start time" in kl:
                        start_key = k
                    if end_key is None and "end time" in kl:
                        end_key = k

                if start_key is not None and end_key is not None:
                    modal_text = defining_modal.inner_text().strip()

                    # Example:
                    # "CSS schedule is restricted to be within RBE schedule: 2026-04-24 19:00 - 2026-04-27 19:00"
                    m = re.search(
                        r"restricted to be within RBE schedule:\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{1,2}:[0-9]{2})\s*-\s*([0-9]{4}-[0-9]{2}-[0-9]{2}\s+[0-9]{1,2}:[0-9]{2})",
                        modal_text,
                        re.IGNORECASE,
                    )
                    if m:
                        from datetime import datetime as _dt

                        def _parse_ymd_hm(v):
                            sv = re.sub(r"[\[\]'\"]", "", str(v)).strip()
                            return _dt.strptime(sv, "%Y-%m-%d %H:%M")

                        allowed_start = _parse_ymd_hm(m.group(1))
                        allowed_end = _parse_ymd_hm(m.group(2))

                        provided_start = _parse_ymd_hm(data[start_key])
                        provided_end = _parse_ymd_hm(data[end_key])

                        # Clamp
                        clamped_start = provided_start
                        clamped_end = provided_end

                        if clamped_start < allowed_start:
                            clamped_start = allowed_start
                        if clamped_start > allowed_end:
                            clamped_start = allowed_end

                        if clamped_end < allowed_start:
                            clamped_end = allowed_start
                        if clamped_end > allowed_end:
                            clamped_end = allowed_end

                        if clamped_start > clamped_end:
                            clamped_end = clamped_start

                        new_start = clamped_start.strftime("%Y-%m-%d %H:%M")
                        new_end = clamped_end.strftime("%Y-%m-%d %H:%M")

                        if new_start != str(data[start_key]) or new_end != str(
                            data[end_key]
                        ):
                            print(
                                f"         🔧 [DefiningSchedules] Clamping {start_key}/{end_key} to allowed range: {new_start} - {new_end}"
                            )
                        data[start_key] = new_start
                        data[end_key] = new_end
            except Exception as _clamp_e:
                print(f"         ⚠️ [DefiningSchedules] Clamp skipped: {_clamp_e}")

        for label, value in data.items():
            print(f"         ↳ Processing '{label}' -> '{value}'")
            try:
                label_lower = str(label).lower().strip()
                value_lower = str(value).lower().strip()

                # ============================
                # PVE MATCH FIXES (missing wiring)
                # ============================
                # 1) SSGroup ID: handle multiselect or select2 depending on UI
                if "ssgroup" in label_lower or "ssdb" in label_lower:
                    try:
                        # Upstream sometimes passes: "SS_Osbourne_Ozzy, 5 Star, Gold"
                        # For SSGroup we only want the first SS token.
                        ss_value_raw = str(value)
                        ss_value = ss_value_raw.strip()

                        m = re.search(r"(SS_[A-Za-z0-9_]+)", ss_value_raw)
                        if m:
                            ss_value = m.group(1)

                        # Fallback: if comma-separated, take first token
                        if "," in ss_value and "SS_" in ss_value:
                            ss_value = ss_value.split(",")[0].strip()
                        elif "," in ss_value and "SS_" not in ss_value:
                            ss_value = ss_value.split(",")[0].strip()

                        # UI bạn cung cấp cho Match 1 hiện là multiselect (not select2):
                        #   input id="searchSSGroupId" placeholder="Type to search" aria-controls="listbox-searchSSGroupId"
                        if self._try_set_ssgroup_id_by_multiselect_search_input(
                            page, ss_value
                        ):
                            print(
                                f"         ✅ SSGroup ID set via multiselect search: '{ss_value}'"
                            )
                            # PVE: dropdown data after SSGroup selection is heavy; wait here (not in save_form)
                            if page.locator("#searchSSGroupId").count() > 0:
                                time.sleep(30)
                            else:
                                time.sleep(2)
                            continue

                        # Fallback: legacy select2 SSDB handler
                        if self._try_set_ssgroup_id_by_ssdb_search_placeholder(
                            page, ss_value
                        ):
                            print(
                                f"         ✅ SSGroup ID set via SSDB search: '{ss_value}'"
                            )
                            # PVE: dropdown data after SSGroup selection is heavy; wait here (not in save_form)
                            if page.locator("#searchSSGroupId").count() > 0:
                                time.sleep(30)
                            else:
                                time.sleep(2)
                            continue
                    except Exception as _ss_err:
                        print(f"         ⚠️ SSGroup ID set error: {_ss_err}")

                # 2) Option-as-value dropdown keys:
                #    AI hay truyền {'5 Star':'select', 'Gold':'select'}
                #    => cần chọn dropdown option = key (label), khi value == 'select'
                if value_lower == "select":
                    star_tier_match = bool(
                        re.match(r"^\d+\s*star$", label_lower)
                        or label_lower in ("bronze", "silver", "gold")
                    )
                    if star_tier_match:
                        # Try native <select> first
                        try:
                            if self._try_select_option_by_select_option_text(
                                page, label
                            ):
                                print(
                                    f"         ✅ Dropdown option set (native select) -> '{label}'"
                                )
                                time.sleep(1.2)
                                continue
                        except:
                            pass

                        # Fallback: try select2 dropdowns by option text
                        try:
                            if self._try_set_select2_option_by_option_text(page, label):
                                print(
                                    f"         ✅ Dropdown option set (select2) -> '{label}'"
                                )
                                time.sleep(1.2)
                                continue
                        except:
                            pass

                # Boolean / toggle on main form (not sidebar nav links like #daily_reward)
                if value_lower in (
                    "true",
                    "false",
                    "1",
                    "0",
                    "on",
                    "off",
                    "yes",
                    "no",
                    "enable",
                    "disable",
                ):
                    if self._try_set_form_toggle_by_label(page, label, value):
                        print(f"         ✅ Toggle '{label}' set to '{value}'")
                        time.sleep(1)
                        continue

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
                # SPECIAL CASE 1b: RADIO BUTTON BY VALUE
                # Khi label chứa "radio" suffix và value KHÔNG phải signal
                # VD: "Energy restart mode radio": "Daily" -> Tìm radio group gần label "Energy restart mode", click option "Daily"
                # ========================================
                label_stripped_radio = label.strip()
                if re.search(r"\s+radio\s*$", label_stripped_radio, re.IGNORECASE):
                    clean_label = re.sub(
                        r"\s+radio\s*$", "", label_stripped_radio, flags=re.IGNORECASE
                    ).strip()
                    print(
                        f"         🔘 Detected radio-by-value: label='{clean_label}', value='{value}'"
                    )
                    if self._try_select_radio_by_value(page, clean_label, str(value)):
                        print(
                            f"         ✅ Radio option '{value}' selected for '{clean_label}'"
                        )
                        time.sleep(3)
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
                    keyword in label.lower()
                    for keyword in ["schedule", "start time", "end time"]
                )
                is_datetime_value = bool(
                    re.match(r"\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}", value_str.strip())
                )

                if is_schedule_field and ("," in value_str or is_datetime_value):
                    # Tách các giá trị datetime (hoặc wrap single value)
                    if datetime_values is None:
                        if "," in value_str:
                            # [FIX] Smart split: detect "MM/DD/YYYY, HH:MM" pattern where comma
                            # is INSIDE each datetime value (not as separator between values).
                            # E.g. "02/27/2026, 03:30 - 02/27/2026, 04:00" → 2 values
                            date_comma_time_tokens = re.findall(
                                r"\d{2}/\d{2}/\d{4},\s*\d{1,2}:\d{2}(?:\s*[AP]M)?",
                                value_str,
                                re.IGNORECASE,
                            )
                            if len(date_comma_time_tokens) >= 2:
                                # Multiple "MM/DD/YYYY, HH:MM" tokens found → use them directly
                                datetime_values = [
                                    v.strip() for v in date_comma_time_tokens
                                ]
                            elif len(date_comma_time_tokens) == 1:
                                # One DATE,TIME token: check if separated by " - " from more values
                                parts = re.split(r"\s+-\s+", value_str)
                                if len(parts) >= 2:
                                    # Re-extract DATE,TIME token from each part for accuracy
                                    extracted = []
                                    for part in parts:
                                        sub_tokens = re.findall(
                                            r"\d{2}/\d{2}/\d{4},\s*\d{1,2}:\d{2}(?:\s*[AP]M)?",
                                            part.strip(),
                                            re.IGNORECASE,
                                        )
                                        if sub_tokens:
                                            extracted.append(sub_tokens[0].strip())
                                        else:
                                            extracted.append(part.strip())
                                    datetime_values = [v for v in extracted if v]
                                else:
                                    # Truly a single DATE,TIME value
                                    datetime_values = [
                                        date_comma_time_tokens[0].strip()
                                    ]
                            else:
                                # Standard split by comma (no DATE,TIME pattern)
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

                # ========================================
                # SPECIAL CASE 3: "Enter Superstars or Groups" (Select2 multiselect)
                # Bắt buộc phải handle theo placeholder vì label/input thường không có
                # <label> visible để _find_input_element() map đúng.
                # ========================================
                if (
                    "superstars or groups" in label_lower
                    or label_lower.strip() == "superstars or groups"
                ):
                    try:
                        if self._try_set_select2_multiselect_by_placeholder(
                            page,
                            placeholder="Enter Superstars or Groups",
                            value=str(value),
                        ):
                            print(
                                f"         ✅ Set 'Superstars or Groups' via select2 multiselect"
                            )
                            time.sleep(2)
                            continue
                    except Exception as _sel2_e:
                        print(f"         ⚠️ Select2 multiselect set failed: {_sel2_e}")

                # ========================================
                # SPECIAL CASE 4: EARLY INLINE EDIT DETECTION
                # Trước khi tìm element thông thường, kiểm tra xem field có phải dạng
                # inline-edit (có nút Edit) không. VD: Lock Time Offset, Buffer Time,
                # Post Event Duration, Player-Base Gathering Time
                # Các field này có input readonly + nút Edit, nếu để _find_input_element
                # chạy trước sẽ dễ bị chọn nhầm element trong container lớn.
                # ========================================
                _inline_handled = False
                try:
                    _inline_labels = (
                        page.locator("label, span, strong, b")
                        .filter(has_text=re.compile(re.escape(label), re.IGNORECASE))
                        .all()
                    )
                    for _ilbl in _inline_labels:
                        if not _ilbl.is_visible():
                            continue
                        _ilbl_text = _ilbl.inner_text().strip()
                        # Chỉ check exact match (tránh false positive)
                        if _ilbl_text.lower() != label.lower():
                            continue
                        # Tìm Edit button trong parent gần nhất (2-3 levels up)
                        for _anc_xpath in [
                            "xpath=../..",
                            "xpath=../../..",
                            "xpath=../../../..",
                        ]:
                            try:
                                _anc = _ilbl.locator(_anc_xpath).first
                                if _anc.count() > 0 and _anc.is_visible():
                                    _anc_text_len = len(_anc.inner_text().strip())
                                    if _anc_text_len > 500:
                                        continue  # Container quá lớn, skip
                                    _edit = _anc.locator(
                                        "button:has-text('Edit'), a:has-text('Edit')"
                                    ).first
                                    if _edit.count() > 0 and _edit.is_visible():
                                        print(
                                            f"         ✏️ [Early Detection] Found Edit button near '{label}', trying inline edit..."
                                        )
                                        if self._handle_inline_edit_field(
                                            page, label, value
                                        ):
                                            print(
                                                f"         ✅ Inline edit completed for '{label}'"
                                            )
                                            _inline_handled = True
                                            time.sleep(3)
                                        break
                            except:
                                pass
                        if _inline_handled:
                            break
                except Exception as _ie:
                    pass  # Fallback to normal flow
                if _inline_handled:
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

    def _try_set_ssgroup_id_by_multiselect_search_input(self, page, ssgroup_id):
        """
        Match panel (your provided HTML) uses a multiselect-like component:
          <input id="searchSSGroupId" placeholder="Type to search" aria-controls="listbox-searchSSGroupId">
          <span class="multiselect__single">SS_CPunk_BITW</span>
        So we:
          1) click/fill search input
          2) wait for listbox results by aria-controls
          3) click the option matching ssgroup_id
          4) verify multiselect__single updated
        """
        try:
            if ssgroup_id is None:
                return False

            value_str = str(ssgroup_id).strip()
            if not value_str:
                return False

            # IMPORTANT: scope to the currently expanded Match 1 panel to avoid
            # selecting the multiselect input from some other (already loaded) panel.
            scoped_root = page
            try:
                panel_id = None
                # Find the chevron/toggle button for Match 1 and extract aria-controls.
                # (Don't require aria-expanded=true here; at fill time it can be flaky.)
                match1_el = page.locator("text=Match 1").first
                # More robust: search toggle button anywhere under the Match 1 ancestor
                toggle_btn = match1_el.locator(
                    "xpath=ancestor::*//button[contains(@aria-controls,'chapter-match-')][1]"
                ).first
                if toggle_btn.count() > 0:
                    panel_id = toggle_btn.get_attribute("aria-controls")
                if panel_id:
                    scoped_root = page.locator(f"#{panel_id}")
            except:
                scoped_root = page

            # Collect candidate search inputs within the intended Match 1 panel.
            # If multiple exist, try each one until selection verifies.
            candidate_inputs = scoped_root.locator("input#searchSSGroupId").all()
            if not candidate_inputs:
                candidate_inputs = scoped_root.locator(
                    "input[aria-controls^='listbox-searchSSGroupId'], input[id^='searchSSGroup']"
                ).all()

            if not candidate_inputs:
                return False

            for search_input in candidate_inputs[:3]:
                # Read aria-controls listbox id for THIS input
                listbox_id = None
                try:
                    aria_controls = search_input.get_attribute("aria-controls") or ""
                    # aria-controls can be space-separated
                    listbox_id = aria_controls.split()[0] if aria_controls else None
                except:
                    listbox_id = None

                # Click/open dropdown
                try:
                    search_input.click(force=True)
                except:
                    pass

                # IMPORTANT: the SSGroup input may be width:0 and positioned absolute.
                # Always set via JS + dispatch events (don’t rely on Playwright fill()).
                try:
                    search_input.evaluate(
                        "(el,v)=>{"
                        "  try{el.focus();}catch(e){}"
                        "  el.value='';"
                        "  el.dispatchEvent(new Event('input',{bubbles:true}));"
                        "  el.dispatchEvent(new Event('change',{bubbles:true}));"
                        "  el.value=v;"
                        "  el.dispatchEvent(new Event('input',{bubbles:true}));"
                        "  el.dispatchEvent(new Event('change',{bubbles:true}));"
                        "}",
                        value_str,
                    )
                except:
                    # Fallback: try fill if JS fails
                    try:
                        search_input.fill("")
                        search_input.fill(value_str)
                    except:
                        continue

                time.sleep(0.25)

                # Wait for listbox results (in this UI, options are often NOT guaranteed to have role="option")
                if listbox_id:
                    # The listbox popup might render outside the Match 1 panel container.
                    # Using page-scoped lookup prevents missing the listbox due to strict scoping.
                    listbox = page.locator(f"#{listbox_id}")
                else:
                    listbox = scoped_root.locator("ul, div, [role='listbox']").first

                try:
                    listbox.wait_for(state="attached", timeout=8000)
                except:
                    try:
                        listbox.wait_for(state="visible", timeout=8000)
                    except:
                        pass

                if listbox_id:
                    # Try exact text match anywhere inside the listbox
                    match_opt = (
                        page.locator(f"#{listbox_id}")
                        .filter(
                            has_text=re.compile(
                                r"^\s*" + re.escape(value_str) + r"\s*$"
                            )
                        )
                        .first
                    )

                    # If exact text node isn't clickable, try broader clickable containers inside the listbox
                    if match_opt.count() == 0:
                        match_opt = (
                            page.locator(f"#{listbox_id} li, #{listbox_id} div")
                            .filter(
                                has_text=re.compile(
                                    r"^\s*" + re.escape(value_str) + r"\s*$",
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )

                    # Fallback: contains match
                    if match_opt.count() == 0:
                        match_opt = (
                            page.locator(f"#{listbox_id} li, #{listbox_id} div")
                            .filter(
                                has_text=re.compile(
                                    re.escape(value_str),
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )

                    # Final fallback: any element inside listbox containing the token
                    if match_opt.count() == 0:
                        match_opt = (
                            page.locator(f"#{listbox_id}")
                            .filter(
                                has_text=re.compile(
                                    re.escape(value_str),
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )
                else:
                    match_opt = (
                        scoped_root.locator("li, div, [role='option']")
                        .filter(
                            has_text=re.compile(
                                r"^" + re.escape(value_str) + r"\s*$",
                                re.IGNORECASE,
                            )
                        )
                        .first
                    )

                if match_opt.count() == 0:
                    continue

                match_opt.click(force=True)

                # Verify selection tag updated (inside intended panel)
                # Try to scope selection tag to the same Match panel as this input.
                panel_root = scoped_root
                try:
                    maybe_panel = search_input.locator(
                        "xpath=ancestor::*[contains(@id,'chapter-match-')][1]"
                    ).first
                    if maybe_panel.count() > 0:
                        panel_root = maybe_panel
                except:
                    pass

                # UI may be slow (dropdown list heavy), so wait a bit and re-check.
                for _ in range(20):
                    try:
                        selected = (
                            panel_root.locator("span.multiselect__single")
                            .filter(
                                has_text=re.compile(
                                    re.escape(value_str),
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )
                        if selected.count() > 0:
                            return True
                    except Exception:
                        pass
                    time.sleep(0.5)

                # One last attempt: Enter to confirm selection
                try:
                    page.keyboard.press("Enter")
                except:
                    pass

                time.sleep(0.5)
                try:
                    selected = (
                        scoped_root.locator("span.multiselect__single")
                        .filter(
                            has_text=re.compile(
                                re.escape(value_str),
                                re.IGNORECASE,
                            )
                        )
                        .first
                    )
                    if selected.count() > 0:
                        return True
                except Exception:
                    pass
            # If all candidate inputs failed
            return False
        except Exception:
            return False

    def _try_set_ssgroup_id_by_ssdb_search_placeholder(self, page, ssgroup_id):
        """
        Trong UI PVE Match, field SSGroup ID thường là select2 search có placeholder:
          - "Type to search SSDB" (hoặc tương tự)
        AI đưa data key='SSGroup ID' với value='SS_...'
        => Mở dropdown đúng control theo placeholder rồi chọn option theo value.
        """
        try:
            if ssgroup_id is None:
                return False

            value_str = str(ssgroup_id).strip()
            if not value_str:
                return False

            # Find select2 search input by placeholder tokens
            # (SSDB may vary: "SSDB", "SSD B", etc. -> match broadly)
            search_re = re.compile(r"type\s*to\s*search.*ssdb", re.IGNORECASE)

            # PVE Match panel loads async (you showed vld-icon + skeleton).
            # Wait a bit so the SSDB select2 input exists before we scan containers.
            try:
                page.locator("text=SSGroup ID").first.wait_for(
                    state="visible", timeout=8000
                )
            except:
                pass

            try:
                page.locator("input.select2-search__field").first.wait_for(
                    state="attached", timeout=8000
                )
            except:
                pass

            search_inputs = page.locator("input.select2-search__field").all()
            target_container = None

            def _get_ssdb_token_for_input(input_el):
                try:
                    ph = (input_el.get_attribute("placeholder") or "").strip()
                    aria = (input_el.get_attribute("aria-label") or "").strip()
                    data_ph = (input_el.get_attribute("data-placeholder") or "").strip()
                    role = (input_el.get_attribute("role") or "").strip()
                    combined = " ".join([ph, aria, data_ph, role]).strip()
                    return combined
                except:
                    return ""

            for inp in search_inputs:
                try:
                    token = _get_ssdb_token_for_input(inp)
                    if not token:
                        continue
                    if search_re.search(token):
                        # Prefer select2-container wrapper (click target)
                        container = inp.locator(
                            "xpath=ancestor::span[contains(@class,'select2-container')][1]"
                        ).first
                        if container.count() == 0:
                            container = inp.locator(
                                "xpath=ancestor::span[contains(@class,'select2-selection')][1]"
                            ).first
                        # As a last resort, allow direct parent click target
                        if container.count() == 0:
                            container = inp.locator("xpath=parent::*[1]").first

                        if container.count() > 0:
                            target_container = container
                            try:
                                if container.is_visible():
                                    break
                            except:
                                # Still accept for force-click later
                                break
                except:
                    continue

            # If we found container but it may be hidden, still allow later force-click.

            # Fallback: placeholder contains "Type to search" and we guess it's the SSDB one by nearby SS label text
            if target_container is None:
                generic_inputs = page.locator("input.select2-search__field").all()
                for inp in generic_inputs:
                    try:
                        placeholder = (inp.get_attribute("placeholder") or "").strip()
                        if not placeholder:
                            continue
                        if re.search(r"type\s*to\s*search", placeholder, re.IGNORECASE):
                            container = inp.locator(
                                "xpath=ancestor::span[contains(@class,'select2-container') or contains(@class,'select2-selection')][1]"
                            ).first
                            if container.count() > 0:
                                # Heuristic: prefer ones near left-side match panel controls
                                box = container.bounding_box()
                                if box and box["x"] < 800:
                                    target_container = container
                                    break
                            else:
                                target_container = container
                                break
                    except:
                        continue

            if target_container is None:
                # Fallback robust: mở từng select2 container để đợi input placeholder render
                try:
                    ssdb_token_re = re.compile(r"ssdb", re.IGNORECASE)

                    select2_containers = page.locator(
                        "span.select2-container, span.select2-selection"
                    ).all()

                    for cont in select2_containers:
                        try:
                            if not cont.is_visible():
                                continue
                        except:
                            continue

                        try:
                            cont.click(force=True)
                        except:
                            continue

                        time.sleep(0.25)

                        try:
                            # After opening, search field may exist with placeholder
                            search_inputs_now = page.locator(
                                "input.select2-search__field"
                            ).all()
                            ssdb_found = False
                            for inp in search_inputs_now:
                                try:
                                    ph = (
                                        inp.get_attribute("placeholder") or ""
                                    ).strip()
                                except:
                                    ph = ""
                                if ph and ssdb_token_re.search(ph):
                                    ssdb_found = True
                                    break

                            if ssdb_found:
                                target_container = cont
                                print(
                                    "         ✅ SSGroup ID: Found select2 container by opening/placeholder (SSDB)"
                                )
                                break
                        except:
                            pass

                        # Close dropdown and try next
                        try:
                            page.keyboard.press("Escape")
                        except:
                            pass

                    if target_container is None:
                        return False
                except:
                    return False

            # Primary path: use container determined by placeholder heuristics
            if self._handle_js_dropdown(page, target_container, value_str, "select2"):
                return True

            # Fallback: brute-force visible select2 containers and try to select by option text.
            # This handles cases where SSDB placeholder varies (or doesn't include SSDB token).
            try:
                select2_conts = page.locator(
                    "span.select2-container:visible, span.select2-selection:visible"
                ).all()
                for cont in select2_conts[:10]:
                    try:
                        if not cont.is_visible():
                            continue
                    except:
                        continue

                    try:
                        cont.click(force=True)
                    except:
                        continue

                    time.sleep(0.25)

                    # Find visible search input belonging to THIS opened select2 and type query
                    try:
                        ss_inp = cont.locator(
                            "input.select2-search__field:visible"
                        ).first
                        if ss_inp.count() == 0:
                            # fallback: global visible input (older layouts)
                            ss_inp = page.locator(
                                "input.select2-search__field:visible"
                            ).first
                        ss_inp.wait_for(state="visible", timeout=3000)
                    except:
                        # Close and continue
                        try:
                            page.keyboard.press("Escape")
                        except:
                            pass
                        continue

                    try:
                        ss_inp.fill("")
                        ss_inp.fill(value_str)
                    except:
                        # last resort: JS set value
                        try:
                            ss_inp.evaluate(
                                "(el,v)=>{el.value=v;el.dispatchEvent(new Event('input',{bubbles:true}));}",
                                value_str,
                            )
                        except:
                            pass

                    time.sleep(0.5)

                    # Wait for options and click match
                    matched = False
                    try:
                        opts = page.locator(".select2-results__option:visible")
                        # wait for options to render
                        try:
                            opts.first.wait_for(state="visible", timeout=3000)
                        except:
                            pass

                        # prefer exact/equal text match
                        match_opt = opts.filter(
                            has_text=re.compile(r"^" + re.escape(value_str) + r"\s*$")
                        ).first
                        if match_opt.count() > 0 and match_opt.is_visible():
                            match_opt.click(force=True)
                            matched = True
                        else:
                            # contains fallback
                            match_opt2 = opts.filter(
                                has_text=re.compile(re.escape(value_str), re.IGNORECASE)
                            ).first
                            if match_opt2.count() > 0 and match_opt2.is_visible():
                                match_opt2.click(force=True)
                                matched = True
                    except:
                        matched = False

                    # Close dropdown
                    try:
                        page.keyboard.press("Escape")
                    except:
                        pass

                    if matched:
                        print(
                            "         ✅ SSGroup ID set via brute-force select2 option match"
                        )
                        return True
            except:
                pass

            return False
        except Exception as e:
            print(
                f"         ⚠️ _try_set_ssgroup_id_by_ssdb_search_placeholder error: {e}"
            )
            return False

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

            # Detect PVE Match 1 context (multiselect input exists only there)
            is_pve_match_page = page.locator("#searchSSGroupId").count() > 0

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
                # Mode "save":
                # - On PVE we MUST prefer the green Match Save button (text "Save"),
                #   not the generic "Save Book Info" button elsewhere.
                if is_pve_match_page:
                    priority_buttons = [
                        "Save",  # prefer Match Save (green button)
                        "Save Book Info",
                        "Save Book",
                        "Save Book Information",
                        "Update",
                        "Submit",
                        "Confirm",
                        "OK",
                    ]
                else:
                    # Default non-PVE: keep original safety (prefer Save Book Info)
                    priority_buttons = [
                        "Save Book Info",
                        "Save Book",
                        "Save Book Information",
                        "Save",  # fallback generic (exact match)
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
                    # EXACT MATCH generic "Save" nhưng KHÔNG match "Save & Continue"
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
                                        f"      🎯 Found exact 'Save' button (mode=save fallback)"
                                    )
                                    break
                            except:
                                pass
                    if target_btn:
                        break
                else:
                    # Prefer exact/contains match for the contextual button text
                    btn = (
                        scope.locator("button, a.btn, input[type='submit']")
                        .filter(
                            has_text=re.compile(
                                rf"\\b{re.escape(btn_text)}\\b|^{re.escape(btn_text)}$|{re.escape(btn_text)}",
                                re.IGNORECASE,
                            )
                        )
                        .last
                    )
                    if btn.count() > 0 and btn.is_visible():
                        try:
                            found_txt = btn.inner_text().strip()
                        except:
                            found_txt = btn_text
                        print(
                            f"      🎯 Found button for mode=save: '{found_txt}' (wanted '{btn_text}')"
                        )
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
            # THỰC HIỆN CLICK (với Network Response Interception)
            # =========================================================
            if target_btn and target_btn.is_visible():
                # PVE: choose the correct green "Save" button (bottom save bar),
                # not the nearby "Save" next to the SSDB/multiselect dropdown.
                # Also: per your request, no extra ~30s wait here (wait only during SSGroup ID fill).
                if is_pve_match_page:
                    try:
                        save_candidates = (
                            scope.locator("button, a.btn, input[type='submit']")
                            .filter(has_text=re.compile(r"^\s*Save\s*$", re.IGNORECASE))
                            .all()
                        )

                        best = None
                        best_score = (-1, -1)  # (green_flag, y)
                        for cand in save_candidates:
                            try:
                                if not cand.is_visible():
                                    continue
                                box = cand.bounding_box()
                                y = box["y"] if box and "y" in box else -1
                                cls = ""
                                try:
                                    cls = (cand.get_attribute("class") or "").lower()
                                except:
                                    cls = ""

                                # Prefer green buttons (btn-success). If class isn't present,
                                # still fall back to bottom-most (max y).
                                green_flag = (
                                    1
                                    if "btn-success" in cls or "btn-green" in cls
                                    else 0
                                )
                                score = (green_flag, y)
                                if score > best_score:
                                    best_score = score
                                    best = cand
                            except:
                                continue

                        if best is not None:
                            target_btn = best
                            print(
                                f"      🎯 PVE Save button chosen at bottom (score={best_score})"
                            )
                    except Exception as _pve_save_pick_err:
                        print(
                            f"      ⚠️ PVE Save button picking failed: {_pve_save_pick_err}"
                        )

                target_btn.scroll_into_view_if_needed()
                time.sleep(0.5)

                # --- JAVASCRIPT-LEVEL NETWORK INTERCEPTION ---
                # Playwright response events don't work over CDP (connect_over_cdp).
                # Instead, inject JS to monkey-patch XMLHttpRequest & fetch
                # to capture POST/PUT/PATCH responses directly in the browser.
                try:
                    page.evaluate("""() => {
                        window.__save_network_errors = [];
                        window.__save_network_all = [];

                        // --- Intercept XMLHttpRequest (jQuery $.ajax uses this) ---
                        const origXHROpen = XMLHttpRequest.prototype.open;
                        const origXHRSend = XMLHttpRequest.prototype.send;

                        XMLHttpRequest.prototype.open = function(method, url) {
                            this.__method = method;
                            this.__url = url;
                            return origXHROpen.apply(this, arguments);
                        };

                        XMLHttpRequest.prototype.send = function() {
                            const xhr = this;
                            const origOnReady = xhr.onreadystatechange;
                            xhr.onreadystatechange = function() {
                                if (xhr.readyState === 4) {
                                    const method = (xhr.__method || '').toUpperCase();
                                    if (['POST', 'PUT', 'PATCH'].includes(method)) {
                                        const info = {
                                            method: method,
                                            url: xhr.__url,
                                            status: xhr.status,
                                            statusText: xhr.statusText,
                                            body: null
                                        };
                                        if (xhr.status >= 400) {
                                            try { info.body = xhr.responseText.substring(0, 2000); } catch(e) {}
                                        }
                                        window.__save_network_all.push(info);
                                        if (xhr.status >= 400) {
                                            window.__save_network_errors.push(info);
                                        }
                                    }
                                }
                                if (origOnReady) origOnReady.apply(this, arguments);
                            };
                            // Also handle addEventListener('load') pattern
                            xhr.addEventListener('load', function() {
                                const method = (xhr.__method || '').toUpperCase();
                                if (['POST', 'PUT', 'PATCH'].includes(method) && xhr.status >= 400) {
                                    const existing = window.__save_network_errors.find(e => e.url === xhr.__url && e.status === xhr.status);
                                    if (!existing) {
                                        window.__save_network_errors.push({
                                            method: method,
                                            url: xhr.__url,
                                            status: xhr.status,
                                            statusText: xhr.statusText,
                                            body: xhr.responseText ? xhr.responseText.substring(0, 2000) : null
                                        });
                                    }
                                }
                            });
                            return origXHRSend.apply(this, arguments);
                        };

                        // --- Intercept fetch() API ---
                        const origFetch = window.fetch;
                        window.fetch = function(input, init) {
                            const method = ((init && init.method) || 'GET').toUpperCase();
                            const url = (typeof input === 'string') ? input : input.url;
                            return origFetch.apply(this, arguments).then(response => {
                                if (['POST', 'PUT', 'PATCH'].includes(method)) {
                                    const info = {
                                        method: method,
                                        url: url,
                                        status: response.status,
                                        statusText: response.statusText,
                                        body: null
                                    };
                                    window.__save_network_all.push(info);
                                    if (response.status >= 400) {
                                        response.clone().text().then(t => {
                                            info.body = t.substring(0, 2000);
                                        }).catch(() => {});
                                        window.__save_network_errors.push(info);
                                    }
                                }
                                return response;
                            });
                        };
                    }""")
                    print("      🔌 Network interceptor injected (JS-level)")
                except Exception as inject_err:
                    print(
                        f"      ⚠️ Failed to inject network interceptor: {inject_err}"
                    )

                target_btn.click(force=True)
                print("      ✅ Clicked successfully.")

                # Chờ network settle (AJAX call + response)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass
                time.sleep(2)

                # --- READ CAPTURED NETWORK ERRORS ---
                network_error = None
                try:
                    all_responses = page.evaluate(
                        "() => window.__save_network_all || []"
                    )
                    errors = page.evaluate("() => window.__save_network_errors || []")
                    print(
                        f"      📊 Captured responses: {len(all_responses)} total, {len(errors)} errors"
                    )

                    for resp in all_responses:
                        print(
                            f"      📡 {resp.get('method')} {resp.get('status')} {str(resp.get('url',''))[:100]}"
                        )

                    if errors:
                        err = errors[0]
                        error_detail = f"HTTP {err.get('status')} {err.get('statusText','')} - {err.get('method','')} {err.get('url','')}"
                        if err.get("body"):
                            body_text = re.sub(
                                r"<[^>]+>", " ", err["body"][:1000]
                            ).strip()
                            body_text = re.sub(r"\s+", " ", body_text)[:500]
                            error_detail += f" | Response: {body_text}"
                        print(f"      🌐 Network Error: {error_detail[:500]}")
                        network_error = error_detail
                except Exception as read_err:
                    print(f"      ⚠️ Could not read network capture: {read_err}")

                # Cleanup interceptor
                try:
                    page.evaluate("""() => {
                        delete window.__save_network_errors;
                        delete window.__save_network_all;
                    }""")
                except:
                    pass

                # Gọi hàm wait và detect error popup
                save_result = None
                if hasattr(self, "_wait_after_save"):
                    save_result = self._wait_after_save(
                        page, network_error=network_error
                    )
                else:
                    # Logic wait mặc định nếu chưa có hàm riêng
                    if network_error:
                        save_result = {"success": False, "error_message": network_error}
                    else:
                        try:
                            page.wait_for_load_state("networkidle", timeout=3000)
                        except:
                            time.sleep(2)

                # Check if save_result indicates an error
                if save_result and isinstance(save_result, dict):
                    if not save_result.get("success", True):
                        error_msg = save_result.get("error_message", "Unknown error")
                        print(f"      ❌ Save failed with error: {error_msg}")

                        # ========================================
                        # AUTO-FIX: Datetime format errors
                        # e.g. "time data '02/24/2026 00:00 AM' does not match format '%m/%d/%Y %I:%M %p'"
                        # ========================================
                        if (
                            "time data" in error_msg
                            and "does not match format" in error_msg
                        ):
                            print(
                                "      🔧 Attempting to auto-fix datetime format error..."
                            )
                            fixed = self._auto_fix_datetime_on_page(page, error_msg)
                            if fixed:
                                print("      🔄 Retrying save after datetime fix...")
                                time.sleep(1)
                                target_btn.scroll_into_view_if_needed()
                                time.sleep(0.3)
                                target_btn.click(force=True)
                                retry_result = (
                                    self._wait_after_save(page)
                                    if hasattr(self, "_wait_after_save")
                                    else None
                                )
                                if (
                                    retry_result
                                    and isinstance(retry_result, dict)
                                    and not retry_result.get("success", True)
                                ):
                                    return f"Error: {retry_result.get('error_message', 'Retry failed')}"
                                return "Success"

                        return f"Error: {error_msg}"

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

    def _wait_after_save(self, page, network_error=None):
        """Hàm phụ: Chờ thông báo thành công hoặc Popup đóng lại.
        Args:
            page: Playwright page object
            network_error: Optional string with HTTP error details from network interception
        Returns:
            dict: {"success": True/False, "error_message": str or None}
        """
        time.sleep(1)

        # ========================================
        # CHECK 0: Network-level HTTP errors (4xx, 5xx)
        # Đây là nguồn thông tin chính xác nhất vì đọc trực tiếp từ API response
        # ========================================
        if network_error:
            print(f"      🌐 Network error from API: {network_error}")
            # Vẫn kiểm tra UI popup để lấy thêm chi tiết nếu có
            ui_error = self._detect_ui_error_popup(page)
            if ui_error:
                combined_msg = f"{network_error} | UI: {ui_error}"
            else:
                combined_msg = network_error
            return {"success": False, "error_message": combined_msg}

        # ========================================
        # CHECK 1: Detect SweetAlert2 error popup (e.g., datetime format error)
        # ========================================
        try:
            # PVE dropdown/load can be slow; give more time for the success/error swal to appear
            swal_popup = page.locator(".swal2-popup")
            swal_popup.wait_for(state="visible", timeout=8000)

            popup_text = ""
            if swal_popup.is_visible():
                popup_text = swal_popup.inner_text().strip()

            if popup_text:
                clean_text = popup_text.replace("\n", " ").strip()[:500]
                print(f"      🚨 Popup detected after save: {clean_text[:200]}")

                # Click OK/Confirm to dismiss the popup
                try:
                    ok_btn = swal_popup.locator(
                        "button.swal2-confirm, button:has-text('OK')"
                    )
                    if ok_btn.count() > 0 and ok_btn.first.is_visible():
                        ok_btn.first.click(force=True)
                        # Wait until popup fully closes so caller doesn't refresh early
                        try:
                            swal_popup.wait_for(state="hidden", timeout=5000)
                        except:
                            time.sleep(0.5)
                except:
                    try:
                        page.evaluate("""
                            const btn = document.querySelector('button.swal2-confirm');
                            if (btn) btn.click();
                        """)
                        time.sleep(0.5)
                    except:
                        pass

                text_lower = popup_text.lower()
                error_keywords = [
                    "error",
                    "failed",
                    "invalid",
                    "duplicate",
                    "missing",
                    "required",
                    "not number",
                    "format",
                    "does not match",
                    "time data",
                    "lỗi",
                    "không hợp lệ",
                ]
                warning_keywords = [
                    "overlapping",
                    "overlap",
                    "already exists",
                    "are you sure",
                    "confirm",
                    "warning",
                    "proceed",
                    "continue",
                ]

                if any(k in text_lower for k in error_keywords):
                    print(f"      ❌ Error popup detected: {clean_text[:200]}")
                    return {"success": False, "error_message": clean_text}
                elif "success" in text_lower or "hoàn thành" in text_lower:
                    print("      ✅ Success popup detected.")
                    return {"success": True, "error_message": None}
                elif any(k in text_lower for k in warning_keywords):
                    print(
                        f"      ⚠️ Warning popup auto-dismissed (OK clicked): {clean_text[:200]}"
                    )
                    return {"success": True, "error_message": None}
                else:
                    print(f"      ⚠️ Unknown popup: {clean_text[:200]}")
                    return {"success": False, "error_message": clean_text}
        except:
            # No SweetAlert2 popup — that's fine, check other indicators
            pass

        # ========================================
        # CHECK 2: Detect Bootstrap alert/toast errors
        # Toastr toast structure: .toast > .toast-close-button + .toast-title + .toast-message
        # Phải target .toast-message cụ thể, không lấy inner_text() cả toast (sẽ bị lẫn "×", "Close")
        # ========================================
        try:
            error_toast = page.locator(".toast-error, .alert-danger, .alert-error")
            if error_toast.count() > 0 and error_toast.first.is_visible():
                # Ưu tiên lấy nội dung từ .toast-message (phần chứa chi tiết lỗi)
                err_text = ""
                try:
                    toast_msg = error_toast.first.locator(".toast-message")
                    if toast_msg.count() > 0:
                        err_text = toast_msg.first.inner_text().strip()[:500]
                except:
                    pass

                # Nếu không có .toast-message, thử lấy từ .toast-title
                if not err_text:
                    try:
                        toast_title = error_toast.first.locator(".toast-title")
                        if toast_title.count() > 0:
                            err_text = toast_title.first.inner_text().strip()[:300]
                    except:
                        pass

                # Fallback: lấy toàn bộ text nhưng loại bỏ "×" và "Close"
                if not err_text:
                    raw_text = error_toast.first.inner_text().strip()
                    err_text = re.sub(r"^[×x✕]\s*", "", raw_text, flags=re.IGNORECASE)
                    err_text = re.sub(
                        r"\bClose\b\s*", "", err_text, flags=re.IGNORECASE
                    ).strip()[:300]

                # Nếu sau khi clean vẫn chỉ còn "error" hoặc chuỗi rỗng → thêm note
                if not err_text or err_text.lower().strip() in ("error", "err", ""):
                    err_text = "Server error (toast had no details). Check Network tab for HTTP response."

                print(f"      ❌ Error toast detected: {err_text}")
                return {"success": False, "error_message": err_text}
        except:
            pass

        # ========================================
        # CHECK 3: Success indicators
        # ========================================
        try:
            # Chờ Toast Message xanh lá hiện lên (đảm bảo popup success đã hiện trước khi refresh)
            page.locator(".toast-success, .alert-success").wait_for(
                state="visible", timeout=8000
            )
            print("      ✅ Thành công (Toast detected).")
            return {"success": True, "error_message": None}
        except:
            pass

        try:
            # Chờ Modal đóng lại (nếu vừa bấm trong modal)
            page.locator(".modal-backdrop").wait_for(state="hidden", timeout=2000)
        except:
            pass

        return {"success": True, "error_message": None}

    def _detect_ui_error_popup(self, page):
        """Kiểm tra nhanh xem có popup lỗi nào đang hiển thị trên UI không.
        Dùng khi đã biết có network error, muốn lấy thêm thông tin từ UI.
        Returns:
            str or None: Nội dung popup lỗi, hoặc None nếu không tìm thấy.
        """
        try:
            # Check SweetAlert2
            swal = page.locator(".swal2-popup")
            if swal.count() > 0 and swal.is_visible():
                text = swal.inner_text().strip()[:500]
                # Dismiss popup
                try:
                    ok_btn = swal.locator("button.swal2-confirm, button:has-text('OK')")
                    if ok_btn.count() > 0 and ok_btn.first.is_visible():
                        ok_btn.first.click(force=True)
                        time.sleep(0.5)
                except:
                    pass
                return text
        except:
            pass

        try:
            # Check Bootstrap toast/alert errors
            error_el = page.locator(".toast-error, .alert-danger, .alert-error")
            if error_el.count() > 0 and error_el.first.is_visible():
                return error_el.first.inner_text().strip()[:300]
        except:
            pass

        try:
            # Check generic error message containers
            error_msg = page.locator(
                ".error-message, .form-error, #error-container, .validation-error"
            )
            if error_msg.count() > 0 and error_msg.first.is_visible():
                return error_msg.first.inner_text().strip()[:300]
        except:
            pass

        return None

    def _dismiss_are_you_sure_confirmations(self, page):
        """
        Auto-dismiss blocking confirmation dialogs like:
          - "Are you sure?"
          - "This event schedule is outside of the RBE's schedule"
        Usually shows OK (blue) / Cancel (grey).
        """
        try:
            import re as _re

            dialog_candidates = page.locator(
                ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible"
            )

            # Filter to only dialogs containing our keywords
            confirm_re = _re.compile(
                r"(are you sure|outside of the rbe.*schedule|outside.*rbe|wish to proceed|proceed.*anyway)",
                _re.IGNORECASE,
            )

            dismissed_any = False

            # We iterate by index to avoid locator re-evaluation issues after click
            count = dialog_candidates.count()
            for i in range(count):
                try:
                    d = dialog_candidates.nth(i)
                    if not d.is_visible():
                        continue
                    # NOTE: Do NOT auto-dismiss Bootstrap modal "Defining Schedules".
                    # In your case, its Close button is the actual "Save/confirm" for schedules.
                    # Clicking it early prevents filling End Time.
                    d_text = d.inner_text().strip()
                    if not d_text:
                        continue
                    if "defining schedules" in d_text.lower():
                        continue
                    if not confirm_re.search(d_text):
                        continue

                    # Prefer OK / Confirm / Yes. NEVER click "Close" or fallback "primary".
                    ok_btn = d.locator(
                        "button:has-text('OK'), button:has-text('Ok'), button:has-text('Confirm'), "
                        "button:has-text('Yes'), button:has-text('Proceed'), button:has-text('Continue')"
                    ).first

                    if ok_btn.count() > 0 and ok_btn.is_visible():
                        print(
                            f"      ✅ Auto-dismiss confirmation modal (OK): {d_text[:120]}..."
                        )
                        ok_btn.click(force=True)
                        dismissed_any = True
                    else:
                        # If no explicit OK/Confirm-like button exists, do not touch the modal.
                        # (Avoids cases where the only button is "Close" which is a real Save/submit.)
                        continue

                    # Wait briefly for modal to disappear/backdrop to hide
                    try:
                        d.wait_for(state="hidden", timeout=3000)
                    except:
                        pass
                    try:
                        page.locator(".modal-backdrop").first.wait_for(
                            state="hidden", timeout=2000
                        )
                    except:
                        pass

                    # After dismissing one, re-check remaining dialogs quickly
                    time.sleep(0.3)
                except Exception:
                    continue

            return dismissed_any
        except Exception:
            return False

    def close_popup(self, page):
        try:
            self._safe_press_escape(page)
            btn = page.locator("button:has-text('Close')").first
            if btn.is_visible():
                btn.click()
        except:
            pass

    # ============================
    # AUTO-FIX: DATETIME FORMAT ERROR
    # ============================
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

    def _main_form_scope(self, page):
        """Main content area — excludes left sidebar nav."""
        for sel in (
            "#content",
            ".content-wrapper",
            ".main-content",
            "#main-content",
            ".tab-content",
            "[role='main']",
        ):
            try:
                loc = page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
            except Exception:
                pass
        return page

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

        for label_el in (
            scope.locator("label, span, strong, b, div").filter(has_text=safe).all()
        ):
            try:
                if not label_el.is_visible():
                    continue
                if label_el.inner_text().strip().lower() != label_lower:
                    continue
                for xpath in (
                    "xpath=ancestor::div[contains(@class,'form-group')][1]",
                    "xpath=ancestor::div[contains(@class,'control-group')][1]",
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

    def _find_input_element(self, page, label_text):
        print(f"         🔍 Searching for field: '{label_text}'")

        # Known field aliases (Versus Tournament Daily Reward tab)
        # NOTE: IMPORTANT - "Event ID" must NOT map to "EventName".
        # This was causing the automation to type Event Name when the testcase requests Event ID.
        _field_aliases = {
            "time of reward utc": "start_time_send_daily_reward",
            "eventname": "EventName",
            "event name": "EventName",
        }

        label_key = label_text.lower().strip()
        # Special handling: Event ID (avoid wrong aliasing)
        if label_key in ("event id", "eventid"):
            # Try common casing/underscore variants
            for cand in [
                "EventID",
                "EventId",
                "eventID",
                "eventId",
                "event_id",
                "eventid",
            ]:
                alias_el = page.locator(f"#{cand}, [name='{cand}']").first
                if alias_el.count() > 0 and alias_el.is_visible():
                    print(f"         🎯 Field alias '{label_text}' → #{cand}")
                    return alias_el

        alias = _field_aliases.get(label_key)
        if alias:
            alias_el = page.locator(f"#{alias}, [name='{alias}']").first
            if alias_el.count() > 0 and alias_el.is_visible():
                print(f"         🎯 Field alias '{label_text}' → #{alias}")
                return alias_el

        # ─── Auto-scope to modal if one is open ────────────────────────────────────────
        # Shadow ‘page’ → modal so mọi page.locator() bên dưới đều scoped đúng
        for _ms in [".modal.show", ".modal.in", ".modal[aria-hidden='false']"]:
            try:
                if page.locator(_ms).count() > 0:
                    page = page.locator(_ms).last
                    print(f"         🔒 Auto-scoped to modal ({_ms})")
                    break
            except Exception:
                pass
        # ───────────────────────────────────────────────────────────────────

        label_lower = label_text.lower().strip()
        # Tạo version không space/underscore để fuzzy match
        label_normalized = re.sub(r"[\s_-]+", "", label_lower)

        # ─── SPECIAL CASE: Condition <select> (Win / Win against any rarity) ─────
        # Tránh việc chọn nhầm select khác trong cùng row/container (VD: event_id/background).
        # HTML thực tế thường là: <select class="condition" ...>
        if label_lower == "condition" or label_normalized == "condition":
            try:
                cond_sel = page.locator("select.condition").first
                if cond_sel.count() > 0:
                    return cond_sel

                # Fallback: name contains "condition"
                cond_sel2 = page.locator("select[name*='condition' i]").first
                if cond_sel2.count() > 0:
                    return cond_sel2
            except Exception:
                pass

        # ─── Keyword fallback for fields that may not have a visible <label> ─────
        # Example: "Superstars or Groups" can be rendered only as a custom select2/multiselect
        # without a direct label element, so label-based lookup fails.
        # We fallback by searching select[name/id] for "superstars"/"groups" keywords.
        if (
            any(k in label_lower for k in ["superstars", "groups", "group"])
            and label_normalized
        ):
            try:
                keyword_words = []
                if "superstars" in label_lower:
                    keyword_words.append("superstars")
                if "groups" in label_lower or "group" in label_lower:
                    keyword_words.append("groups")

                keyword_words = [w for w in keyword_words if w]
                if keyword_words:
                    selects = page.locator("select").all()
                    for sel in selects:
                        try:
                            sel_id = (sel.get_attribute("id") or "").lower()
                            sel_name = (sel.get_attribute("name") or "").lower()
                            sel_class = (sel.get_attribute("class") or "").lower()

                            if any(
                                w in sel_id or w in sel_name or w in sel_class
                                for w in keyword_words
                            ):
                                # Prefer wrapper if hidden/custom dropdown (select2/chosen)
                                if not sel.is_visible():
                                    wrapper = self._find_custom_dropdown_wrapper(sel)
                                    if wrapper:
                                        print(
                                            f"         ✅ Keyword fallback: wrapper for hidden '{label_text}' via select id/name containing {keyword_words}"
                                        )
                                        return wrapper
                                if sel.is_visible():
                                    print(
                                        f"         ✅ Keyword fallback: found select for '{label_text}' via id/name containing {keyword_words}"
                                    )
                                    return sel
                                # If hidden and no wrapper found, still return select (JS fill may work)
                                print(
                                    f"         ⚠️ Keyword fallback: returning hidden select for '{label_text}' (no wrapper found)"
                                )
                                return sel
                        except:
                            continue
            except Exception:
                pass

        # ========================================
        # PRIORITY 0: Direct ID/Name Match (Highest Priority)
        # Tìm element có ID hoặc name khớp với label (underscore/hyphen format)
        # VD: "Boost Result Value2" -> ID "boost_result_value2"
        # [FIX] Skip nếu label chứa ký tự đặc biệt CSS (parentheses, brackets, etc.)
        # VD: "PreEvent Phase Start Date Time(UTC)" chứa () → crash CSS selector
        # ========================================
        _has_css_special = bool(re.search(r'[()\[\]{}#.>+~:,\'"\\]', label_lower))
        if not _has_css_special:
            label_id_format = label_lower.replace(" ", "_").replace("-", "_")

            # CSS selector "#5_star" is invalid (id starts with digit).
            # Use attribute selector [id='...'] which is safe.
            if label_id_format and str(label_id_format)[0].isdigit():
                direct_by_id = page.locator(
                    f"[id='{label_id_format}'], [name='{label_id_format}']"
                ).first
            else:
                direct_by_id = page.locator(
                    f"#{label_id_format}, [name='{label_id_format}']"
                ).first

            if direct_by_id.count() > 0 and direct_by_id.is_visible():
                tag = (direct_by_id.evaluate("el => el.tagName") or "").lower()
                href = direct_by_id.get_attribute("href") or ""
                cls = direct_by_id.get_attribute("class") or ""
                is_nav_link = tag == "a" and ("navigate" in cls or href.startswith("#"))
                if is_nav_link:
                    print(
                        f"         ⚠️ Skip nav link #{label_id_format} "
                        f"(sidebar tab, not form toggle)"
                    )
                else:
                    print(f"         🎯 DIRECT MATCH by ID/name: '{label_id_format}'")
                    return direct_by_id

            # Try with hyphens too
            label_id_hyphen = label_lower.replace(" ", "-").replace("_", "-")

            if label_id_hyphen and str(label_id_hyphen)[0].isdigit():
                direct_by_id_hyphen = page.locator(
                    f"[id='{label_id_hyphen}'], [name='{label_id_hyphen}']"
                ).first
            else:
                direct_by_id_hyphen = page.locator(
                    f"#{label_id_hyphen}, [name='{label_id_hyphen}']"
                ).first

            if direct_by_id_hyphen.count() > 0 and direct_by_id_hyphen.is_visible():
                tag = (direct_by_id_hyphen.evaluate("el => el.tagName") or "").lower()
                href = direct_by_id_hyphen.get_attribute("href") or ""
                cls = direct_by_id_hyphen.get_attribute("class") or ""
                is_nav_link = tag == "a" and ("navigate" in cls or href.startswith("#"))
                if not is_nav_link:
                    print(
                        f"         🎯 DIRECT MATCH by ID/name (hyphen): '{label_id_hyphen}'"
                    )
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
                    # [FIX] Multiselect (Vue multiselect / custom-vue-multiselect)
                    # "Book Texture Icon" is rendered as <div class="multiselect">...</div>
                    # and the underlying <input> is hidden (style width:0/absolute),
                    # so searching only input/select/textarea will miss it.
                    try:
                        multiselect_box = parent_containers.locator(
                            "div.multiselect"
                        ).first
                        if multiselect_box.count() > 0:
                            # Return the visible wrapper if possible; otherwise still return it
                            if multiselect_box.is_visible():
                                print(
                                    f"         ✅ Found multiselect wrapper for '{label_text}' via fieldset container"
                                )
                                return multiselect_box
                            # Even if not visible, it can still be interacted with using force later
                            print(
                                f"         ⚠️ Found multiselect wrapper for '{label_text}' but it's not visible; returning anyway"
                            )
                            return multiselect_box
                    except:
                        pass

                    # [CRITICAL] Tìm input/select TRONG container này
                    # Không dùng fallback
                    elements = parent_containers.locator(
                        "select, input:not([type='radio']):not([type='button']):not([type='hidden']), textarea"
                    ).all()

                    print(
                        f"         📦 Found {len(elements)} input/select elements in container"
                    )

                    if len(elements) > 0:
                        # [FIX] PRE-SCAN: Tìm hidden SELECT (bị ẩn bởi Chosen.js/Select2) TRƯỚC
                        # Vì select gốc bị ẩn (display:none), code không tìm được nếu chỉ xét visible
                        # VD: select#id_event_type bị Chosen.js ẩn -> phải tìm wrapper của nó
                        _pre_scan_label_norm = label_lower.replace(" ", "_").replace(
                            "-", "_"
                        )
                        _pre_scan_words = [
                            w for w in _pre_scan_label_norm.split("_") if len(w) > 2
                        ]
                        for _el in elements:
                            if (
                                not _el.is_visible()
                                and _el.evaluate("el => el.tagName") == "SELECT"
                            ):
                                _el_name = (_el.get_attribute("name") or "").lower()
                                _el_id = (_el.get_attribute("id") or "").lower()
                                _ps_related = False
                                if (
                                    _pre_scan_label_norm in _el_name
                                    or _pre_scan_label_norm in _el_id
                                ):
                                    _ps_related = True
                                elif _el_name and _el_name in _pre_scan_label_norm:
                                    _ps_related = True
                                elif _el_id and _el_id in _pre_scan_label_norm:
                                    _ps_related = True
                                else:
                                    for _pw in _pre_scan_words:
                                        # Phải khớp cả từ (whole-word) trong name/id, không chỉ substring
                                        _name_parts = re.split(r"[_\-\s]", _el_name)
                                        _id_parts = re.split(r"[_\-\s]", _el_id)
                                        if _pw in _name_parts or _pw in _id_parts:
                                            _ps_related = True
                                            break
                                        if _pw.endswith("s") and (
                                            _pw[:-1] in _name_parts
                                            or _pw[:-1] in _id_parts
                                        ):
                                            _ps_related = True
                                            break
                                if _ps_related:
                                    _wrapper = self._find_custom_dropdown_wrapper(_el)
                                    if _wrapper:
                                        print(
                                            f"         ✅ Found Chosen/Select2 wrapper for hidden SELECT: name='{_el_name}', id='{_el_id}'"
                                        )
                                        return _wrapper
                                    else:
                                        print(
                                            f"         ⚠️ Hidden SELECT matched (name='{_el_name}') but no wrapper found, continuing..."
                                        )

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
                                    # Word-level match (whole-word only, không dùng substring)
                                    # VD: "type" KHÔNG được match "time_deduct_type" (chỉ match "event_type")
                                    _el_name_parts = set(re.split(r"[_\-\s]", _el_name))
                                    _el_id_parts = set(re.split(r"[_\-\s]", _el_id))
                                    for _w in _label_words:
                                        if _w in _el_name_parts or _w in _el_id_parts:
                                            _is_related = True
                                            break
                                        # Singular form (schedules -> schedule)
                                        if _w.endswith("s") and (
                                            _w[:-1] in _el_name_parts
                                            or _w[:-1] in _el_id_parts
                                        ):
                                            _is_related = True
                                            break

                                # Nếu container nhỏ (form-group/control-group) VÀ ít elements, accept thậm chí không related
                                # [FIX] Thêm điều kiện len(elements) <= 4 để tránh chọn nhầm trong container lớn
                                # VD: PreEvent Phase control-group có 14 elements → KHÔNG phải tight container
                                _is_tight_container = (
                                    container_source
                                    in [
                                        "xpath=ancestor::div[contains(@class,'form-group')]",
                                        "xpath=ancestor::div[contains(@class,'control-group')]",
                                        "xpath=ancestor::fieldset",
                                    ]
                                    and len(elements) <= 4
                                )

                                if _is_related or _is_tight_container:
                                    element = _el
                                    break
                                else:
                                    print(
                                        f"         ⏭️ Skip visible but unrelated element: tag={_el_tag}, name='{_el_name}', id='{_el_id}'"
                                    )

                        if not element and len(elements) <= 3:
                            # Fallback: nếu tất cả visible elements đều không related VÀ container nhỏ (<=3)
                            # [FIX] Chỉ fallback khi container thực sự nhỏ, tránh chọn nhầm trong container lớn
                            for _el in elements:
                                if _el.is_visible():
                                    element = _el
                                    print(
                                        f"         ⚠️ Using first visible element as fallback (small container: {len(elements)} elements)"
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
            clicked_exact = False
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
