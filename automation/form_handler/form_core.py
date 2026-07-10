# automation/form_handler/form_core.py - split from form_handler.py
# Main form dispatcher (_smart_update_form) + scope/util helpers
import time
import re
import random
from playwright.sync_api import Page


class FormCoreMixin:
    """Main form dispatcher (_smart_update_form) + scope/util helpers"""

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

        # 🧠 Remember clone modal "New ... ID" so later edit_row can be deterministic
        # even if the action plan says RANDOM.
        try:
            if isinstance(data, dict):
                for k, v in data.items():
                    kl = str(k).lower()
                    if "new" in kl and "id" in kl and v is not None:
                        new_id = str(v).strip()
                        if new_id:
                            # Use a stable key for later row lookup
                            self.memory["LAST_CLONED_NEW_ID"] = new_id
                            print(
                                f"   🧠 Memory: LAST_CLONED_NEW_ID='{new_id}' (from '{k}')"
                            )
                            break
        except Exception as _mem_e:
            print(f"   ⚠️ Memory capture failed: {_mem_e}")

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

        # SPECIAL (RBE): clamp Defining-Schedules Start/End Time to parent RBE schedule range
        self._handle_rbe_contest_superstar(page, data)

        # SPECIAL (PVE): Contest Superstar toggle + Normal/Hard/Hell panels (Node 1 + SS/Soft Currency)
        self._handle_pve_contest_superstar(page, data)

        for label, value in data.items():
            # DNU Warning / "Are you sure" from the PREVIOUS field fill may still be visible.
            # Dismiss it before attempting the next field so it doesn't block the fill.
            try:
                ensure_fn = getattr(self, "_ensure_rbe_are_you_sure_closed", None)
                if callable(ensure_fn):
                    ensure_fn(page)
            except Exception:
                pass

            # ============================
            # RANDOM FILTER RESOLVER
            # Any filter/search field with value "RANDOM" → pick a real row ID from the table.
            # Covers "ID contains" (most pages), "Offer Name" (Offer page), etc.
            # In update_form context, RANDOM always means a filter sentinel — never a literal value.
            # ============================
            is_filter_sentinel = str(value).strip().upper() == "RANDOM"
            if is_filter_sentinel:
                try:
                    _filter_js = """
                        (requireVisible) => {
                            // Strict: game event ID (e.g. "RBE_Jun2026_Wknd1")
                            const isIdLike = t => /^[A-Z][a-zA-Z]+_/.test(t);

                            // Use .th-inner text when available (fixed-header tables duplicate
                            // content via .fht-cell div — textContent of th would include both).
                            const getHeaderText = th => {
                                const inner = th.querySelector('.th-inner');
                                return ((inner ? inner.textContent : th.textContent) || '').trim();
                            };

                            // ---------------------------------------------------------------
                            // VALUE-BASED COLUMN SCORING, evaluated across EVERY candidate
                            // table on the page (not just the first one found). Committing to
                            // the FIRST table with any non-empty tbody text is unsafe — many
                            // Brick pages have unrelated layout/nav/widget tables earlier in
                            // the DOM than the real data grid, so that table could win with
                            // zero viable ID columns and the resolver would return null even
                            // though the real data table (later in the DOM) has a perfectly
                            // good ID column (Currency-page failure). Instead, score every
                            // column of every table and pick the single best table+column
                            // combo globally.
                            // ---------------------------------------------------------------
                            const isDateish = t =>
                                /\\d{4}-\\d{1,2}-\\d{1,2}/.test(t) ||          // 2026-06-29
                                /\\d{1,2}\\/\\d{1,2}\\/\\d{2,4}/.test(t) ||    // 06/29/2026
                                /\\d{1,2}:\\d{2}/.test(t) ||                   // 02:14
                                /\\b(AM|PM)\\b/.test(t);                       // AM/PM
                            const isDash = t => !t || /^[-—–]+$/.test(t);
                            const isControlWord = t =>
                                /^(edit|clone|delete|copy|view|remove|select|action)$/i.test(t);

                            // Score how much a single cell value looks like a row ID.
                            const scoreVal = t => {
                                if (isDash(t) || isDateish(t) || isControlWord(t)) return -100;
                                if (/^\\d+$/.test(t)) return t.length >= 3 ? 2 : -50;  // numeric ID
                                let s = 0;
                                if (/^[A-Za-z][\\w]*_[\\w]/.test(t)) s += 5;   // has an underscore token
                                if (/^[A-Z][a-zA-Z]+_/.test(t)) s += 3;        // strict game-event ID
                                if (/[a-z]/.test(t) && /[A-Z]/.test(t)) s += 2; // mixed case
                                if (/^!!/.test(t)) s -= 4;                      // localization key (Name/Desc)
                                if (/\\s/.test(t)) s -= 2;                      // has spaces (e.g. "Gacha Token")
                                if (t.length < 3) s -= 3;
                                return s;
                            };

                            let best = null;  // { score, col, rows }
                            for (const tbl of document.querySelectorAll('table')) {
                                const rows = [...tbl.querySelectorAll('tbody tr')]
                                    .filter(r => (requireVisible ? r.offsetParent : true)
                                        && (r.textContent || '').trim().length > 0);
                                if (rows.length === 0) continue;

                                const sampleRows = rows.slice(0, 8);
                                const maxCols = Math.max(
                                    0, ...sampleRows.map(r => r.querySelectorAll('td').length));
                                if (maxCols === 0) continue;

                                // Only trust THIS table's own thead for the ID-header bonus
                                // (guaranteed aligned to its own <td>s); a borrowed header from
                                // a different (e.g. fixedHeader clone) table can't be trusted
                                // to align 1:1, so we never cross-reference other tables here.
                                const ownHeaders = [...tbl.querySelectorAll('thead th, thead td')];
                                const headersAligned =
                                    ownHeaders.some(h => getHeaderText(h)) &&
                                    Math.abs(ownHeaders.length - maxCols) <= 1;
                                const headerHasId = i => {
                                    if (!headersAligned) return false;
                                    const h = ownHeaders[i];
                                    if (!h) return false;
                                    const t = getHeaderText(h).toLowerCase();
                                    return (/\\bid\\b/.test(t) || t.endsWith('id')) &&
                                        !t.includes('modified') && !t.includes('valid');
                                };

                                for (let c = 0; c < maxCols; c++) {
                                    let colScore = 0, valid = 0, hasControl = false;
                                    for (const r of sampleRows) {
                                        const cell = r.querySelectorAll('td')[c];
                                        if (!cell) continue;
                                        if (cell.querySelector('input, button, select, a.btn')) {
                                            hasControl = true; break;  // checkbox / action column
                                        }
                                        const sv = scoreVal((cell.textContent || '').trim());
                                        colScore += sv;
                                        if (sv > 0) valid++;
                                    }
                                    if (hasControl || valid === 0) continue;
                                    // Normalize by sample size so tables aren't compared unfairly
                                    // just because one has more sampled rows than another.
                                    let avg = colScore / sampleRows.length;
                                    if (headerHasId(c)) avg += 100;  // header confirms ID column
                                    if (!best || avg > best.score) {
                                        best = {score: avg, col: c, rows};
                                    }
                                }
                            }

                            if (best) {
                                for (const r of best.rows) {
                                    const cell = r.querySelectorAll('td')[best.col];
                                    if (!cell) continue;
                                    const t = (cell.textContent || '').trim();
                                    if (scoreVal(t) > 0) return t.substring(0, 60);
                                }
                            }

                            // Last resort: strict game-event-ID pattern anywhere on the page.
                            for (const tbl of document.querySelectorAll('table')) {
                                const rows = [...tbl.querySelectorAll('tbody tr')]
                                    .filter(r => (requireVisible ? r.offsetParent : true));
                                for (const row of rows) {
                                    const cells = row.querySelectorAll('td');
                                    for (let i = 0; i < cells.length; i++) {
                                        const text = (cells[i].textContent || '').trim();
                                        if (isIdLike(text)) return text.substring(0, 60);
                                    }
                                }
                            }
                            return null;
                        }
                    """
                    # The data table is usually still loading (AJAX) when we
                    # arrive from navigation. Clear spinners + wait for rows
                    # BEFORE reading a row ID, otherwise we resolve to "".
                    _wait_long = getattr(self, "_wait_for_long_loading", None)
                    _wait_rows = getattr(self, "wait_for_table_data", None)
                    if callable(_wait_long):
                        try:
                            _wait_long(page)
                        except Exception:
                            pass
                    # Retry: alternate waiting for rows with the JS resolve.
                    resolved = None
                    for _attempt in range(5):
                        if callable(_wait_rows):
                            try:
                                _wait_rows(page, timeout=8)
                            except Exception:
                                pass
                        resolved = page.evaluate(_filter_js, True)
                        if resolved:
                            break
                        page.wait_for_timeout(1500)
                    # Last resort: read rows ignoring strict visibility (handles
                    # tables whose rows briefly report offsetParent === null).
                    if not resolved:
                        resolved = page.evaluate(_filter_js, False)
                    if resolved:
                        value = resolved
                        print(f"         🎲 RANDOM filter resolved → '{value}'")
                    else:
                        print(f"         ⚠️ RANDOM filter: no visible table rows found, using empty string")
                        value = ""
                except Exception as _re:
                    print(f"         ⚠️ RANDOM filter resolve failed: {_re}")

            # FILTER SENTINEL: fill the page's filter/search box directly.
            # The box label varies per page ("ID contains", "Offer Name", ...),
            # so find it structurally (Filter Results bar) instead of by the
            # AI-provided label. This makes "Filter ... bất kỳ" work on every page.
            if is_filter_sentinel:
                try:
                    if self._fill_page_filter_box(page, value):
                        print(f"         ✅ Filter box filled with '{value}'")
                        continue
                    print(
                        "         ⚠️ Dedicated filter box not found — "
                        "falling back to label-based search"
                    )
                except Exception as _fb_err:
                    print(f"         ⚠️ Filter box fill error: {_fb_err}")

            # Strip contextual location suffix added by AI:
            # "Gate in Chapter Info" → "Gate", "Gate trong Chapter Info" → "Gate"
            _loc_suffix = re.search(
                r"\s+(in|trong)\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s*$",
                str(label),
            )
            if _loc_suffix:
                label = str(label)[: _loc_suffix.start()].strip()

            print(f"         ↳ Processing '{label}' -> '{value}'")
            try:
                label_lower = str(label).lower().strip()
                value_lower = str(value).lower().strip()

                # ============================
                # CHECKBOX/TOGGLE LABEL SUFFIX FIX
                # AI sometimes appends " checkbox" / " toggle" to label names
                # (e.g. "Hide LiveOpsTest gate items checkbox") but the actual page
                # label has no such suffix. Strip it and route to the toggle filler.
                # ============================
                _cs_suffix_match = re.search(
                    r"\s+(checkbox|toggle|check|switch)\s*$", label_lower
                )
                if _cs_suffix_match:
                    _clean_label = label_lower[: _cs_suffix_match.start()].strip()
                    try:
                        _tog_ok = self._try_set_form_toggle_by_label(
                            page, _clean_label, value
                        )
                    except Exception:
                        _tog_ok = False
                    if _tog_ok:
                        print(
                            f"         ✅ Toggle '{_clean_label}' set (stripped suffix '{_cs_suffix_match.group().strip()}' from label)"
                        )
                        continue

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
                # SPECIAL CASE 3b: CSS row plain-number inputs (Attempt / Amount)
                # These fields have no <label> — only placeholder/title/class attrs.
                # Always target .last so we fill the most recently added CSS row.
                # ========================================
                if label_lower in ("attempt", "amount"):
                    try:
                        _css_inp = page.locator(
                            f"input[placeholder='{label}'], input[title='{label}']"
                        ).last
                        if _css_inp.count() > 0 and _css_inp.is_visible(timeout=2000):
                            _css_inp.click(force=True)
                            _css_inp.fill(str(value))
                            print(
                                f"         ✅ CSS row field '{label}' filled via placeholder → '{value}'"
                            )
                            time.sleep(0.5)
                            continue
                    except Exception as _css_e:
                        print(f"         ⚠️ CSS row field '{label}' placeholder fill failed: {_css_e}")

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
                        # Dismiss any blocking popup that appeared as a result of the field fill
                        # e.g. "Are you sure? This CSS event is already set in RBE"
                        #      "DNU Warning: X is currently in the DNU list"
                        # These appear AFTER Select2 selection and would block the next action.
                        try:
                            ensure_fn = getattr(self, "_ensure_rbe_are_you_sure_closed", None)
                            if callable(ensure_fn):
                                ensure_fn(page)
                        except Exception:
                            pass
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
                            try:
                                ensure_fn = getattr(self, "_ensure_rbe_are_you_sure_closed", None)
                                if callable(ensure_fn):
                                    ensure_fn(page)
                            except Exception:
                                pass
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

    def _fill_page_filter_box(self, page, value):
        """
        Find and fill the page's filter/search text box structurally, regardless
        of its visible label. Every Brick list page has a "Filter Results" bar
        with a text input (labeled "ID contains" on most pages, sometimes other
        labels) next to a "Filter Data" / "Filter" button.

        Returns True if a box was found and filled, else False.

        DOM reality (Offer Section): the filter is a plain GET form where the
        label "ID contains:" is a RAW TEXT NODE right before its <input>, and
        the Gate <select> is enhanced to a select2/chosen widget that injects
        its OWN search <input>. So we must (a) read preceding text nodes — not
        just element text — to locate the "contains" input, and (b) hard-exclude
        any input that lives inside a dropdown widget (Gate), otherwise we type
        the row ID into the Gate search box.

        Scoring (highest wins):
          +100  preceding text / label / name / placeholder mentions "contains"
          + 40  preceding text mentions "id" (e.g. "ID contains:")
          + 20  shares a <form>/container with a visible "Filter" button
        Candidates inside select2/chosen/multiselect/dropdown wrappers are
        discarded entirely. Filled via JS input/change/keyup events.
        """
        sel = page.evaluate(
            """
            (val) => {
                const vis = el => el && el.offsetParent !== null
                    && !el.disabled && !el.readOnly;
                const isText = el => el.tagName === 'INPUT'
                    && (!el.type || /^(text|search)$/i.test(el.type));
                // Inputs injected by dropdown widgets (the Gate select2/chosen).
                const inDropdownWidget = el => !!el.closest(
                    '.select2-container, .select2, .chosen-container, '
                    + '.multiselect, .vue-treeselect, .dropdown-menu, .ts-wrapper'
                );

                // Text immediately preceding the input (incl. raw text nodes).
                const precedingText = el => {
                    let txt = '';
                    let n = el.previousSibling, hops = 0;
                    while (n && hops < 8 && txt.length < 80) {
                        txt = ((n.textContent || '') + ' ' + txt);
                        n = n.previousSibling; hops++;
                    }
                    // include any leading text of the parent if still thin
                    if (txt.trim().length < 3 && el.parentElement) {
                        txt = (el.parentElement.textContent || '') + ' ' + txt;
                    }
                    return txt.toLowerCase().replace(/\\s+/g, ' ').trim();
                };

                const mark = el => {
                    el.setAttribute('data-autogameops-filter', '1');
                    el.focus();
                    el.value = val;
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, key: 'a'}));
                    return true;
                };

                // Visible "Filter" buttons → their forms/containers (for scoring).
                const filterBtns = [...document.querySelectorAll(
                    'button, a.btn, input[type=button], input[type=submit]')]
                    .filter(b => /filter/i.test((b.textContent || b.value || '')) && vis(b));
                const sharesFilterContainer = inp => filterBtns.some(b => {
                    const f = inp.closest('form');
                    if (f && f.contains(b)) return true;
                    let c = inp.parentElement;
                    for (let h = 0; h < 4 && c; h++) { if (c.contains(b)) return true; c = c.parentElement; }
                    return false;
                });

                let best = null, bestScore = -1;
                for (const inp of document.querySelectorAll('input')) {
                    if (!vis(inp) || !isText(inp) || inDropdownWidget(inp)) continue;
                    const pre = precedingText(inp);
                    const meta = ((inp.name || '') + ' ' + (inp.id || '')
                        + ' ' + (inp.placeholder || '')
                        + ' ' + (inp.getAttribute('aria-label') || '')).toLowerCase();
                    let score = 0;
                    if (pre.includes('contains') || meta.includes('contains')) score += 100;
                    if (/\\bid\\b/.test(pre) || /\\bid\\b/.test(meta)) score += 40;
                    if (sharesFilterContainer(inp)) score += 20;
                    // A bare unlabeled box in the filter bar still beats nothing.
                    if (score === 0 && sharesFilterContainer(inp)) score = 5;
                    if (score > bestScore) { bestScore = score; best = inp; }
                }
                if (best && bestScore > 0) return mark(best);
                return false;
            }
            """,
            value,
        )
        if not sel:
            return False
        # Confirm via Playwright (keeps state coherent with the rest of the loop).
        try:
            loc = page.locator("[data-autogameops-filter='1']").first
            if loc.count() > 0:
                loc.evaluate("el => el.removeAttribute('data-autogameops-filter')")
        except Exception:
            pass
        return True

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
