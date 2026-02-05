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

                # Bước 1: Tìm Element
                target_element = self._find_input_element(page, label)

                if target_element:
                    # Bước 2: Điền dữ liệu (Logic thông minh nằm ở đây)
                    success = self._fill_element_smartly(page, target_element, value)
                    if not success:
                        print(f"         ❌ Action Failed for '{label}'")
                    else:
                        # Chờ 3s sau mỗi field để dropdown/data load xong
                        time.sleep(3)
                else:
                    print(
                        f"         ❌ Cannot find field '{label}'. Trying alternative search..."
                    )
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
            scope = page
            if page.locator(".modal.show").count() > 0:
                scope = page.locator(".modal.show").last
                print("      📍 Scope: Modal detected")

            target_btn = None

            # =========================================================
            # CHIẾN THUẬT 1: TÌM NÚT THEO THỨ TỰ ƯU TIÊN CAO
            # Clone > Create > Save > Update > Submit
            # =========================================================
            priority_buttons = [
                "Clone",  # Clone form
                "Create",
                "Save",
                "Update",
                "Submit",
                "Confirm",
                "OK",
                "Yes",
            ]

            for btn_text in priority_buttons:
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
        print(f"         🔍 Searching for field: '{label_text}'")
        label_lower = label_text.lower().strip()
        # Tạo version không space/underscore để fuzzy match
        label_normalized = re.sub(r"[\s_-]+", "", label_lower)

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

        # [FIX] Thêm <legend> vào danh sách tìm kiếm (Gate field dùng <legend>)
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

                    print(f"         ✅ Found target by for attribute: #{for_attr}")

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
        try:
            selects = page.locator("select:visible").all()
            for sel in selects:
                try:
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

            # Vue Multiselect: div.multiselect
            multiselect_sib = hidden_select.locator(
                "xpath=following-sibling::div[contains(@class, 'multiselect')]"
            ).first
            if multiselect_sib.count() > 0 and multiselect_sib.is_visible():
                return multiselect_sib

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
                    #     lib_type = "chosen"
                    # else:
                    #     lib_type = "select2"
                    # return self._handle_js_dropdown(page, wrapper, value, lib_type)

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
            elif lib_type == "multiselect":
                # Vue Multiselect: Click vào input hoặc container
                trigger = container.locator(
                    ".multiselect__input, .multiselect__tags"
                ).first
                if trigger.is_visible():
                    trigger.click()
                else:
                    container.click()
            else:
                container.click()

            # ========================================
            # 2. CHỜ DROPDOWN OPTIONS LOAD XONG
            # Polling cho đến khi có ít nhất 1 option hiển thị
            # ========================================
            print(f"         ⏳ Waiting for dropdown options to load...")
            wait_start = time.time()
            max_wait = 2  # Chờ tối đa 2 giây
            options_loaded = False

            while time.time() - wait_start < max_wait:
                try:
                    if lib_type == "chosen":
                        # Chosen: Tìm .chosen-drop có chứa options
                        options = container.locator(
                            ".chosen-drop .active-result, .chosen-drop li"
                        ).all()
                    elif lib_type == "multiselect":
                        # Vue Multiselect: Tìm .multiselect__element
                        options = page.locator(
                            ".multiselect__element, .multiselect__option"
                        ).all()
                    else:
                        # Select2: Tìm options trong dropdown đang mở
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

            # 3. Tìm ô search
            search_box = None
            if lib_type == "chosen":
                search_box = container.locator(".chosen-drop input").first
            elif lib_type == "multiselect":
                search_box = container.locator(".multiselect__input").first
            else:
                search_box = page.locator(
                    ".select2-container--open input.select2-search__field"
                ).first

            # Đợi search box visible
            try:
                search_box.wait_for(state="visible", timeout=2000)
            except:
                pass

            # 4. Điền giá trị và chờ filter
            if search_box and search_box.is_visible():
                search_box.fill(str(value))

                # ========================================
                # CHỜ KẾT QUẢ FILTER HIỂN THỊ
                # ========================================
                print(f"         ⏳ Waiting for search results...")
                time.sleep(1.0)  # Chờ 1s cho filter chạy

                # Chờ thêm cho đến khi có kết quả match
                wait_start = time.time()
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
                            break
                    except:
                        pass
                    time.sleep(0.3)

                # 5. Click vào kết quả đầu tiên
                try:
                    if lib_type == "chosen":
                        first_result = container.locator(".active-result").first
                        if first_result.is_visible():
                            first_result.click()
                        else:
                            page.keyboard.press("Enter")
                    elif lib_type == "multiselect":
                        first_result = page.locator(
                            ".multiselect__element span, .multiselect__option"
                        ).first
                        if first_result.is_visible():
                            first_result.click()
                        else:
                            page.keyboard.press("Enter")
                    else:
                        first_result = page.locator(
                            ".select2-results__option--highlighted, .select2-results__option"
                        ).first
                        if first_result.is_visible():
                            first_result.click()
                        else:
                            page.keyboard.press("Enter")
                except:
                    page.keyboard.press("Enter")

                print(f"         ✅ [Dropdown] Đã chọn: '{value}'")
            else:
                # Fallback gõ mù
                print(f"         ⌨️ Gõ phím trực tiếp: '{value}'")
                page.keyboard.type(str(value))
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
