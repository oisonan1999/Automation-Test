# automation/table_handler/table_checkbox.py - split from table_handler.py
# Select rows via checkbox (random/all/specific), safe check
import time
import re
import random


class TableCheckboxMixin:
    """Select rows via checkbox (random/all/specific), safe check"""

    def _safe_check(self, locator):
        try:
            # 1. Scroll dòng ra GIỮA MÀN HÌNH (Tránh bị Sticky Header che)
            locator.evaluate(
                "el => el.scrollIntoView({block: 'center', inline: 'nearest'})"
            )
            time.sleep(0.2)

            if locator.is_checked():
                print(f"         ✓ Already checked")
                return True

            # 2. Click thông thường
            try:
                locator.check(force=True, timeout=1000)
                print(f"         ✓ Checked via .check()")
            except Exception as e:
                print(f"         ⚠️ .check() failed: {e}")

            if locator.is_checked():
                return True

            # 3. Click vào ô cha (td) hoặc label nếu click input không ăn
            # (Đôi khi input bị ẩn, phải click vào cell)
            print(f"         ⚠️ Trying JS click...")
            locator.evaluate(
                "el => { el.click(); if(!el.checked) el.checked=true; el.dispatchEvent(new Event('change', {bubbles: true})); }"
            )
            time.sleep(0.1)

            is_checked = locator.is_checked()
            print(
                f"         {'✓' if is_checked else '✗'} JS click result: {is_checked}"
            )
            return is_checked
        except Exception as e:
            print(f"         ✗ _safe_check exception: {e}")
            return False

    def handle_checkbox(self, page, target_col, value):
        logs = []
        try:
            # FIX: Nếu value rỗng → default random_1
            if not value or str(value).strip() == "":
                print("   🔧 Value rỗng! Auto fallback → random_1")
                value = "random_1"

            # A. Tìm bảng dữ liệu chuẩn (tránh bảng header)
            target_table = self._find_data_table(page)
            if not target_table:
                return [
                    {
                        "step": "Checkbox",
                        "status": "FAIL",
                        "details": "No data table found",
                    }
                ]

            if not self.wait_for_table_data(page):
                return [
                    {
                        "step": "Checkbox",
                        "status": "FAIL",
                        "details": "Table Empty / Loading Timeout",
                    }
                ]

            # Lấy tất cả dòng dữ liệu
            # Lưu ý: Dùng target_table thay vì page để scope chính xác
            all_rows = target_table.locator("tbody tr").filter(has=page.locator("td"))
            total_rows = all_rows.count()

            print(f"   📊 Tìm thấy {total_rows} dòng dữ liệu khả dụng.")
            val_lower = str(value).lower()

            # Safety net: if target looks like a specific ID value (not a column header)
            # but value says random_N, swap them so CASE 3 searches for the exact ID.
            # "on" must NOT be used — core.py routes "on" to form-toggle before reaching here.
            _tgt_str = str(target_col).strip()
            if (
                "random" in val_lower
                and len(_tgt_str) > 10
                and "_" in _tgt_str
            ):
                print(f"   🔧 REDIRECT: checkbox target='{_tgt_str}' is specific ID, swap target↔value for CASE 3")
                value = _tgt_str
                target_col = "ID"
                val_lower = value.lower()

            # --- CASE 1: RANDOM ---
            if "random" in val_lower:
                num_to_select = 1
                match = re.search(r"random.*?(\d+)", val_lower)
                if match:
                    num_to_select = int(match.group(1))

                num_to_select = min(num_to_select, total_rows)
                selected_ids = []
                used_indices = set()

                # 🆕 Special handling:
                # If caller is trying to pick a random row by ID (e.g. "Filter một ID bất kỳ"
                # but action is mapped to checkbox random), we first pick a random ID text,
                # then use the table Filter box with that ID to mimic the intended UX
                # (filter/search) instead of pure random checkbox selection.
                target_col_lower = str(target_col).lower().strip()
                wants_id_filter = "id" in target_col_lower

                if num_to_select == 1 and wants_id_filter and total_rows > 0:
                    idx = random.randint(0, total_rows - 1)
                    row = all_rows.nth(idx)

                    try:
                        print(
                            f"      🎯 [ID-Random] Pick row #{idx+1} then filter by its ID text..."
                        )
                        cell_text = ""
                        all_cells = row.locator("td")
                        cell_count = all_cells.count()

                        for col_idx in range(1, min(cell_count, 5)):
                            try:
                                text = (
                                    all_cells.nth(col_idx)
                                    .inner_text(timeout=500)
                                    .strip()
                                )
                                if text and text not in ["", "-", "N/A"]:
                                    cell_text = text
                                    break
                            except Exception as cell_err:
                                print(
                                    f"      ⚠️ [ID-Random] Cell {col_idx} error: {cell_err}"
                                )

                        if not cell_text:
                            cell_text = f"Row_{idx+1}"
                            print(
                                f"      ⚠️ [ID-Random] No cell text found, fallback: {cell_text}"
                            )

                        print(f"      🔍 [ID-Random] Using search_term='{cell_text}'")
                        self.memory["LAST_SELECTED"] = cell_text
                        if "SELECTED_IDS" not in self.memory:
                            self.memory["SELECTED_IDS"] = []
                        self.memory["SELECTED_IDS"].append(cell_text)

                        # Filter table by the chosen ID text
                        if self._perform_table_filter(page, target_col, cell_text):
                            # Refresh rows after filter
                            target_table = self._find_data_table(page)
                            all_rows = target_table.locator("tbody tr").filter(
                                has=page.locator("td")
                            )

                            # Tick the matching row
                            if self._find_and_tick(all_rows, cell_text):
                                selected_ids.append(cell_text)
                                print(f"   ✅ [ID-Random] Filter+tick OK: {cell_text}")
                        # If filter+tick fails, fallback to direct random checkbox tick
                        if len(selected_ids) == 0:
                            chk = row.locator("input[type='checkbox']").first
                            if self._safe_check(chk):
                                selected_ids.append(cell_text)
                                print(
                                    f"   ✅ [ID-Random] Fallback direct tick OK: {cell_text}"
                                )
                    except Exception as e:
                        print(f"   ⚠️ [ID-Random] Failed: {type(e).__name__}: {e}")
                        # absolute fallback: try direct random tick without filter
                        chk = row.locator("input[type='checkbox']").first
                        if self._safe_check(chk):
                            fallback_id = f"Row_{idx+1}_checked"
                            selected_ids.append(fallback_id)

                    if len(selected_ids) == 0:
                        logs.append(
                            {
                                "step": "Checkbox",
                                "status": "FAIL",
                                "details": "ID-Random filter/tick failed",
                            }
                        )
                    else:
                        logs.append(
                            {
                                "step": "Checkbox",
                                "status": "PASS",
                                "details": f"ID-Random: {selected_ids[0]}",
                            }
                        )

                else:
                    attempts = 0
                    max_attempts = num_to_select * 3

                    while len(selected_ids) < num_to_select and attempts < max_attempts:
                        attempts += 1
                        idx = random.randint(0, total_rows - 1)
                        if idx in used_indices:
                            continue
                        used_indices.add(idx)

                        row = all_rows.nth(idx)
                        chk = row.locator("input[type='checkbox']").first

                        print(
                            f"      🎯 Row {idx+1}: Checkbox visible={chk.is_visible() if chk.count() > 0 else 'N/A'}"
                        )

                        check_result = self._safe_check(chk)
                        print(f"      🔍 _safe_check returned: {check_result}")

                        if check_result:
                            try:
                                print(f"      🔍 Attempting to get cell text...")
                                # Lấy ID/Text để lưu vào Memory - Thử nhiều cột để tìm text không rỗng
                                cell_text = ""
                                all_cells = row.locator("td")
                                cell_count = all_cells.count()
                                print(f"      🔍 Row has {cell_count} cells")

                                # Thử từ cột 1 đến hết (bỏ cột 0 vì đó là checkbox)
                                for col_idx in range(
                                    1, min(cell_count, 5)
                                ):  # Chỉ thử 4 cột đầu
                                    try:
                                        text = (
                                            all_cells.nth(col_idx)
                                            .inner_text(timeout=500)
                                            .strip()
                                        )
                                        print(f"      🔍 Cell {col_idx}: '{text}'")
                                        if text and text not in ["", "-", "N/A"]:
                                            cell_text = text
                                            break
                                    except Exception as cell_err:
                                        print(
                                            f"      ⚠️ Cell {col_idx} error: {cell_err}"
                                        )
                                        continue

                                if not cell_text:
                                    # Fallback: Lấy toàn bộ text của row
                                    cell_text = f"Row_{idx+1}"
                                    print(
                                        f"      ⚠️ No cell text found, using fallback: {cell_text}"
                                    )

                                print(f"      🔍 Got cell_text: '{cell_text}'")
                                self.memory["LAST_SELECTED"] = cell_text
                                if "SELECTED_IDS" not in self.memory:
                                    self.memory["SELECTED_IDS"] = []
                                self.memory["SELECTED_IDS"].append(cell_text)

                                selected_ids.append(cell_text)
                                print(f"   ✅ Đã tick dòng {idx+1}: {cell_text}")
                            except Exception as e:
                                print(
                                    f"   ⚠️ Exception getting cell text for row {idx+1}: {type(e).__name__}: {e}"
                                )
                                import traceback

                                traceback.print_exc()
                                # CRITICAL FIX: Vẫn count là đã chọn thành công nếu checkbox đã được tick
                                fallback_id = f"Row_{idx+1}_checked"
                                selected_ids.append(fallback_id)
                                print(f"   ⚠️ Using fallback ID: {fallback_id}")
                        else:
                            print(f"   ⚠️ Lỗi tick dòng {idx+1}. Thử dòng khác...")
                        time.sleep(0.2)

                    if len(selected_ids) < num_to_select:
                        print(
                            f"   ⚠️ Chỉ chọn được {len(selected_ids)}/{num_to_select} dòng."
                        )

                    # [FIX] Nếu không chọn được dòng nào, trả về FAIL
                    if len(selected_ids) == 0:
                        logs.append(
                            {
                                "step": "Checkbox",
                                "status": "FAIL",
                                "details": f"Không thể chọn bất kỳ dòng nào. Target: random {num_to_select}",
                            }
                        )
                    else:
                        logs.append(
                            {
                                "step": "Checkbox",
                                "status": (
                                    "PASS"
                                    if len(selected_ids) == num_to_select
                                    else "PARTIAL"
                                ),
                                "details": f"Random: {selected_ids} ({len(selected_ids)}/{num_to_select})",
                            }
                        )

            # --- CASE 2: ALL ---
            elif "all" in val_lower:
                h = target_table.locator("thead input[type='checkbox']").first
                if h.is_visible():
                    self._safe_check(h)
                    time.sleep(1)
                else:
                    # Fallback: Tick từng cái (tối đa 20 cái đầu)
                    limit = min(total_rows, 20)
                    for i in range(limit):
                        self._safe_check(
                            all_rows.nth(i).locator("input[type='checkbox']").first
                        )
                        time.sleep(0.1)
                logs.append(
                    {"step": "Checkbox", "status": "PASS", "details": "Select All"}
                )

            # --- CASE 3: SPECIFIC TARGET (CÓ AUTO-FILTER) ---
            else:
                # 3a. Tìm dòng khớp regex (Logic của bạn)
                target_regex = self._safe_compile(
                    target_col
                )  # target_col lúc này đóng vai trò là text cần tìm (vì value='on') hoặc value thực tế

                # Nếu User gọi lệnh: "checkbox -> ID ABC" thì target_col='ID', value='ABC' -> Cần tìm 'ABC'
                # Nếu User gọi lệnh: "checkbox -> ABC on" thì target_col='ABC', value='on' -> Cần tìm 'ABC'
                # Logic: Nếu value là on/off/true/false -> Tìm target_col. Ngược lại tìm value.
                search_term = (
                    str(value)
                    if str(value).lower() not in ["on", "off", "true", "false"]
                    else str(target_col)
                )

                # BƯỚC 1: Tìm trực tiếp qua Playwright locator
                found = self._find_and_tick(all_rows, search_term)

                # BƯỚC 1b: JS fallback — Playwright has_text filter can miss rows
                # whose cell text is mixed with icon-button DOM nodes (e.g. PVE events
                # Book column: clone icon + ID text in same td). JS textContent.includes
                # reads the full rendered text regardless of DOM nesting.
                if not found:
                    try:
                        js_found = page.evaluate(
                            """(text) => {
                                const term = text.toLowerCase();
                                for (const tbl of document.querySelectorAll('table')) {
                                    for (const row of tbl.querySelectorAll('tbody tr')) {
                                        if (!row.textContent.toLowerCase().includes(term)) continue;
                                        const chk = row.querySelector('input[type="checkbox"]');
                                        if (!chk) continue;
                                        chk.scrollIntoView({block: 'center', inline: 'nearest'});
                                        if (!chk.checked) {
                                            chk.click();
                                            chk.dispatchEvent(new Event('change', {bubbles: true}));
                                        }
                                        return true;
                                    }
                                }
                                return false;
                            }""",
                            search_term,
                        )
                        if js_found:
                            found = True
                            print(f"   ✅ JS DOM search: Đã tick dòng chứa '{search_term}'")
                    except Exception as _js_err:
                        print(f"   ⚠️ JS fallback error: {_js_err}")

                # BƯỚC 2: Nếu vẫn không thấy -> FILTER -> Tìm lại
                if not found:
                    print(
                        f"   ⚠️ Không thấy '{search_term}' trên trang hiện tại. Đang thử Filter..."
                    )
                    if self._perform_table_filter(page, target_col, search_term):
                        # Cập nhật lại rows sau khi filter
                        target_table = self._find_data_table(page)
                        all_rows = target_table.locator("tbody tr").filter(
                            has=page.locator("td")
                        )

                        if self._find_and_tick(all_rows, search_term):
                            found = True

                if found:
                    logs.append(
                        {"step": "Checkbox", "status": "PASS", "details": search_term}
                    )
                else:
                    logs.append(
                        {
                            "step": "Checkbox",
                            "status": "FAIL",
                            "details": f"Not found: {search_term}",
                        }
                    )

        except Exception as e:
            logs.append({"step": "Checkbox", "status": "FAIL", "details": str(e)})
        return logs

    def _find_and_tick(self, rows_locator, text):
        """Tìm dòng chứa text và tick checkbox"""
        reg = self._safe_compile(text)
        matched = rows_locator.filter(has_text=reg)
        target_row = matched.first

        # count() > 0: row exists in DOM even if off-screen/below fold.
        # is_visible() returns False for off-viewport rows → missed rows that are
        # actually present. _safe_check already calls scrollIntoView so force works.
        if matched.count() > 0:
            chk = target_row.locator("input[type='checkbox']").first
            if self._safe_check(chk):
                print(f"   ✅ Đã tick dòng chứa '{text}'")
                return True
        return False

