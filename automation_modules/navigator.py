# automation_modules/navigator.py
import time
import re
from playwright.sync_api import Page


class NavigatorMixin:
    """Chứa logic tìm kiếm menu và điều hướng"""

    def _safe_compile(self, text):
        if not text:
            return re.compile(r"^$")
        safe_text = re.escape(str(text)).replace(r"\ ", r"\s+")
        return re.compile(safe_text, re.IGNORECASE)

    def _smart_navigate_path(self, page, path_list):
        print(f"📍 Nav: {'->'.join(path_list)}")
        if "/" not in path_list:
            self.smart_click(page, path_list)
        else:
            page.goto(path_list)

        for i, item_name in enumerate(path_list):
            is_first_step = i == 0
            is_last_step = i == len(path_list) - 1
            regex_name = self._safe_compile(item_name)

            target_element = None

            try:
                # 1. Lấy tất cả ứng viên chứa từ khóa (Partial Match)
                # Thêm div[class*='menu'] để bắt các menu div nếu có
                raw_candidates = (
                    page.locator(
                        "a, button, .dropdown-item, .nav-link, [role='menuitem'], div[role='button']"
                    )
                    .filter(has_text=regex_name)
                    .all()
                )

                # 2. Lọc danh sách hiển thị (Visible)
                visible_candidates = [el for el in raw_candidates if el.is_visible()]

                if visible_candidates:
                    # --- BƯỚC LỌC THÔNG MINH (QUAN TRỌNG) ---

                    # Nhóm 1: Khớp CHÍNH XÁC 100% (Case-insensitive)
                    # Ví dụ: Text là "Perk", User tìm "Perk" -> Trúng. "Perk Slot" -> Trượt.
                    exact_matches = []
                    for el in visible_candidates:
                        text = el.inner_text().strip().lower()
                        if text == item_name.lower():
                            exact_matches.append(el)

                    # LOGIC CHỌN MỤC TIÊU:
                    if exact_matches:
                        # Nếu có khớp chính xác:
                        # - Bước 1 (Menu Cha): Chọn cái ĐẦU TIÊN (thường là Parent Menu trên thanh chính)
                        # - Bước >1 (Menu Con): Chọn cái CUỐI CÙNG (thường là Child Menu vừa xổ ra)
                        #   (Điều này giải quyết được cả vụ Boost -> Boost trùng tên)
                        if is_first_step:
                            target_element = exact_matches[0]
                        else:
                            target_element = exact_matches[-1]
                        print(
                            f"   ⚡️ Chọn kết quả khớp chính xác (Exact Match): '{item_name}'"
                        )

                    else:
                        # Nếu KHÔNG có khớp chính xác (User gõ tắt hoặc tên dài):
                        # Dùng lại logic cũ: Lấy cái cuối cùng (để bắt menu con)
                        # Nhưng ưu tiên cái nào ngắn nhất (gần với từ khóa nhất) để tránh bắt nhầm "Perk Slot"
                        best_candidate = visible_candidates[-1]
                        min_len = 9999
                        for el in visible_candidates:
                            txt_len = len(el.inner_text())
                            if txt_len < min_len:
                                min_len = txt_len
                                best_candidate = el

                        target_element = best_candidate
                        print(
                            f"   ⚠️ Không khớp chính xác, chọn kết quả gần đúng nhất: '{target_element.inner_text()}'"
                        )

            except Exception as e:
                print(f"   ⚠️ Lỗi Locator: {e}")

            # --- FALLBACK: QUÉT SÂU (Nếu cách trên thất bại hoàn toàn) ---
            if not target_element:
                print(f"   🐢 Turbo mode miss, deep scanning...")
                all_locs = page.get_by_text(regex_name).all()
                vis = [l for l in all_locs if l.is_visible()]
                if vis:
                    target_element = vis[-1]  # Lấy cái cuối cùng

            if not target_element:
                raise Exception(f"Không tìm thấy Menu '{item_name}'")

            # --- THAO TÁC ---
            target_element.scroll_into_view_if_needed()
            if not is_first_step:
                time.sleep(0.5)  # Chờ menu xổ xuống

            target_element.hover(force=True)
            time.sleep(0.2)

            if not is_last_step:
                next_item = path_list[i + 1]
                # Kiểm tra xem menu con đã hiện chưa.
                # Nếu chưa HOẶC nếu menu con trùng tên cha (Perk -> Perk), click để mở.
                next_regex = self._safe_compile(next_item)

                should_click = True
                try:
                    # Nếu tìm thấy menu con KHỚP CHÍNH XÁC đang hiện -> Không cần click
                    # (Tránh trường hợp click lại làm đóng menu)
                    next_cand = page.get_by_text(next_regex, exact=True).all()
                    for n in next_cand:
                        if n.is_visible():
                            should_click = False
                            break
                except:
                    pass

                # Với trường hợp trùng tên (Perk -> Perk), luôn Click cha để chắc chắn
                if item_name.lower() == next_item.lower():
                    should_click = True

                if should_click:
                    target_element.click()
                    time.sleep(0.5)
            else:
                # Bước cuối
                print(f"   🎯 Click: {item_name}")
                if target_element.is_visible():
                    target_element.click()
                else:
                    target_element.evaluate("e => e.click()")

        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except:
            pass

    def _handle_locked_item_popup(self, page):
        """
        Xử lý popup Locked Item.
        Target chính xác vào class .btn-acquire-lock dựa trên HTML.
        """
        try:
            # --- ƯU TIÊN 1: SELECTOR CHÍNH XÁC (Dựa trên ảnh HTML) ---
            # Tìm nút có class .btn-acquire-lock (thường là thẻ <a>)
            lock_btn = page.locator(".btn-acquire-lock").first

            # Check visible với timeout ngắn
            if lock_btn.is_visible(timeout=2000):
                print("      🔒 Phát hiện Locked Item (Class match).")
                print("      🔓 Đang bấm 'Acquire Lock'...")

                # Force click để đảm bảo bấm được dù có overlay
                lock_btn.click(force=True)

                # Chờ loading sau khi acquire (thường trang sẽ reload)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except:
                    time.sleep(2.0)
                return

            # --- ƯU TIÊN 2: QUÉT TEXT (Fallback cho các modal kiểu khác) ---
            popup = (
                page.locator(".modal-content, #vit_locker, .swal2-popup")
                .filter(has_text=re.compile("locked|is locked", re.IGNORECASE))
                .last
            )

            if popup.is_visible(timeout=1000):
                print("      🔒 Phát hiện Locked Item (Text match).")
                # Tìm nút bấm chứa text Acquire hoặc Unlock hoặc Kick
                btn = (
                    popup.locator("a, button")
                    .filter(has_text=re.compile("Acquire|Unlock|Kick", re.IGNORECASE))
                    .first
                )

                if btn.is_visible():
                    btn.click(force=True)
                    time.sleep(2.0)

        except Exception as e:
            # print(f"      ⚠️ Lỗi check lock: {e}")
            pass

    def process_deployment(self, page, options=[]):
        print(f"   🚀 Deploy: {options}")
        try:
            logo = page.locator(".brand-link, .logo, a.navbar-brand").first
            if not logo.is_visible():
                logo = page.locator("a").filter(has_text="The Brick").first
            logo.click()
            page.wait_for_selector("text=Process Blueprints", timeout=10000)
            for opt in options:
                lbl = (
                    page.locator("label")
                    .filter(has_text=re.compile(opt, re.IGNORECASE))
                    .first
                )
                if lbl.is_visible():
                    chk = lbl.locator("input[type='checkbox']").first
                    if not chk.is_visible():
                        id_v = lbl.get_attribute("for")
                        if id_v:
                            chk = page.locator(f"#{id_v}")
                    if chk.is_visible() and not chk.is_checked():
                        chk.check()

            btn = page.locator("button:has-text('Process')").first
            if btn.is_visible():
                btn.click()
        except:
            pass

    # ==========================================================================
    # [MỚI] SMART CLICK: CHUYÊN TRỊ SIDEBAR / TABS
    # ==========================================================================
    def smart_click(self, page, target_text):
        print(f"      🖱 Smart Click: '{target_text}'")
        target_clean = target_text.strip()
        clicked = False

        # 1. SIDEBAR (Ưu tiên số 1)
        sidebar_selectors = [
            ".sidebar",
            "#sidebar",
            "#left-menu",
            ".nav-pills",
            ".list-group",
            "div[class*='sidebar']",
            "div[class*='menu']",
            "aside",
            "#menu",
        ]

        for sel in sidebar_selectors:
            sidebar = page.locator(sel).first
            if sidebar.is_visible():
                item = (
                    sidebar.locator(f"a, div[role='button'], li, span, div.menu-item")
                    .filter(has_text=re.compile(re.escape(target_clean), re.IGNORECASE))
                    .last
                )
                if item.is_visible():
                    print(f"         ✅ Found '{target_text}' in Sidebar ({sel})")
                    item.scroll_into_view_if_needed()
                    item.click()
                    clicked = True
                    break

        # 2. TABS
        if not clicked:
            tab = (
                page.locator(f"a[data-toggle='tab'], button[role='tab'], li.nav-item a")
                .filter(has_text=re.compile(re.escape(target_clean), re.IGNORECASE))
                .first
            )
            if tab.is_visible():
                print(f"         ✅ Found Tab '{target_text}'")
                tab.click()
                clicked = True

        # 3. GENERIC TEXT
        if not clicked:
            print(f"         ⚠️ Sidebar/Tab not found. Trying generic text match...")
            element = (
                page.locator(f"button, a, div[role='button']")
                .filter(
                    has_text=re.compile(f"^{re.escape(target_clean)}$", re.IGNORECASE)
                )
                .first
            )
            if not element.is_visible():
                element = page.locator(f"text={target_clean}").first

            if element.is_visible():
                element.click()
                clicked = True

        if clicked:
            # Gọi hàm chờ loading được update bên dưới
            self._wait_for_long_loading(page)
            return True

        raise Exception(f"Cannot click element: '{target_text}'")

    def _wait_for_long_loading(self, page):
        """
        Đợi bánh răng xoay (Gear/Spinner).
        Chiến thuật: Chủ động đợi selector xuất hiện (Wait for attached/visible).
        """
        print("         ⏳ Checking for Loaders/Spinners...")

        # Danh sách selector loading (Ưu tiên HTML bạn cung cấp)
        spinner_selectors = [
            "i.fa.fa-cog.fa-spin",  # Chính xác HTML bạn đưa
            "i.fa-cog.fa-spin",  # Rút gọn
            ".fa-spin",  # Mọi icon xoay
            ".loading",
            ".spinner",
            ".loader",
            "div:has-text('Loading')",
            ".swal2-loading",
            ".blockUI",
        ]

        active_spinner = None

        # GIAI ĐOẠN 1: PHỤC KÍCH (Ambush)
        # Đợi tối đa 5s xem có bất kỳ spinner nào xuất hiện không
        # Dùng Promise.race để bắt cái nào hiện ra trước
        try:
            # Tạo list các task wait_for_selector
            for sel in spinner_selectors:
                try:
                    # Wait for visible với timeout ngắn (200ms) để scan nhanh
                    # Hoặc dùng logic polling của Playwright
                    if page.locator(sel).first.is_visible():
                        active_spinner = sel
                        break
                except:
                    pass

            # Nếu chưa thấy ngay, thử đợi 3s xem nó có render ra không (Network delay)
            if not active_spinner:
                time.sleep(1.0)  # Đợi render
                for sel in spinner_selectors:
                    if page.locator(sel).first.is_visible():
                        active_spinner = sel
                        break
        except:
            pass

        # GIAI ĐOẠN 2: CHỜ BIẾN MẤT (Wait for Hidden)
        if active_spinner:
            print(
                f"         🔄 Spinner DETECTED: '{active_spinner}'. Waiting for it to finish..."
            )
            try:
                # Chờ tối đa 60s để spinner biến mất
                page.locator(active_spinner).first.wait_for(
                    state="hidden", timeout=60000
                )
                print("         ✅ Spinner finished (Main content loaded).")
            except:
                print(
                    "         ⚠️ Spinner wait timed out (It might be stuck or hidden differently)."
                )
        else:
            print(
                "         ℹ️ No spinner detected immediately. Waiting for network idle just in case."
            )

        # GIAI ĐOẠN 3: NETWORK IDLE (Chốt chặn)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass

        # Nghỉ thêm 1s an toàn
        time.sleep(1.0)

    def _is_sidebar_item(self, page, text):
        """Helper check sidebar"""
        try:
            sidebar_selectors = [
                ".sidebar",
                "#sidebar",
                ".nav-pills",
                ".list-group",
                "aside",
            ]
            for sel in sidebar_selectors:
                sidebar = page.locator(sel).first
                if sidebar.is_visible():
                    if sidebar.locator(f"text={text}").count() > 0:
                        return True
        except:
            pass
        return False
