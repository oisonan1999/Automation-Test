# automation/table_handler.py - Table operations: checkbox, row actions, filtering
# Tách từ form_handler.py để giảm kích thước monolith
import time
import re
import random


class TableHandlerMixin:
    """Chứa logic tương tác với Table: Checkbox, Edit/Clone Row, Filter"""

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

            # --- CASE 1: RANDOM ---
            if "random" in val_lower:
                num_to_select = 1
                match = re.search(r"random.*?(\d+)", val_lower)
                if match:
                    num_to_select = int(match.group(1))

                num_to_select = min(num_to_select, total_rows)
                selected_ids = []
                used_indices = set()

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
                                    print(f"      ⚠️ Cell {col_idx} error: {cell_err}")
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

                # BƯỚC 1: Tìm trực tiếp
                found = self._find_and_tick(all_rows, search_term)

                # BƯỚC 2: Nếu không thấy -> FILTER -> Tìm lại
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

    def _click_icon_in_row(self, page, target_text, action_type):
        if target_text == "LAST_SELECTED":
            target_text = self.memory.get("LAST_SELECTED", "")
            if not target_text:
                print("   ⚠️ Memory rỗng! Dùng fallback lấy dòng đầu tiên...")
                target_text = (
                    page.locator("tbody tr")
                    .first.locator("td")
                    .nth(1)
                    .inner_text()
                    .strip()
                )
            else:
                print(f"   🧠 Recall Memory: '{target_text}'")

        print(f"   🔎 Tìm dòng '{target_text}' để {action_type}...")

        js_script = """
            (args) => {
                const targetText = args.text.toLowerCase().trim();
                const action = args.action; 
                const rows = Array.from(document.querySelectorAll('tbody tr'));
                
                for (const row of rows) {
                    if (row.innerText.toLowerCase().includes(targetText)) {
                        let btn = null;
                        if (action === 'edit') {
                            btn = row.querySelector("i[class*='edit'], i[class*='pencil'], .btn-edit");
                        } else {
                            btn = row.querySelector("i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone");
                        }
                        if (btn) {
                            (btn.closest('button') || btn.closest('a') || btn).click();
                            return "Clicked via Icon";
                        }
                        const buttons = row.querySelectorAll("button, a.btn, a[class*='btn']");
                        if (buttons.length > 0) {
                            if (buttons.length >= 2) { (action === 'edit' ? buttons[0] : buttons[1]).click(); } 
                            else { buttons[0].click(); }
                            return "Clicked via Position";
                        }
                    }
                }
                return "Row Not Found";
            }
        """
        result = page.evaluate(
            js_script, {"text": str(target_text), "action": action_type}
        )

        if "Clicked" in result:
            print(f"   ✅ JS Click Success: {result}")

            # [CRITICAL] Check for Locked Item popup after edit/clone click
            # Some items may be locked by other users
            # Chờ đủ lâu để popup có thời gian render (tăng từ 0.5s lên 1s)
            time.sleep(1.0)
            if action_type == "edit" or action_type == "clone":
                popup_handled = self._handle_locked_item_popup(page)
                if popup_handled:
                    # After acquiring lock, wait for form to fully load
                    time.sleep(1.0)
                    print("      ✅ Ready to update form.")
                else:
                    # No popup = item unlocked, proceed normally
                    time.sleep(0.5)
        elif "Row Not Found" in result:
            if self._auto_filter_data(page, target_text):
                result = page.evaluate(
                    js_script, {"text": str(target_text), "action": action_type}
                )
                # Same lock check after retry
                if "Clicked" in result and (
                    action_type == "edit" or action_type == "clone"
                ):
                    time.sleep(1.0)
                    popup_handled = self._handle_locked_item_popup(page)
                    if popup_handled:
                        time.sleep(1.0)
                        print("      ✅ Ready to update form.")
                    else:
                        time.sleep(0.5)
            else:
                raise Exception(f"Không tìm thấy dòng '{target_text}'")

    # ============================
    # TABLE HELPERS
    # ============================

    def _auto_filter_data(self, page, keyword):
        try:
            search_input = None
            placeholders = ["ID", "Search", "Name", "Filter", "Title"]
            for p in placeholders:
                inp = page.get_by_placeholder(re.compile(p, re.IGNORECASE)).first
                if inp.is_visible():
                    search_input = inp
                    break

            if not search_input:
                search_input = page.locator("input[type='text']:visible").first

            if search_input and search_input.is_visible():
                print(f"      👉 Auto Filter: '{keyword}'")
                search_input.fill(keyword)
                search_input.press("Enter")
                time.sleep(2)
                return True
        except:
            pass
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

    def _find_and_tick(self, rows_locator, text):
        """Tìm dòng chứa text và tick checkbox"""
        reg = self._safe_compile(text)
        target_row = rows_locator.filter(has_text=reg).first

        if target_row.is_visible():
            chk = target_row.locator("input[type='checkbox']").first
            if self._safe_check(chk):
                print(f"   ✅ Đã tick dòng chứa '{text}'")
                return True
        return False

    def _perform_table_filter(self, page, col_name, value):
        """Tự động điền Filter và bấm nút"""
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
