# automation_modules/form_handler.py
import time
import re
import random
from playwright.sync_api import Page


class FormHandlerMixin:
    """Chứa logic tương tác với Form, Checkbox, Row"""

    def _safe_check(self, locator):
        try:
            # 1. Scroll dòng ra GIỮA MÀN HÌNH (Tránh bị Sticky Header che)
            locator.evaluate(
                "el => el.scrollIntoView({block: 'center', inline: 'nearest'})"
            )
            time.sleep(0.2)

            if locator.is_checked():
                return True

            # 2. Click thông thường
            try:
                locator.check(force=True, timeout=1000)
            except:
                pass
            if locator.is_checked():
                return True

            # 3. Click vào ô cha (td) hoặc label nếu click input không ăn
            # (Đôi khi input bị ẩn, phải click vào cell)
            locator.evaluate(
                "el => { el.click(); if(!el.checked) el.checked=true; el.dispatchEvent(new Event('change', {bubbles: true})); }"
            )
            time.sleep(0.1)

            return locator.is_checked()
        except:
            return False

    def handle_checkbox(self, page, target, value):
        logs = []
        try:
            if not self.wait_for_table_data(page):
                return [
                    {"step": "Checkbox", "status": "FAIL", "details": "Table Empty"}
                ]

            # Lọc bỏ Header, chỉ lấy dòng dữ liệu
            all_rows = page.locator("tbody tr").filter(has=page.locator("td"))
            total_rows = all_rows.count()

            print(f"   📊 Tìm thấy {total_rows} dòng dữ liệu khả dụng.")

            if "random" in value.lower():
                num_to_select = 1
                match = re.search(r"random.*?(\d+)", value.lower())
                if match:
                    num_to_select = int(match.group(1))

                num_to_select = min(num_to_select, total_rows)

                selected_ids = []
                used_indices = set()  # Theo dõi các dòng đã thử

                # --- VÒNG LẶP KIÊN TRÌ (WHILE LOOP) ---
                # Chạy cho đến khi tick đủ số lượng yêu cầu
                attempts = 0
                max_attempts = num_to_select * 3  # Cho phép thử gấp 3 lần số cần thiết

                while len(selected_ids) < num_to_select and attempts < max_attempts:
                    attempts += 1

                    # 1. Chọn 1 index ngẫu nhiên chưa từng dùng
                    idx = random.randint(0, total_rows - 1)
                    if idx in used_indices:
                        continue  # Nếu trùng thì quay lại chọn cái khác

                    used_indices.add(idx)  # Đánh dấu đã dùng

                    row = all_rows.nth(idx)
                    chk = row.locator("input[type='checkbox']").first

                    # 2. Thử Tick
                    if self._safe_check(chk):
                        # Thành công -> Lưu ID
                        try:
                            cell_text = row.locator("td").nth(1).inner_text().strip()
                            if not cell_text:
                                cell_text = (
                                    row.locator("td").nth(2).inner_text().strip()
                                )

                            self.memory["LAST_SELECTED"] = cell_text
                            if "SELECTED_IDS" not in self.memory:
                                self.memory["SELECTED_IDS"] = []
                            self.memory["SELECTED_IDS"].append(cell_text)

                            selected_ids.append(cell_text)
                            print(f"   ✅ Đã tick dòng {idx+1}: {cell_text}")
                        except:
                            pass
                    else:
                        print(
                            f"   ⚠️ Lỗi tick dòng {idx+1}. Robot sẽ tự chọn dòng khác bù vào..."
                        )

                    # Nghỉ xíu để Web load
                    time.sleep(0.2)

                if len(selected_ids) < num_to_select:
                    print(
                        f"   ⚠️ Đã cố hết sức nhưng chỉ tick được {len(selected_ids)}/{num_to_select}."
                    )
                else:
                    print(f"   🎉 Hoàn thành: Đã chọn đủ {len(selected_ids)} dòng.")

                logs.append(
                    {
                        "step": "Checkbox",
                        "status": "PASS",
                        "details": f"Selected: {selected_ids}",
                    }
                )

            elif "all" in value.lower():
                h = page.locator("thead input[type='checkbox']").first
                if h.is_visible():
                    self._safe_check(h)
                    time.sleep(1)  # Chờ select all tác dụng
                else:
                    # Fallback tick từng cái
                    for i in range(min(total_rows, 20)):
                        self._safe_check(
                            all_rows.nth(i).locator("input[type='checkbox']").first
                        )
                        time.sleep(0.1)
                logs.append(
                    {"step": "Checkbox", "status": "PASS", "details": "Select All"}
                )
            else:
                # Chọn đích danh (Target)
                target_regex = self._safe_compile(target)
                target_row = all_rows.filter(has_text=target_regex).first

                if target_row.is_visible():
                    chk = target_row.locator("input[type='checkbox']").first
                    self._safe_check(chk)
                    logs.append(
                        {"step": "Checkbox", "status": "PASS", "details": target}
                    )
                else:
                    logs.append(
                        {
                            "step": "Checkbox",
                            "status": "FAIL",
                            "details": f"Not found: {target}",
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
        elif "Row Not Found" in result:
            if self._auto_filter_data(page, target_text):
                page.evaluate(
                    js_script, {"text": str(target_text), "action": action_type}
                )
            else:
                raise Exception(f"Không tìm thấy dòng '{target_text}'")

    # ============================
    # 4. SMART FORM FILLER (FULL FEATURES)
    # ============================
    def _smart_update_form(self, page, data_dict, strict_mode=False):
        success_count = 0
        print(f"   📝 Updating Form (Strict={strict_mode}): {data_dict}")
        self._handle_locked_item_popup(page)

        if "Tab" in data_dict:
            tab_name = data_dict.pop("Tab")
            self._switch_to_tab(page, tab_name)

        # 1. SCOPE
        try:
            modal = page.locator(
                ".modal.show .modal-content, .modal-content:visible"
            ).last
            if not modal.is_visible():
                modal = page
                is_modal = False
            else:
                is_modal = True
        except:
            modal = page
            is_modal = False

        # 2. TAB SWITCHING (NÂNG CẤP: Tìm Tab Sidebar chính xác hơn)
        if "Tab" in data_dict:
            t = data_dict.pop("Tab")
            print(f"      👉 Switching to Tab: '{t}'")

            # Tìm tất cả phần tử có chứa text tên Tab
            # Tìm rộng: a, div, span, li, button
            potential_tabs = (
                page.locator(f"a, div, span, li, button")
                .filter(has_text=re.compile(f"^{re.escape(t)}$", re.IGNORECASE))
                .all()
            )

            target_tab = None
            for tab in potential_tabs:
                if tab.is_visible():
                    try:
                        box = tab.bounding_box()
                        if box:
                            # Sidebar thường nằm bên trái (x < 300)
                            # Modal tab nằm phía trên
                            if box["x"] < 300 or box["y"] < 250:
                                # Kiểm tra kích thước để không click nhầm vào container lớn
                                if box["width"] < 300 and box["height"] < 100:
                                    target_tab = tab
                                    break
                    except:
                        pass

            # Fallback: Tìm chứa text (Contains) nếu tìm chính xác thất bại
            if not target_tab:
                potential_tabs = (
                    page.locator(f".sidebar a, .nav-link, li").filter(has_text=t).all()
                )
                for tab in potential_tabs:
                    if tab.is_visible():
                        target_tab = tab
                        break

            if target_tab:
                # Kiểm tra active
                cls = target_tab.get_attribute("class") or ""
                # Nếu chưa active thì mới click
                if (
                    "active" not in cls
                    and "selected" not in cls
                    and "current" not in cls
                ):
                    target_tab.click()
                    time.sleep(1.5)  # Chờ load nội dung
            else:
                print(f"      ⚠️ Warning: Could not find tab '{t}'")

        # 3. LOOP DATA
        for key, value in data_dict.items():
            print(f"      👉 Xử lý '{key}' -> '{value}'")
            target = self._find_input_element(page, key)
            if target:
                self._fill_element_smartly(page, target, value)
            else:
                print(f"      ❌ Give up: Cannot find field '{key}'")

            target_input = None

            # --- RETRY LOOP (Thử 3 lần, mỗi lần chờ 1s để bảng render) ---
            for attempt in range(3):
                if target_input:
                    break
                if attempt > 0:
                    time.sleep(1.0)
                # --- A. RADIO BUTTON SCAN ---
                try:
                    radio_label = (
                        modal.locator("label")
                        .filter(
                            has_text=re.compile(re.escape(str(value)), re.IGNORECASE)
                        )
                        .first
                    )
                    if radio_label.is_visible():
                        if modal.locator("input[type='radio']").count() > 0:
                            print(f"         ✅ Found Radio Label: '{value}'")
                            radio_label.click()
                            time.sleep(0.5)
                            success_count += 1
                            continue
                except:
                    pass

                # --- B. MAPPING ---
                k_map = {
                    "id": ["ffID", "New Event ID", "New ID", "BagID", "Gacha ID"],
                    "gate": ["ff_gate", "Gate", "Condition"],
                    "currency": ["Currency", "Type", "Cost Type"],
                    "cost": ["HC Cost", "Price", "Amount"],  # Map thêm cho Cost
                    "stock": ["Initial Stock", "Limit", "Count"],  # Map thêm cho Stock
                }
                cands = [key]
                for k, v in k_map.items():
                    if k in key.lower():
                        cands.extend(v)
                if "id" in key.lower() and "ffID" not in cands:
                    cands.insert(0, "ffID")

                # --- C. CHIẾN THUẬT TÌM KIẾM ---

                # C0. CLASS NAME MATCH (Ưu tiên SỐ 1 cho Quantity/Weight)
                if not target_input:
                    try:
                        cls_key = key.lower().strip()
                        # Tìm input có class chứa từ khóa (vd: class="quantity form-control")
                        # Dùng selector input[class*='...'] để bắt linh hoạt
                        selector = f"input[class*='{cls_key}']"
                        found_els = modal.locator(selector).all()
                        visible_els = [e for e in found_els if e.is_visible()]

                        if visible_els:
                            # Lấy phần tử cuối cùng (thường là dòng đang edit)
                            target_input = visible_els[-1]
                            print(
                                f"         ✅ Found Input via Class Match: '{selector}'"
                            )
                    except:
                        pass

                # C1. TABLE COLUMN SEARCH
                if not target_input:
                    for term in cands:
                        headers = modal.locator("thead th, table th").all()
                        col_index = -1
                        for idx, th in enumerate(headers):
                            if not th.is_visible():
                                continue
                            if term.lower() in th.inner_text().strip().lower():
                                col_index = idx
                                break

                        if col_index != -1:
                            rows = modal.locator("tbody tr").all()
                            visible_rows = [r for r in rows if r.is_visible()]
                            if visible_rows:
                                target_row = visible_rows[-1]
                                cells = target_row.locator("td").all()
                                if col_index < len(cells):
                                    cell_inp = (
                                        cells[col_index].locator("input, select").first
                                    )
                                    if cell_inp.is_visible():
                                        target_input = cell_inp
                                        print(
                                            f"         ✅ Found Input in Table Column '{term}'"
                                        )
                                        break
                    if target_input:
                        break

                # C2. Exact ID Match
                if not target_input:
                    for term in cands:
                        if " " not in term:
                            el = modal.locator(f"#{term}").first
                            if el.count() and el.is_visible():
                                target_input = el
                                break

                # C3. Label Match
                if not target_input:
                    for term in cands:
                        reg = re.compile(re.escape(term), re.IGNORECASE)
                        if is_modal:
                            labels = (
                                modal.locator("label, span, h5, h4, strong")
                                .filter(has_text=reg)
                                .all()
                            )
                        else:
                            labels = (
                                modal.locator("label, span, h5, th, strong")
                                .filter(has_text=reg)
                                .all()
                            )

                        for lbl in labels:
                            if not lbl.is_visible():
                                continue
                            try:
                                for_attr = lbl.get_attribute("for")
                                if for_attr:
                                    inp = modal.locator(f"#{for_attr}").first
                                    if inp.is_visible():
                                        target_input = inp
                                        break
                            except:
                                pass
                            if target_input:
                                break

                            candidates = lbl.locator(
                                "xpath=following::input | following::select | following::span[contains(@class,'select2-container')]"
                            ).all()
                            for cand in candidates[:3]:
                                if (
                                    not cand.is_visible()
                                    and cand.evaluate("e=>e.tagName.toLowerCase()")
                                    != "select"
                                ):
                                    continue
                                cand_type = cand.get_attribute("type")
                                if cand_type == "radio":
                                    if "value" in key.lower():
                                        continue
                                    if (
                                        len(str(value)) > 15
                                        and " " not in str(value).strip()
                                    ):
                                        continue
                                if cand_type == "checkbox" and str(
                                    value
                                ).lower() not in ["true", "false", "on", "off"]:
                                    continue
                                target_input = cand
                                break
                            if target_input:
                                break
                        if target_input:
                            break

                # C4. Attribute/Placeholder
                if not target_input:
                    for term in cands:
                        els = modal.locator(
                            "input:visible, select, textarea:visible"
                        ).all()
                        for el in els:
                            n = (el.get_attribute("name") or "").lower()
                            i = (el.get_attribute("id") or "").lower()
                            if term.lower() in n or term.lower() in i:
                                target_input = el
                                break
                        if not target_input:
                            ph = modal.get_by_placeholder(
                                re.compile(term, re.IGNORECASE)
                            ).first
                            if ph.is_visible():
                                target_input = ph
                        if target_input:
                            break
            # END RETRY LOOP
            if target_input == "RadioDone":
                continue

            # C5. Fallback Input cuối (BỊ CHẶN BỞI STRICT MODE)
            if not target_input:
                if strict_mode:
                    print(f"      🚫 Strict Mode: Skipping fallback for '{key}'")
                    continue  # Bỏ qua ngay, không đoán mò

                # Chỉ chạy nếu KHÔNG phải strict mode
                if key.lower() in ["quantity", "weight", "cost", "stock"]:
                    candidates = modal.locator(
                        "input[type='number']:visible, input[type='text']:visible"
                    ).all()
                    valid_candidates = []
                    for c in candidates:
                        try:
                            cls = (c.get_attribute("class") or "").lower()
                            id_attr = (c.get_attribute("id") or "").lower()
                            if any(
                                x in cls
                                for x in ["search", "chosen", "select2", "hidden"]
                            ):
                                continue
                            if any(x in id_attr for x in ["search", "filter"]):
                                continue
                            valid_candidates.append(c)
                        except:
                            pass

                    if valid_candidates:
                        print(
                            f"         ⚠️ Fallback: Picking valid candidate from {len(valid_candidates)} inputs"
                        )
                        target_input = valid_candidates[-1]

            if not target_input:
                print(f"      ❌ Give up: {key}")
                continue

            # --- D. ACTION ---
            try:
                cls = target_input.get_attribute("class") or ""
                tag = target_input.evaluate("e=>e.tagName.toLowerCase()")

                # FIX SELECT2
                if tag == "select":
                    if (
                        not target_input.is_visible()
                        or "select2-hidden-accessible" in cls
                    ):
                        s2 = target_input.locator(
                            "xpath=following-sibling::span[contains(@class,'select2')]"
                        ).first
                        if s2.is_visible():
                            target_input = s2
                            cls = "select2-container"
                        else:
                            try:
                                sel_id = target_input.get_attribute("id")
                                if sel_id:
                                    s2_alt = page.locator(
                                        f".select2-selection[aria-labelledby*='{sel_id}']"
                                    ).first
                                    if s2_alt.is_visible():
                                        target_input = s2_alt
                                        cls = "select2-container"
                            except:
                                pass

                is_s2 = (
                    "select2" in cls
                    or "selection" in cls
                    or ("gate" in key.lower() and tag != "select")
                )
                typ = target_input.get_attribute("type")

                # Select2
                if is_s2 and typ != "checkbox" and typ != "radio":
                    print("         ↳ Action: Select2")
                    target_input.click()
                    time.sleep(0.5)
                    box = page.locator(
                        ".select2-container--open input.select2-search__field"
                    ).last
                    if box.is_visible():
                        box.fill(str(value))
                        time.sleep(1.0)
                        opt = page.locator(
                            ".select2-results__option--highlighted"
                        ).first
                        if not opt.is_visible():
                            opt = page.locator(
                                f".select2-results__option:has-text('{value}')"
                            ).first
                        if opt.is_visible():
                            opt.click()
                        else:
                            page.keyboard.press("Enter")
                    else:
                        page.keyboard.type(str(value))
                        page.keyboard.press("Enter")

                # Radio
                elif typ == "radio":
                    print("         ↳ Action: Radio Click")
                    target_input.click()

                # Text / Number
                else:
                    print(f"         ↳ Action: Fill Text '{value}'")
                    target_input.click(force=True)
                    target_input.fill("")
                    target_input.fill(str(value))
                    # Trigger change event để đảm bảo web nhận giá trị
                    target_input.evaluate(
                        "e => e.dispatchEvent(new Event('change', {bubbles: true}))"
                    )
                    # Dùng TAB để chuyển sang ô kế tiếp (như Weight) thay vì Submit Form
                    page.keyboard.press("Tab")
                success_count += 1
            except Exception as e:
                print(f"         ❌ Action Error: {e}")

        return success_count

    # ============================
    # 6. HELPERS
    # ============================
    def _save_form(self, page, mode="continue"):
        """
        Hợp nhất:
        1. Ưu tiên tuyệt đối attribute 'data-continue' (Fix lỗi hiện tại).
        2. Fallback về logic tìm text linh hoạt của bạn (Create/Clone/Update...).
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
            # 1. Xác định phạm vi (Scope) - Giữ logic của bạn
            scope = page
            # Nếu có modal đang mở, chỉ tìm trong modal
            if page.locator(".modal.show").count() > 0:
                scope = page.locator(".modal.show").last

            target_btn = None

            # =========================================================
            # CHIẾN THUẬT 1: TÌM CHÍNH XÁC "SAVE & CONTINUE" (ƯU TIÊN SỐ 1)
            # =========================================================
            if mode == "continue":
                # Tìm bằng "chìa khóa vàng" data-continue='1'
                btn = scope.locator(
                    "button[data-continue='1'], input[data-continue='1']"
                ).last
                if btn.is_visible():
                    print("      🎯 Found 'Save & Continue' via [data-continue='1']")
                    target_btn = btn
                else:
                    # Fallback Regex: Chấp nhận icon hoặc khoảng trắng lạ
                    # r"Save.*Continue" tìm chữ Save rồi đến Continue bất kể ở giữa là gì
                    print("      ⚠️ Fallback: Tìm text 'Save...Continue'")
                    regex = re.compile(r"Save.*Continue", re.IGNORECASE)
                    target_btn = scope.locator("button, a").filter(has_text=regex).last

            # =========================================================
            # CHIẾN THUẬT 2: TÌM CÁC NÚT KHÁC (SAVE, CLONE, CREATE...)
            # =========================================================
            else:  # mode == "save" hoặc mặc định
                # 2.1. Tìm nút Save chuẩn (Tránh nhầm nút Continue)
                # Tìm nút .btn-save hoặc nút có chữ Save nhưng KHÔNG có chữ Continue
                save_regex = re.compile(r"Save(?!.*Continue)", re.IGNORECASE)

                # Ưu tiên class .btn-save chuẩn của Brick
                btn_class = scope.locator(".btn-save:not([data-continue='1'])").last

                if btn_class.is_visible():
                    target_btn = btn_class
                elif (
                    scope.locator("button")
                    .filter(has_text=save_regex)
                    .last.is_visible()
                ):
                    target_btn = (
                        scope.locator("button").filter(has_text=save_regex).last
                    )

                # 2.2. Nếu không phải Save, tìm các hành động khác (Logic cũ của bạn)
                if not target_btn or not target_btn.is_visible():
                    target_texts = [
                        "Save All",
                        "Create",
                        "Update",
                        "Submit",
                        "Duplicate",
                        "Clone",
                        "Confirm",
                        "Yes",
                        "Acquire Lock",
                    ]
                    for text in target_texts:
                        # Dùng regex biên \b để tìm chính xác từ (tránh tìm nhầm)
                        # VD: Tìm "Create" sẽ không bắt nhầm "Created By"
                        btn = (
                            scope.locator(f"button, a.btn, input[type='submit']")
                            .filter(has_text=re.compile(re.escape(text), re.IGNORECASE))
                            .last
                        )
                        if btn.is_visible():
                            print(f"      👉 Found generic button: '{text}'")
                            target_btn = btn
                            break

            # =========================================================
            # CHIẾN THUẬT 3: FALLBACK THEO CLASS (CŨNG CỦA BẠN)
            # =========================================================
            if not target_btn or not target_btn.is_visible():
                class_selectors = [
                    "button.btn-primary",
                    "button.btn-success",
                    "input[type='submit']",
                ]
                for sel in class_selectors:
                    btn = scope.locator(sel).last
                    if btn.is_visible():
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

    def _handle_locked_item_popup(self, page):
        try:
            # Tìm popup có chứa text "locked this item"
            popup = (
                page.locator(".modal-content, .swal2-popup")
                .filter(has_text="locked this item")
                .last
            )

            if popup.is_visible(timeout=2000):  # Check nhanh 2s
                print("      🔒 Detected Locked Item Popup.")
                # Tìm nút Acquire Lock
                acquire_btn = (
                    popup.locator("button, a")
                    .filter(has_text=re.compile("Acquire Lock|Unlock", re.IGNORECASE))
                    .first
                )

                if acquire_btn.is_visible():
                    print("      🔓 Clicking 'Acquire Lock'...")
                    acquire_btn.click()
                    time.sleep(1.5)  # Chờ reload
                else:
                    print("      ⚠️ Locked but no Acquire button found!")
        except:
            pass

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
        s = time.time()
        while time.time() - s < timeout:
            if page.locator("tbody tr").count() > 0:
                return True
            time.sleep(0.5)
        return False

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

    def _find_input_element(self, page, key):
        """Tìm Input thông minh với logic ưu tiên ID và Clean Key"""

        # 1. HARDCODE CHO TRƯỜNG HỢP ĐẶC BIỆT (Dựa trên ảnh HTML)
        key_lower = key.lower()

        # Case: Paid-Only Loot -> ID #category (trong div#premium-loot)
        if "paid-only" in key_lower or "paid only" in key_lower:
            print(f"         🔍 Detect Special Key '{key}' -> Target ID #category")
            # Tìm input có id="category" (Input gốc của toggle)
            tgl = page.locator("#category").first
            if tgl.count() > 0:
                return tgl
            # Fallback: Tìm qua container cha
            tgl_container = page.locator("#premium-loot input").first
            if tgl_container.count() > 0:
                return tgl_container

        # Case: Gate -> ID #gate
        if key_lower == "gate":
            gate = page.locator("#gate").first
            if gate.count() > 0:
                return gate

        # 2. TÌM BẰNG TỪ KHÓA ĐÃ LÀM SẠCH
        # "Toggle Paid-Only Loot" -> "paid-only loot"
        clean_key = self._clean_key(key)
        if not clean_key:
            clean_key = key  # Nếu xóa hết thì giữ nguyên

        lbl_regex = re.compile(re.escape(clean_key), re.IGNORECASE)

        # Tìm Label chứa text (Partial match)
        labels = (
            page.locator("label.control-label, label").filter(has_text=lbl_regex).all()
        )
        visible_labels = [l for l in labels if l.is_visible()]

        for lbl in visible_labels:
            # Tìm Parent Group
            group = lbl.locator(
                "xpath=ancestor::div[contains(@class, 'control-group')][1]"
            )
            if group.count() > 0:
                # A. Toggle
                tgl = group.locator("input.tgl, input.tgl-ios").first
                if tgl.count() > 0:
                    return tgl
                # B. Select2
                sel2 = group.locator("select.select2-hidden-accessible").first
                if sel2.count() > 0:
                    return sel2
                # C. Input thường
                inp = group.locator(
                    "input:not([type='hidden']), select, textarea"
                ).first
                if inp.is_visible():
                    return inp

        # 3. FALLBACK ID/SIBLING
        if visible_labels:
            target_lbl = visible_labels[-1]
            for_attr = target_lbl.get_attribute("for")
            if for_attr:
                by_id = page.locator(f"#{for_attr}").first
                if by_id.count() > 0:
                    return by_id

        return None

    def _fill_element_smartly(self, page, element, value):
        """Điền dữ liệu (Clean Log, No Double Select2)"""
        try:
            # Lấy thông tin element an toàn
            info = element.evaluate(
                """e => ({
                cls: e.className || '',
                tag: e.tagName.toLowerCase(),
                type: e.getAttribute('type'),
                id: e.id,
                visible: (e.offsetWidth > 0 && e.offsetHeight > 0)
            })"""
            )

            cls = info["cls"]
            tag = info["tag"]
            input_id = info["id"]

            # --- CASE 1: SELECT2 ---
            # Chỉ xử lý nếu class chứa select2
            if "select2" in cls:
                print(f"         ↳ Action: Select2 '{value}'")  # Log 1 lần duy nhất

                # Nếu là thẻ Select ẩn -> Click Container kế bên
                if "select2-hidden-accessible" in cls or not info["visible"]:
                    container = element.locator(
                        "xpath=following-sibling::span[contains(@class, 'select2-container')]"
                    ).first
                    if container.is_visible():
                        container.click()
                    else:
                        # Fallback JS click nếu container chưa load kịp
                        page.evaluate(
                            "e => { var s = e.nextElementSibling; if(s && s.classList.contains('select2')) s.click(); }",
                            element,
                        )
                else:
                    # Nếu là container -> Click trực tiếp
                    element.click()

                # Điền search
                time.sleep(0.5)
                search_box = page.locator(
                    ".select2-search__field, input.select2-input"
                ).last
                if search_box.is_visible():
                    search_box.fill(str(value))
                    time.sleep(1.0)
                    page.keyboard.press("Enter")
                return  # Return ngay để không chạy xuống dưới

            # --- CASE 2: TOGGLE / CHECKBOX ---
            is_tgl = "tgl" in cls or "toggle" in cls
            is_checkbox = tag == "input" and info["type"] == "checkbox"

            if is_tgl or is_checkbox:
                print(f"         ↳ Action: Toggle '{value}'")
                want_checked = str(value).lower() in ["true", "on", "yes", "1"]
                is_currently_checked = element.evaluate("e => e.checked")

                if is_currently_checked != want_checked:
                    # Nếu là TGL-IOS (Input ẩn -> Click Label)
                    if "tgl" in cls and input_id:
                        # Tìm label theo for attribute
                        btn_label = page.locator(f"label.tgl-btn[for='{input_id}']")
                        if btn_label.is_visible():
                            btn_label.click()
                            return

                    # Checkbox thường
                    if info["visible"]:
                        element.click(force=True)
                    else:
                        element.evaluate("e => e.click()")
                return

            # --- CASE 3: INPUT THƯỜNG ---
            if not info["visible"]:
                # Skip log warning cho select2 hidden (đã xử lý ở trên)
                if "select2" not in cls:
                    print(f"         ⚠️ Element hidden, cannot fill.")
                return

            print(f"         ↳ Action: Fill Text '{value}'")
            element.click(force=True)
            element.fill("")
            element.fill(str(value))
            element.evaluate(
                "e => e.dispatchEvent(new Event('change', {bubbles: true}))"
            )
            element.press("Tab")

        except Exception as e:
            print(f"         ⚠️ Fill Error: {e}")

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
