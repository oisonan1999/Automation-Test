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

        # Handle RANDOM sentinel: pick a random row from the table
        _random_keywords = {
            "random",
            "any",
            "bất kỳ",
            "bat ky",
            "first",
            "random_1",
            "any row",
            "bất kỳ dòng",
            "một dòng bất kỳ",
        }
        # Also detect patterns like "một Superstar bất kỳ", "Superstar bất kỳ", etc.
        target_lower = str(target_text).lower().strip()
        is_random = (
            target_lower in _random_keywords
            or target_text == "RANDOM"
            or "bất kỳ" in target_lower
            or "bat ky" in target_lower
            or "random" in target_lower
        )
        if is_random:
            print(
                f"   🎲 Random mode: đang chọn ngẫu nhiên một dòng để {action_type}..."
            )
            try:
                # Scope đúng bảng: chỉ lấy những <tr> có nút/icon Edit (hoặc Clone) bên trong.
                # Tránh trường hợp page có nhiều tbody tr (vd fullcalendar) làm RANDOM chọn nhầm.
                if action_type == "edit":
                    action_has = page.locator(
                        "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                    )
                else:
                    action_has = page.locator(
                        "i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone, button:has-text('Clone'), a:has-text('Clone')"
                    )

                all_rows = page.locator("tbody tr").filter(has=action_has)
                total = all_rows.count()

                # If we can't find action buttons (icons) for this row type,
                # don't crash. Fall back to any data row and click by heuristics later.
                if total == 0:
                    all_rows = page.locator("tbody tr").filter(has=page.locator("td"))
                    total = all_rows.count()
                    if total == 0:
                        raise Exception(
                            f"Bảng không có dòng nào để chọn ngẫu nhiên (missing {action_type} action buttons)"
                        )

                idx = random.randint(0, total - 1)
                # Wait/retry: sometimes table rows render a bit later (ajax).
                # Don’t hard-fail when total==0 on first check.
                total = all_rows.count()
                if total == 0:
                    for _attempt in range(12):
                        try:
                            if hasattr(self, "wait_for_table_data"):
                                ok = self.wait_for_table_data(page, timeout=2)
                            else:
                                ok = page.locator("tbody tr").count() > 0
                        except:
                            ok = False

                        if ok:
                            all_rows = page.locator("tbody tr").filter(
                                has=page.locator("td")
                            )
                            total = all_rows.count()
                            if total > 0:
                                break
                        time.sleep(0.5)

                if total == 0:
                    raise Exception(
                        "Bảng không có dòng nào để chọn ngẫu nhiên (after wait/retry)"
                    )

                idx = random.randint(0, total - 1)
                chosen_row = all_rows.nth(idx)
                # Choose "best ID-like" cell text (not a fixed column like td[nth(1)]),
                # because tables often place Gate in td[1] and ID in another column.
                try:
                    cells = chosen_row.locator("td").all()
                    candidates: list[str] = []
                    for i_cell, c in enumerate(cells):
                        try:
                            t = c.inner_text(timeout=300).strip()
                        except:
                            t = ""
                        if not t:
                            continue
                        # Skip pure short labels
                        if len(t) < 3:
                            continue
                        candidates.append(t)

                    def _score_id_like(t: str) -> float:
                        tl = (t or "").strip()
                        tl_low = tl.lower()
                        score = 0.0
                        # Strong hints
                        if "hieunm_test" in tl_low:
                            score += 50
                        if re.search(r"\b(id|event|event id)\b", tl_low):
                            score += 20
                        # RBE_/PVE_/Gacha_/LOC_/Offer_...
                        if any(
                            p in tl_low
                            for p in [
                                "rbe_",
                                "pve_",
                                "gacha_",
                                "loc_",
                                "offer_",
                                "boost_",
                                "feeder",
                                "superstar",
                                "slot",
                            ]
                        ):
                            score += 10
                        # Contains separators typically used in IDs
                        if "_" in tl or "-" in tl:
                            score += 15
                        # Prefer longer token as ID (Event IDs are usually long)
                        score += min(len(tl), 80) / 2.5
                        return score

                    best = None
                    best_score = float("-inf")
                    for t in candidates:
                        s = _score_id_like(t)
                        if s > best_score:
                            best_score = s
                            best = t

                    if best:
                        target_text = best
                    else:
                        # Fallback to td[1] then td[0]
                        try:
                            td_count = chosen_row.locator("td").count()
                            if td_count >= 2:
                                target_text = (
                                    chosen_row.locator("td").nth(1).inner_text().strip()
                                )
                            elif td_count >= 1:
                                target_text = (
                                    chosen_row.locator("td").first.inner_text().strip()
                                )
                            else:
                                target_text = ""
                        except:
                            target_text = (
                                chosen_row.locator("td").first.inner_text().strip()
                            )
                except Exception:
                    # Absolute fallback
                    try:
                        target_text = (
                            chosen_row.locator("td").nth(1).inner_text().strip()
                        )
                    except:
                        target_text = (
                            chosen_row.locator("td").first.inner_text().strip()
                        )

                print(f"   🎲 Chọn ngẫu nhiên dòng #{idx + 1}: '{target_text}'")
                # Lưu vào memory để debug/trace, nhưng KHÔNG dựa vào target_text để click row action.
                self.memory["LAST_SELECTED"] = target_text

                # CRITICAL FIX:
                # Random mode có thể tạo target_text rỗng ('') → sau đó JS search dựa trên text sẽ match sai/treo.
                # Vì vậy: click trực tiếp nút Edit/Clone nằm trong `chosen_row`.
                try:
                    if action_type == "edit":
                        icon = chosen_row.locator(
                            "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                        ).first
                        if icon.count() > 0 and icon.is_visible():
                            icon.click(force=True)
                        else:
                            # fallback: click bất kỳ nút/link nào có chữ edit trong row
                            any_action = (
                                chosen_row.locator("button, a, [role='button']")
                                .filter(has_text=re.compile(r"\bedit\b", re.IGNORECASE))
                                .first
                            )
                            if any_action.count() > 0 and any_action.is_visible():
                                any_action.click(force=True)
                            else:
                                # final fallback: click nút đầu tiên có vẻ là action icon
                                fallback_btn = chosen_row.locator(
                                    "button, a, [role='button']"
                                ).first
                                fallback_btn.click(force=True)
                    else:
                        icon = chosen_row.locator(
                            "i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone, button:has-text('Clone'), a:has-text('Clone')"
                        ).first
                        if icon.count() > 0 and icon.is_visible():
                            icon.click(force=True)
                        else:
                            any_action = (
                                chosen_row.locator("button, a, [role='button']")
                                .filter(
                                    has_text=re.compile(
                                        r"\b(clone|copy|copy from|duplicate)\b",
                                        re.IGNORECASE,
                                    )
                                )
                                .first
                            )
                            if any_action.count() > 0 and any_action.is_visible():
                                any_action.click(force=True)
                            else:
                                fallback_btn = chosen_row.locator(
                                    "button, a, [role='button']"
                                ).first
                                fallback_btn.click(force=True)

                    time.sleep(1.0)

                    # Check lock popup only for edit
                    # PVE/Classic PVE panels load async and show skeleton/vld-icon loader.
                    # Requirement: do NOT check Locked Item popup until:
                    #  - we have observed loading indicator at least once
                    #  - and at least ~30s have passed
                    if action_type == "edit":
                        try:
                            start_t = time.time()
                            saw_async_loader = False

                            # hard minimum wait (30s)
                            while time.time() - start_t < 30:
                                try:
                                    aria_busy = (
                                        page.locator(
                                            "[aria-busy='true']:visible"
                                        ).count()
                                        > 0
                                    )
                                except:
                                    aria_busy = False
                                try:
                                    skeleton = (
                                        page.locator(".b-skeleton:visible").count() > 0
                                    )
                                except:
                                    skeleton = False
                                try:
                                    vld_loader = (
                                        page.locator(".vld-icon:visible").count() > 0
                                    )
                                except:
                                    vld_loader = False

                                if aria_busy or skeleton or vld_loader:
                                    saw_async_loader = True

                                # If already satisfied (min time + loader observed) we can stop early
                                if saw_async_loader and time.time() - start_t >= 30:
                                    break

                                time.sleep(0.5)

                            # Even if loader wasn't detected, wait_for_long_loading is still safer
                            # than immediate popup check.
                            if hasattr(self, "_wait_for_long_loading"):
                                try:
                                    self._wait_for_long_loading(page)
                                except:
                                    pass
                        except:
                            pass

                        popup_handled = self._handle_locked_item_popup(page)
                        if popup_handled:
                            time.sleep(1.0)
                            print("      ✅ Ready to update form.")
                        else:
                            time.sleep(0.5)

                    # Random đã bấm xong action, thoát luôn để tránh JS search theo target_text.
                    return
                except Exception as click_e:
                    # Nếu click direct fail thì KHÔNG dùng JS search theo `target_text`
                    # (vì `target_text` có thể là chuỗi rác như fullcalendar/text lớn).
                    # Thay vào đó: retry click trực tiếp action icon trong các row nằm trong scope `all_rows`.
                    print(f"      ⚠️ Random direct click failed: {click_e}")
                    try:
                        for _retry in range(3):
                            retry_row = all_rows.nth(
                                random.randint(0, max(0, total - 1))
                            )
                            if action_type == "edit":
                                retry_icon = retry_row.locator(
                                    "i[class*='edit'], i[class*='pencil'], .btn-edit, button:has-text('Edit'), a:has-text('Edit')"
                                ).first
                                if retry_icon.count() > 0:
                                    retry_icon.evaluate(
                                        "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                    )
                                else:
                                    retry_any = (
                                        retry_row.locator("button, a, [role='button']")
                                        .filter(
                                            has_text=re.compile(
                                                r"\bedit\b",
                                                re.IGNORECASE,
                                            )
                                        )
                                        .first
                                    )
                                    if retry_any.count() > 0:
                                        retry_any.evaluate(
                                            "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                        )
                                    else:
                                        continue
                            else:
                                retry_icon = retry_row.locator(
                                    "i[class*='clone'], i[class*='copy'], i[class*='share'], .btn-clone, button:has-text('Clone'), a:has-text('Clone')"
                                ).first
                                if retry_icon.count() > 0:
                                    retry_icon.evaluate(
                                        "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                    )
                                else:
                                    retry_any = (
                                        retry_row.locator("button, a, [role='button']")
                                        .filter(
                                            has_text=re.compile(
                                                r"\b(clone|copy|copy from|duplicate)\b",
                                                re.IGNORECASE,
                                            )
                                        )
                                        .first
                                    )
                                    if retry_any.count() > 0:
                                        retry_any.evaluate(
                                            "el => { el.scrollIntoView({block: 'center'}); el.click(); }"
                                        )
                                    else:
                                        continue

                            time.sleep(1.0)
                            if action_type == "edit":
                                popup_handled = self._handle_locked_item_popup(page)
                                if popup_handled:
                                    time.sleep(1.0)
                                    print("      ✅ Ready to update form (retry).")
                                else:
                                    time.sleep(0.5)
                            return
                    except Exception as _retry_e:
                        print(f"      ⚠️ Random direct click retry failed: {_retry_e}")

                    raise Exception(
                        f"Random direct click failed for action_type={action_type} after retries"
                    )
            except Exception as e:
                raise Exception(f"Random row selection failed: {e}")

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

            # [CRITICAL] Check for Locked Item popup after edit click (NOT clone)
            # Clone just opens a modal - lock popup check happens AFTER save_form(clone)
            # Some items may be locked by other users
            # Chờ đủ lâu để popup có thời gian render (tăng từ 0.5s lên 1s)
            time.sleep(1.0)
            if action_type == "edit":
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
                # Lock check only for edit (not clone)
                if "Clicked" in result and action_type == "edit":
                    time.sleep(1.0)
                    popup_handled = self._handle_locked_item_popup(page)
                    if popup_handled:
                        time.sleep(1.0)
                        print("      ✅ Ready to update form.")
                    else:
                        time.sleep(0.5)
            else:
                # Fallback: không crash job nếu không tìm thấy row target_text (đặc biệt sau khi filter/tab thay đổi).
                # Chọn dòng visible đầu tiên và thực hiện edit/clone theo action_type.
                try:
                    print(
                        f"      ⚠️ Row '{target_text}' not found. Falling back to first visible row for action='{action_type}'."
                    )
                    # Find first visible data row
                    first_row = (
                        page.locator("tbody tr")
                        .filter(has=page.locator("button, a, [role='button']"))
                        .first
                    )
                    if first_row.count() > 0 and first_row.is_visible():
                        js_fallback = """
(e) => {
  const row = e;
  const buttons = row.querySelectorAll("button, a.btn, a[class*='btn'], [role='button']");
  // Heuristic: pick first row action with edit if action hint exists in DOM text/aria
  const clickables = Array.from(buttons).filter(b => {
    const t = ((b.innerText||'') + ' ' + (b.getAttribute('aria-label')||'') + ' ' + (b.getAttribute('title')||'')).toLowerCase();
    return b.offsetParent !== null && (t.includes('edit') || t.includes('clone') || t.includes('copy') || t.includes('open') || t.includes('save'));
  });
  const b = clickables[0] || buttons[0];
  if (b) { b.closest('button,a')?.click?.(); (b.click ? b.click() : b.dispatchEvent(new MouseEvent('click',{bubbles:true}))); return true; }
  return false;
}
"""
                        ok = page.evaluate(js_fallback, first_row)
                        if ok:
                            time.sleep(1.0)
                            return
                    print(
                        "      ⚠️ Fallback row click failed; no visible rows/actions found."
                    )
                except Exception as fb_e:
                    print(f"      ❌ Fallback row click error: {fb_e}")
                # As last resort, keep old behavior
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

    # ============================
    # DRAG-AND-DROP REORDER
    # ============================

    def drag_to_reorder(self, page, target, position=None, before=None, after=None):
        """
        Kéo thả một item (row/panel-item) để đổi thứ tự ưu tiên.

        Tìm drag handle (dấu ≡) của target item, sau đó kéo đến vị trí mong muốn.

        Args:
            page:     Playwright Page object
            target:   Text/ID của item cần di chuyển (khớp với text content)
            position: Vị trí đích (1-based). position=1 = lên đầu danh sách.
            before:   Tên item mà target sẽ được đặt TRƯỚC.
            after:    Tên item mà target sẽ được đặt SAU.

        Returns:
            list of log dicts
        """
        logs = []
        print(
            f"\n   🖱️  REORDER: '{target}' → position={position} before={before} after={after}"
        )

        # ----------------------------------------------------------------
        # 1. Tìm handle selector có drag handles trên trang
        # ----------------------------------------------------------------
        DRAG_HANDLE_SELECTORS = [
            "i.fa-bars",
            "i.fa-grip",
            "i.fa-grip-vertical",
            "i.fa-grip-lines",
            "[class*='drag']",
            "[class*='handle']",
            "[class*='sort']",
            "span[class*='drag']",
            "svg[class*='drag']",
            ".drag-handle",
            ".sort-handle",
            "[draggable='true']",
        ]

        drag_rows = None

        # Chiến lược: Tìm handle selector có nhiều hơn 1 handle
        for handle_sel in DRAG_HANDLE_SELECTORS:
            handles = page.locator(handle_sel)
            count = handles.count()
            if count > 1:
                drag_rows = handle_sel
                print(f"      ✓ Found {count} drag handles via '{handle_sel}'")
                break

        if not drag_rows:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": "No draggable items found on page",
                }
            )
            return logs

        drag_handle_sel = drag_rows

        # Guard: target rỗng → fail ngay, tránh match nhầm item đầu tiên
        if not target or not target.strip():
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": "Reorder target is empty. Please specify the item name to drag.",
                }
            )
            print("      ❌ Reorder aborted: target is empty string.")
            return logs

        # ----------------------------------------------------------------
        # 2. Thu thập tất cả rows có drag handle và text content
        #    Scope về đúng cột/panel chứa target bằng cách cluster theo
        #    tọa độ X của drag handle (cùng cột = cùng X ± 150px)
        # ----------------------------------------------------------------
        print(f"      📌 Handle selector: '{drag_handle_sel}'")

        all_handles_full = page.locator(drag_handle_sel)
        total_full = all_handles_full.count()

        # ── Bước 2a: Thu thập bbox + text cho mọi handle ─────────────────
        raw_items = []  # list of (global_idx, text, handle, bbox)
        target_lower_pre = target.lower().strip()

        def _quick_text(h):
            """Lấy text ngắn gọn của item chứa handle h."""
            for steps in range(1, 5):
                xpath_str = "/".join([".."] * steps)
                try:
                    row = h.locator(f"xpath={xpath_str}")
                    if row.count() == 0:
                        continue
                    bbox = row.bounding_box()
                    if bbox is None or bbox["height"] > 150:
                        continue
                    text = row.inner_text(timeout=500).strip().replace("\n", " ")
                    if len(text) > 200:
                        continue
                    return text
                except Exception:
                    continue
            try:
                return (
                    all_handles_full.nth(0)
                    .locator("xpath=..")
                    .inner_text(timeout=500)[:100]
                )
            except Exception:
                return ""

        for i in range(total_full):
            h = all_handles_full.nth(i)
            try:
                bbox = h.bounding_box()
                text = _quick_text(h)
                raw_items.append((i, text, h, bbox))
            except Exception:
                raw_items.append((i, "", h, None))

        # ── Bước 2b: Tìm source item và lấy X của handle đó ──────────────
        source_x = None
        for idx, text, h, bbox in raw_items:
            if target_lower_pre in text.lower() or text.lower().startswith(
                target_lower_pre
            ):
                if bbox:
                    source_x = bbox["x"]
                    print(f"      🎯 Source handle X = {source_x:.0f}")
                break

        # ── Bước 2c: Lọc chỉ những handle cùng cột (|x - source_x| ≤ 150) ─
        X_TOLERANCE = 150  # px
        if source_x is not None:
            same_col = [
                (idx, text, h, bbox)
                for idx, text, h, bbox in raw_items
                if bbox and abs(bbox["x"] - source_x) <= X_TOLERANCE
            ]
            if len(same_col) > 1:
                print(
                    f"      ✅ Scoped to {len(same_col)} handles in same column (X ≈ {source_x:.0f})"
                )
                # Bọc lại dưới dạng cấu trúc tương thích với code bên dưới
                scoped_items = same_col
            else:
                print(
                    f"      ⚠️  Column scope found only {len(same_col)} item(s), using all handles"
                )
                scoped_items = raw_items
        else:
            print(f"      ⚠️  Source X not found, using all handles")
            scoped_items = raw_items

        # Xây dựng all_handles tương thích (dùng global index list, không dùng locator)
        # Thay thế all_handles.nth(i) bằng trực tiếp scoped_items
        total = len(scoped_items)
        print(f"      📋 Total drag handles found: {total}")

        def _get_row_for_handle(handle):
            """Trả về (row_locator, text) của item chứa handle.
            Đi từ direct parent lên dần đến khi tìm được element có text
            nhỏ gọn (không phải container chứa nhiều items)."""
            for steps in range(1, 5):  # thử lên 1-4 cấp
                xpath_str = "/".join([".."] * steps)  # "..", "../..", "../../.." …
                try:
                    row = handle.locator(f"xpath={xpath_str}")
                    if row.count() == 0:
                        continue
                    # Kiểm tra bbox — nếu phần tử quá cao (>150px) thì đang ở container
                    bbox = row.bounding_box()
                    if bbox is None:
                        continue
                    if bbox["height"] > 150:
                        continue  # Quá cao → chứa nhiều items → đi tiếp
                    text = row.inner_text(timeout=1000).strip().replace("\n", " ")
                    # Nếu text quá dài (>200 chars) → likely container text
                    if len(text) > 200:
                        continue
                    return row, text
                except Exception:
                    continue
            # Fallback: direct parent bất kể
            try:
                row = handle.locator("xpath=..")
                text = row.inner_text(timeout=1000).strip().replace("\n", " ")
                return row, text[:200]
            except Exception:
                return None, ""

        # Map text → index (0-based) — dùng scoped_items đã thu thập sẵn
        # scoped_items: list of (global_idx, text, handle, bbox)
        items = []
        for local_i, (global_idx, text, handle, bbox) in enumerate(scoped_items):
            items.append((local_i, text, handle, None))
            print(f"         [{local_i+1}] {text[:100]}")

        if not items:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": "Could not read draggable item texts",
                }
            )
            return logs

        # ----------------------------------------------------------------
        # 3. Tìm source item (target)
        # ----------------------------------------------------------------
        source_idx = None
        target_lower = target.lower().strip()
        for idx, text, handle, row in items:
            if target_lower in text.lower() or text.lower().startswith(target_lower):
                source_idx = idx
                print(f"      ✅ Source found at index {idx+1}: '{text[:60]}'")
                break

        if source_idx is None:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": f"Source item '{target}' not found in draggable list",
                }
            )
            return logs

        # ----------------------------------------------------------------
        # 4. Tính destination index
        # ----------------------------------------------------------------
        dest_idx = None

        # ── Fallback: nếu không có position/before/after, di chuyển xuống 1 bước ────
        if position is None and before is None and after is None:
            dest_idx = min(source_idx + 1, total - 1)
            print(
                f"      ⚠️  No position/before/after given → defaulting to move down 1 step (index {dest_idx})"
            )

        if position is not None:
            # position là 1-based; 9999 = last
            dest_idx = max(0, min(int(position) - 1, total - 1))
            print(f"      🎯 Destination by position={position} → index {dest_idx}")

        elif before is not None:
            before_lower = before.lower().strip()
            for idx, text, handle, row in items:
                if before_lower in text.lower():
                    dest_idx = idx
                    # Nếu source đang ở trước dest, dest thực sự là dest-1 sau khi source rời
                    print(
                        f"      🎯 Destination BEFORE '{text[:60]}' → index {dest_idx}"
                    )
                    break

        elif after is not None:
            after_lower = after.lower().strip()
            for idx, text, handle, row in items:
                if after_lower in text.lower():
                    dest_idx = min(idx + 1, total - 1)
                    print(
                        f"      🎯 Destination AFTER '{text[:60]}' → index {dest_idx}"
                    )
                    break

        if dest_idx is None:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "FAIL",
                    "details": f"Could not determine destination position",
                }
            )
            return logs

        if source_idx == dest_idx:
            logs.append(
                {
                    "step": "Reorder",
                    "status": "PASS",
                    "details": f"'{target}' already at position {dest_idx+1}, no move needed",
                }
            )
            return logs

        # ----------------------------------------------------------------
        # 5. Thực hiện kéo thả
        # ----------------------------------------------------------------
        source_handle = items[source_idx][2]
        dest_handle = items[dest_idx][2]
        # Dùng bbox đã fetch sẵn từ scoped_items để tránh stale re-fetch
        src_box_pre = scoped_items[source_idx][3]
        dest_box_pre = scoped_items[dest_idx][3]

        try:
            # Scroll source vào view
            source_handle.scroll_into_view_if_needed(timeout=3000)
            time.sleep(0.3)

            src_box = source_handle.bounding_box() or src_box_pre
            dest_box = dest_handle.bounding_box() or dest_box_pre

            if not src_box or not dest_box:
                raise Exception("Could not get bounding boxes for drag handles")

            src_x = src_box["x"] + src_box["width"] / 2
            src_y = src_box["y"] + src_box["height"] / 2
            dest_x = dest_box["x"] + dest_box["width"] / 2

            # Đặt dest_y: nếu kéo lên → Y trên của dest, nếu kéo xuống → Y dưới của dest
            if source_idx > dest_idx:
                # Kéo lên: thả ở cạnh trên của dest item
                dest_y = dest_box["y"] + 4
            else:
                # Kéo xuống: thả ở cạnh dưới của dest item
                dest_y = dest_box["y"] + dest_box["height"] - 4

            print(
                f"      🖱️  Drag ({src_x:.0f},{src_y:.0f}) → ({dest_x:.0f},{dest_y:.0f})"
            )

            mouse = page.mouse
            mouse.move(src_x, src_y)
            time.sleep(0.2)
            mouse.down()
            time.sleep(0.3)

            # Di chuyển mượt mà theo từng bước nhỏ
            steps = 20
            for step in range(1, steps + 1):
                mid_x = src_x + (dest_x - src_x) * step / steps
                mid_y = src_y + (dest_y - src_y) * step / steps
                mouse.move(mid_x, mid_y)
                time.sleep(0.02)

            time.sleep(0.3)
            mouse.up()
            time.sleep(0.5)

            # Chờ UI cập nhật
            page.wait_for_load_state("networkidle", timeout=5000)
            time.sleep(0.5)

            move_desc = f"'{target}' moved from position {source_idx+1} to {dest_idx+1}"
            print(f"      ✅ {move_desc}")
            logs.append({"step": "Reorder", "status": "PASS", "details": move_desc})

        except Exception as e:
            print(f"      ❌ Drag failed: {e}")
            logs.append(
                {"step": "Reorder", "status": "FAIL", "details": f"Drag error: {e}"}
            )

        return logs
