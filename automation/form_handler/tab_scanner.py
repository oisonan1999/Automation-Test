# automation/form_handler/tab_scanner.py - split from form_handler.py
# Scan/verify fields across sidebar tabs
import time
import re
import random
from playwright.sync_api import Page


class TabScannerMixin:
    """Scan/verify fields across sidebar tabs"""

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

