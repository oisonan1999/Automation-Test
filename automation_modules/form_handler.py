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

    def handle_checkbox(self, page, target_col, value):
        logs = []
        try:
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

                    if self._safe_check(chk):
                        try:
                            # Lấy ID/Text để lưu vào Memory
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
                        print(f"   ⚠️ Lỗi tick dòng {idx+1}. Thử dòng khác...")
                    time.sleep(0.2)

                if len(selected_ids) < num_to_select:
                    print(
                        f"   ⚠️ Chỉ chọn được {len(selected_ids)}/{num_to_select} dòng."
                    )

                logs.append(
                    {
                        "step": "Checkbox",
                        "status": "PASS",
                        "details": f"Random: {selected_ids}",
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
    def _smart_update_form(self, page, data):
        """
        Hàm chính: Duyệt qua data và điền từng trường.
        """
        print(f"      📝 Updating Form Data: {data}")

        # Chờ form ổn định
        try:
            page.wait_for_load_state("domcontentloaded")
            time.sleep(0.5)
        except:
            pass

        for label, value in data.items():
            print(f"         ↳ Processing '{label}' -> '{value}'")
            try:
                # Bước 1: Tìm Element
                target_element = self._find_input_element(page, label)

                if target_element:
                    # Bước 2: Điền dữ liệu (Logic thông minh nằm ở đây)
                    success = self._fill_element_smartly(page, target_element, value)
                    if not success:
                        print(f"         ❌ Action Failed for '{label}'")
                else:
                    print(f"         ❌ Give up: Cannot find field '{label}'")
            except Exception as e:
                print(f"         ❌ Error filling '{label}': {e}")

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

    def _find_input_element(self, page, label_text):
        safe_label = re.compile(re.escape(label_text), re.IGNORECASE)
        candidates = (
            page.locator("label, span, h5, th, strong, div, b")
            .filter(has_text=safe_label)
            .all()
        )
        visible_candidates = [c for c in candidates if c.is_visible()]
        visible_candidates.sort(
            key=lambda x: (
                0 if x.evaluate("el => el.tagName") == "LABEL" else 1,
                len(x.inner_text()),
            )
        )

        for label_el in visible_candidates:
            # A. Check 'for' attribute
            for_attr = label_el.get_attribute("for")
            if for_attr:
                target = page.locator(f"#{for_attr}").first
                if target.count() > 0:
                    # Nếu target bị ẩn (Select), thử tìm wrapper ngay lập tức
                    if (
                        not target.is_visible()
                        and target.evaluate("el => el.tagName") == "SELECT"
                    ):
                        wrapper = self._find_custom_dropdown_wrapper(target)
                        if wrapper:
                            return wrapper
                    return target

            # B. Check Input lồng bên trong
            nested = label_el.locator("input, select, textarea").first
            if nested.count() > 0:
                if (
                    not nested.is_visible()
                    and nested.evaluate("el => el.tagName") == "SELECT"
                ):
                    wrapper = self._find_custom_dropdown_wrapper(nested)
                    if wrapper:
                        return wrapper
                return nested

            # C. Check Sibling (Input/Select2/Chosen nằm ngay sau Label)
            # [FIX]: Thêm .chosen-container vào danh sách tìm kiếm
            sibling = label_el.locator(
                "xpath=following::input | following::select | following::textarea | following::span[contains(@class,'select2-container')] | following::div[contains(@class,'chosen-container')]"
            ).first

            if sibling.count() > 0:
                # Nếu tìm thấy wrapper hiển thị ngay -> Trả về
                if sibling.is_visible():
                    return sibling

                # Nếu tìm thấy select ẩn -> Tìm wrapper của nó
                if (
                    not sibling.is_visible()
                    and sibling.evaluate("el => el.tagName") == "SELECT"
                ):
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

        return None

    def _find_custom_dropdown_wrapper(self, hidden_select):
        """Tìm thẻ bao (Wrapper) hiển thị của Select2 hoặc Chosen.js"""
        try:
            # 1. Tìm theo ID Biến thể (Quan trọng cho Chosen)
            # ID gốc: clone-gate -> Chosen ID: clone_gate_chosen (dấu - thành _)
            sel_id = hidden_select.get_attribute("id")
            if sel_id:
                # Case A: ID gốc + _chosen (Chuẩn Chosen)
                chosen_id = f"#{sel_id}_chosen"
                if hidden_select.page.locator(chosen_id).is_visible():
                    return hidden_select.page.locator(chosen_id)

                # Case B: Thay '-' thành '_' rồi + _chosen (Fix lỗi ID của bạn)
                alt_id = sel_id.replace("-", "_") + "_chosen"
                if hidden_select.page.locator(f"#{alt_id}").is_visible():
                    return hidden_select.page.locator(f"#{alt_id}")

                # Case C: Select2 container ID
                s2_id = f"#select2-{sel_id}-container"
                if hidden_select.page.locator(s2_id).is_visible():
                    # Trả về cha của container (là .select2-container)
                    return (
                        hidden_select.page.locator(s2_id)
                        .locator(
                            "xpath=ancestor::span[contains(@class,'select2-container')]"
                        )
                        .first
                    )

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

        except:
            pass
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

            # --- 3. HIDDEN SELECT (Chosen/Select2) ---
            is_hidden_select = tag_name == "select" and not is_visible
            is_lib = "select2" in class_attr or "chosen" in class_attr

            if is_hidden_select or is_lib:
                print(f"         🕵️ Xử lý Dropdown nâng cao cho '{value}'...")
                wrapper = self._find_custom_dropdown_wrapper(element)

                if wrapper:
                    w_class = wrapper.get_attribute("class") or ""
                    lib_type = "chosen" if "chosen" in w_class else "select2"
                    return self._handle_js_dropdown(page, wrapper, value, lib_type)

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

            if tag_name == "select":
                try:
                    element.select_option(label=str(value))
                except:
                    element.select_option(value=str(value))
                print(f"         ✅ Selected option '{value}'")
            else:
                element.fill("")
                element.fill(str(value))

            # [QUAN TRỌNG]: Ép buộc lưu dữ liệu bằng cách Tab ra ngoài
            element.press("Tab")
            # Đề phòng Tab không ăn, gọi thêm blur
            try:
                element.blur()
            except:
                pass

            print(f"         ✅ Filled & Saved: '{value}'")
            return True

        except Exception as e:
            print(f"         ❌ Lỗi thao tác: {e}")
            return False

    def _handle_js_dropdown(self, page, container, value, lib_type="chosen"):
        try:
            # 1. Click mở dropdown
            container.scroll_into_view_if_needed()

            if lib_type == "chosen":
                trigger = container.locator("a.chosen-single, span").first
                if trigger.is_visible():
                    trigger.click()
                else:
                    container.click()
            else:
                container.click()

            # 2. Tìm ô search (Selector rộng hơn để tránh trượt)
            # Chosen: input nằm trong .chosen-drop
            # Select2: input nằm trong .select2-container--open (thường ở cuối body)
            search_box = None
            if lib_type == "chosen":
                search_box = container.locator(".chosen-drop input").first
            else:
                # Tìm input search của Select2 đang mở bất kỳ đâu trên trang
                search_box = page.locator(
                    ".select2-container--open input.select2-search__field"
                ).first

            # Đợi 1 chút cho animation dropdown
            try:
                search_box.wait_for(state="visible", timeout=1000)
            except:
                pass

            # 3. Điền giá trị
            if search_box and search_box.is_visible():
                search_box.fill(str(value))
                time.sleep(0.5)  # Đợi filter chạy

                # [QUAN TRỌNG]: Thay vì chỉ Enter, hãy thử CLICK vào kết quả đầu tiên
                # Điều này giúp đảm bảo sự kiện onClick của JS được kích hoạt
                try:
                    if lib_type == "chosen":
                        # Chọn kết quả active đầu tiên
                        first_result = container.locator(".active-result").first
                        if first_result.is_visible():
                            first_result.click()
                        else:
                            page.keyboard.press("Enter")
                    else:
                        # Select2 highlighted result
                        first_result = page.locator(
                            ".select2-results__option--highlighted"
                        ).first
                        if first_result.is_visible():
                            first_result.click()
                        else:
                            page.keyboard.press("Enter")
                except:
                    page.keyboard.press("Enter")

                print(f"         ✅ [Dropdown] Đã chọn: '{value}'")
            else:
                # Fallback gõ mù (Nếu ô search bị ẩn do CSS lạ)
                print(f"         ⌨️ Gõ phím trực tiếp: '{value}'")
                page.keyboard.type(str(value))
                time.sleep(0.5)
                page.keyboard.press("Enter")

            # [QUAN TRỌNG]: Nhấn Tab để đóng dropdown và trigger Save
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

    def _safe_compile(self, text):
        """Tạo Regex an toàn từ text"""
        try:
            return re.compile(re.escape(str(text)), re.IGNORECASE)
        except:
            return re.compile(str(text), re.IGNORECASE)

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
