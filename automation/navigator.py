# automation/navigator.py
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

    def smart_navigate(self, page, target):
        """
        Điều hướng thông minh:
        - Nếu target là List (VD: ["Menu", "SubMenu"]) -> Gọi _smart_navigate_path (Của bạn)
        - Nếu target là String (VD: "Menu") -> Gọi smart_click hoặc goto
        """
        # DEBUG: Print target type and value
        print(
            f"   🔍 DEBUG smart_navigate - Type: {type(target).__name__}, Value: {target}"
        )

        try:
            page.wait_for_load_state("domcontentloaded", timeout=3000)
        except:
            pass
        # CASE 1: BREADCRUMB LIST (Path Navigation)
        if isinstance(target, list):
            print(f"   ✅ Detected LIST path, calling _smart_navigate_path")
            # Gọi hàm chuyên biệt của bạn
            self._smart_navigate_path(page, target)
            return

        # CASE 2: SINGLE TARGET (String)
        print(f"      🧭 Navigating to: {target}")
        target_str = str(target)
        try:
            if "/" not in target_str and "http" not in target_str:
                self.smart_click(page, target_str)
            else:
                page.goto(target_str)
                self._wait_for_long_loading(page)
        except:
            print(f"      ⚠️ Navigation fallback failed for {target}")

    def _smart_navigate_path(self, page, path_list):
        print(f"📍 Nav: {'->'.join(path_list)}")
        # Bỏ networkidle wait để tăng tốc, menu thường đã sẵn sàng

        for i, item_name in enumerate(path_list):
            item_name = str(item_name).strip()
            is_first_step = i == 0
            is_last_step = i == len(path_list) - 1
            regex_name = self._safe_compile(item_name)

            target_element = None

            try:
                # 1. Lấy tất cả ứng viên chứa từ khóa (Partial Match)
                # Thêm div[class*='menu'] để bắt các menu div nếu có
                raw_candidates = (
                    page.locator(
                        "a, button, div, span, li, b, strong, h1, h2, h3, h4, h5, h6, .dropdown-item, .nav-link, [role='menuitem'], [role='button']"
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
                        need_parent = is_first_step
                        if not is_last_step and i + 1 < len(path_list):
                            next_name = str(path_list[i + 1]).strip()
                            if next_name.lower() == item_name.lower():
                                need_parent = True
                                print(
                                    f"   🔄 Detected Parent of same-name submenu. Selecting Parent [0]."
                                )

                        if need_parent:
                            target_element = exact_matches[0]
                        else:
                            target_element = exact_matches[-1]

                        print(f"   ⚡️ Exact Match Selected: '{item_name}'")

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
                time.sleep(0.1)  # Giảm từ 0.5s xuống 0.1s

            target_element.hover(force=True)
            time.sleep(0.05)  # Giảm từ 0.2s xuống 0.05s

            if not is_last_step:
                next_item = path_list[i + 1]

                # LOGIC CHÍNH XÁC: Kiểm tra trùng tên TRƯỚC (Highest Priority)
                # Nếu menu con trùng tên menu cha (Perk -> Perk), LUÔN CLICK để toggle
                if item_name.lower() == str(next_item).strip().lower():
                    print(
                        f"   🔄 Same-name submenu detected: '{item_name}' -> '{next_item}'. FORCE CLICK."
                    )
                    target_element.click()
                    time.sleep(0.3)  # Giảm từ 1.0s xuống 0.3s

                    # Chờ cho đến khi submenu xuất hiện (tối đa 2s)
                    wait_start = time.time()
                    submenu_found = False
                    while time.time() - wait_start < 2:  # Giảm từ 3s xuống 2s
                        try:
                            # Đếm số element visible - phải có ít nhất 2 (cha + con)
                            next_regex = self._safe_compile(next_item)
                            all_matches = page.get_by_text(next_regex, exact=True).all()
                            visible_count = sum(
                                1 for el in all_matches if el.is_visible()
                            )
                            if visible_count >= 2:
                                print(
                                    f"   ✅ Submenu '{next_item}' appeared ({visible_count} visible)."
                                )
                                submenu_found = True
                                break
                        except:
                            pass
                        time.sleep(0.1)  # Giảm từ 0.2s xuống 0.1s

                    if not submenu_found:
                        print(
                            f"   ⚠️ Warning: Submenu '{next_item}' may not be visible yet."
                        )
                else:
                    # Nếu KHÔNG trùng tên, kiểm tra xem menu con đã hiện chưa
                    should_click = True
                    try:
                        next_regex = self._safe_compile(next_item)
                        # Tìm menu con KHỚP CHÍNH XÁC
                        next_cand = page.get_by_text(next_regex, exact=True).all()
                        for n in next_cand:
                            if n.is_visible():
                                # Menu con đã mở rồi, không cần click
                                should_click = False
                                print(
                                    f"   ℹ️ Submenu '{next_item}' already visible. Skip click."
                                )
                                break
                    except:
                        pass

                    if should_click:
                        target_element.click()
                        time.sleep(0.2)  # Giảm từ 0.5s xuống 0.2s
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
        Returns True if popup was handled, False otherwise.
        """
        try:
            print("      🔍 Checking for Locked Item popup...")

            # Chờ một chút để popup render
            time.sleep(0.5)

            # --- STRATEGY 1: SELECTOR CHÍNH XÁC (Dựa trên ảnh HTML) ---
            # Tìm nút có class .btn-acquire-lock (thường là thẻ <a>)
            lock_btn = page.locator(".btn-acquire-lock, a.btn-acquire-lock").first

            # Chờ nút xuất hiện với timeout dài hơn (5s)
            try:
                lock_btn.wait_for(state="visible", timeout=5000)
                print("      🔒 Detected Locked Item popup (Class match).")
                print("      🔓 Clicking 'Acquire Lock' button...")

                # Force click để đảm bảo bấm được dù có overlay
                lock_btn.click(force=True)

                print("      ⏳ Waiting for lock acquisition...")

                # Chờ loading sau khi acquire (thường trang sẽ reload hoặc popup đóng)
                try:
                    # Strategy A: Chờ popup biến mất
                    page.locator(".btn-acquire-lock").first.wait_for(
                        state="hidden", timeout=5000
                    )
                    print("      ✅ Lock popup closed")
                except:
                    pass

                try:
                    # Strategy B: Chờ page load
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except:
                    pass

                # Additional buffer để form load xong
                time.sleep(1.5)
                print("      ✅ Lock acquired successfully!")
                return True
            except:
                # Nút không xuất hiện trong 5s
                pass

            # --- STRATEGY 2: TÌM POPUP QUA TEXT (Fallback cho các modal kiểu khác) ---
            print("      🔍 Checking for lock popup by text...")

            # Tìm modal/popup chứa text "locked"
            popup_selectors = [
                ".modal-content",
                ".modal.show",
                "#vit_locker",
                ".swal2-popup",
                "[role='dialog']",
                ".popup",
                ".dialog",
            ]

            popup_found = None
            for selector in popup_selectors:
                try:
                    popup = (
                        page.locator(selector)
                        .filter(
                            has_text=re.compile(
                                "locked|is locked|acquire lock", re.IGNORECASE
                            )
                        )
                        .first
                    )

                    if popup.count() > 0 and popup.is_visible():
                        popup_found = popup
                        print(f"      🔒 Detected lock popup via selector: {selector}")
                        break
                except:
                    continue

            if popup_found:
                # Tìm nút bấm chứa text Acquire hoặc Unlock hoặc Kick
                btn_patterns = [
                    "Acquire Lock",
                    "Acquire",
                    "Unlock",
                    "Kick",
                    "Take Lock",
                    "Override",
                ]

                btn = None
                for pattern in btn_patterns:
                    try:
                        btn_candidate = (
                            popup_found.locator("a, button")
                            .filter(
                                has_text=re.compile(re.escape(pattern), re.IGNORECASE)
                            )
                            .first
                        )

                        if btn_candidate.count() > 0 and btn_candidate.is_visible():
                            btn = btn_candidate
                            print(f"      🎯 Found button: '{pattern}'")
                            break
                    except:
                        continue

                if btn:
                    print("      🔓 Clicking lock button...")
                    btn.click(force=True)

                    # Chờ popup đóng
                    try:
                        popup_found.wait_for(state="hidden", timeout=5000)
                        print("      ✅ Lock popup closed")
                    except:
                        pass

                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass

                    time.sleep(1.5)
                    print("      ✅ Lock acquired successfully!")
                    return True
                else:
                    print("      ⚠️ Lock popup found but no action button detected")

            # --- STRATEGY 3: Global scan for any visible acquire lock button ---
            print("      🔍 Global scan for acquire lock button...")
            try:
                global_lock_btn = (
                    page.locator("a, button")
                    .filter(
                        has_text=re.compile(
                            "Acquire Lock|Acquire|Take Lock", re.IGNORECASE
                        )
                    )
                    .first
                )

                if global_lock_btn.count() > 0 and global_lock_btn.is_visible():
                    print("      🔒 Found lock button via global scan")
                    print("      🔓 Clicking button...")
                    global_lock_btn.click(force=True)

                    try:
                        global_lock_btn.wait_for(state="hidden", timeout=5000)
                    except:
                        pass

                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except:
                        pass

                    time.sleep(1.5)
                    print("      ✅ Lock acquired successfully!")
                    return True
            except:
                pass

            print("      ℹ️ No lock popup detected (item is unlocked)")
            return False  # No popup detected

        except Exception as e:
            print(f"      ⚠️ Error checking lock popup: {e}")
            return False

    def process_deployment(self, page, options=[]):
        print(f"   🚀 Deploy: {options}")
        try:
            # Kiểm tra xem đã ở trang Home (Process Blueprints) chưa
            already_home = False
            try:
                if page.locator("text=Process Blueprints").first.is_visible(
                    timeout=1000
                ):
                    already_home = True
                    print(f"      ✅ Already on Home page")
            except:
                pass

            # Nếu chưa ở Home -> Click logo The Brick để về
            if not already_home:
                print(f"      🏠 Navigating to Home page...")
                logo = page.locator(".brand-link, .logo, a.navbar-brand").first
                if not logo.is_visible():
                    logo = page.locator("a").filter(has_text="The Brick").first
                if not logo.is_visible():
                    logo = page.locator(
                        "nav a:first-child, .navbar a:first-child"
                    ).first

                if logo.is_visible():
                    logo.click()
                    print(f"      ⏳ Waiting for Home page to load (5-10s)...")
                    time.sleep(7)  # Đợi 7s để trang load hoàn toàn
                    page.wait_for_selector("text=Process Blueprints", timeout=10000)
                    print(f"      ✅ Navigated to Home page")
                else:
                    raise Exception("Cannot find The Brick logo to navigate home")

            time.sleep(0.5)

            # Tick các checkbox options
            for opt in options:
                print(f"      🔲 Ticking option: '{opt}'")
                # Strategy 1: Tìm label chứa text và tick checkbox gần nhất
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
                        print(f"         ✅ Ticked: '{opt}'")
                    elif chk.is_visible() and chk.is_checked():
                        print(f"         ✅ Already ticked: '{opt}'")
                    else:
                        print(f"         ⚠️ Checkbox not visible for: '{opt}'")
                else:
                    # Strategy 2: Tìm text trực tiếp rồi click checkbox bên cạnh
                    try:
                        text_el = page.locator(f"text='{opt}'").first
                        if text_el.is_visible():
                            chk_nearby = text_el.locator(
                                "xpath=preceding-sibling::input[@type='checkbox'] | following-sibling::input[@type='checkbox'] | ../input[@type='checkbox']"
                            ).first
                            if chk_nearby.is_visible() and not chk_nearby.is_checked():
                                chk_nearby.check()
                                print(f"         ✅ Ticked via nearby: '{opt}'")
                            else:
                                print(f"         ⚠️ Cannot tick: '{opt}'")
                        else:
                            print(f"         ⚠️ Label not found: '{opt}'")
                    except Exception as e:
                        print(f"         ⚠️ Strategy 2 failed for '{opt}': {e}")

            # Click nút Process
            print(f"      🖱 Clicking Process button...")
            btn = page.locator("button:has-text('Process')").first
            if btn.is_visible():
                btn.click()
                print(f"      ✅ Clicked Process button")
                time.sleep(2)
            else:
                raise Exception("Process button not found or not visible")

        except Exception as e:
            print(f"   ❌ Process Deployment Error: {e}")
            raise e

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
            try:
                sidebar = page.locator(sel).first
                if sidebar.count() > 0 and sidebar.is_visible():
                    item = (
                        sidebar.locator(
                            f"a, div[role='button'], li, span, div.menu-item"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .last
                    )
                    if item.count() > 0 and item.is_visible():
                        print(f"         ✅ Found '{target_text}' in Sidebar ({sel})")
                        item.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        item.click()
                        clicked = True
                        break
            except:
                continue

        # 2. TABS
        if not clicked:
            try:
                tab = (
                    page.locator(
                        f"a[data-toggle='tab'], button[role='tab'], li.nav-item a"
                    )
                    .filter(has_text=re.compile(re.escape(target_clean), re.IGNORECASE))
                    .first
                )
                if tab.count() > 0 and tab.is_visible():
                    print(f"         ✅ Found Tab '{target_text}'")
                    tab.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    tab.click()
                    clicked = True
            except:
                pass

        # 3. CHECK IF ALREADY ACTIVE
        # Element có thể đã được click rồi (class active/selected)
        if not clicked:
            try:
                active_items = (
                    page.locator("a.active, li.active, div.active, [class*='selected']")
                    .filter(has_text=re.compile(re.escape(target_clean), re.IGNORECASE))
                    .all()
                )

                for item in active_items:
                    if item.is_visible():
                        item_text = item.inner_text().strip()
                        if target_clean.lower() in item_text.lower():
                            print(
                                f"         ℹ️ Element '{target_text}' is already active/selected"
                            )
                            clicked = True
                            break
            except:
                pass

        # 4. GENERIC TEXT (Multiple strategies)
        if not clicked:
            print(f"         ⚠️ Sidebar/Tab not found. Trying generic text match...")

            # Strategy A: Exact match with buttons/links
            try:
                element = (
                    page.locator(f"button, a, div[role='button'], span[role='button']")
                    .filter(
                        has_text=re.compile(
                            f"^\\s*{re.escape(target_clean)}\\s*$", re.IGNORECASE
                        )
                    )
                    .first
                )
                if element.count() > 0 and element.is_visible():
                    element.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    element.click()
                    clicked = True
            except:
                pass

            # Strategy B: Contains match (broader)
            if not clicked:
                try:
                    element = (
                        page.locator(
                            f"button, a, div[role='button'], span[role='button'], li, div.menu-item"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .first
                    )
                    if element.count() > 0 and element.is_visible():
                        element.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        element.click()
                        clicked = True
                except:
                    pass

            # Strategy C: Playwright's text= selector (most lenient)
            if not clicked:
                try:
                    element = page.locator(f"text={target_clean}").first
                    if element.count() > 0 and element.is_visible():
                        element.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        element.click()
                        clicked = True
                except:
                    pass

        if clicked:
            # Gọi hàm chờ loading được update bên dưới
            self._wait_for_long_loading(page)
            return True

        # [FIX] KHÔNG CRASH - Log error và return False
        print(f"         ❌ FAILED: Cannot find clickable element '{target_text}'")
        print(f"         💡 Possible reasons:")
        print(
            f"            - Element not loaded yet (try adding wait/delay before this step)"
        )
        print(f"            - Element text might be different (check page source)")
        print(f"            - Element might be in iframe/shadow DOM")

        # Debug: In ra các elements có text tương tự
        try:
            print(f"         🔍 Looking for similar elements...")
            similar = (
                page.locator("a, button, div[role='button'], li, span")
                .filter(
                    has_text=re.compile(
                        (
                            target_clean.split()[0]
                            if target_clean.split()
                            else target_clean
                        ),
                        re.IGNORECASE,
                    )
                )
                .all()[:5]
            )

            if similar:
                print(f"         📋 Found {len(similar)} similar elements:")
                for el in similar:
                    if el.is_visible():
                        try:
                            text = el.inner_text().strip()[:60]
                            print(f"            - '{text}'")
                        except:
                            pass
        except:
            pass

        return False

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
                # Chờ tối đa 6s để spinner biến mất
                page.locator(active_spinner).first.wait_for(
                    state="hidden", timeout=3000
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
            page.wait_for_load_state("networkidle", timeout=3000)
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
