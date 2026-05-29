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

        # PERF/SPEED: Fast path for known PVE -> Classic PVE navigation.
        # BUT: if 'Classic PVE' isn't visible yet (sidebar accordion collapsed),
        # smart_click can fail and leave us stuck. Only do fast-path if visible.
        try:
            if path_list and str(path_list[-1]).strip().lower() == "classic pve":
                classic_text = str(path_list[-1]).strip()
                classic_loc = (
                    page.locator(
                        "aside a, #left-menu a, .sidebar a, #sidebar a, a, button, [role='button']"
                    )
                    .filter(
                        has_text=re.compile(r"^\s*Classic\s*PVE\s*$", re.IGNORECASE)
                    )
                    .first
                )

                if classic_loc.count() > 0 and classic_loc.is_visible():
                    print(
                        "   ⚡️ Fast path: smart_click('Classic PVE') (Classic PVE already visible)"
                    )
                    self.smart_click(page, classic_text)
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=3000)
                    except:
                        pass
                    # PVE heavy render: wait for React skeletons / aria-busy to complete.
                    # Your Match 1 HTML contains b-skeleton wrappers with aria-busy="true".
                    try:
                        for _ in range(12):  # ~3.6s
                            busy_visible = False
                            skeleton_visible = False
                            try:
                                busy_visible = (
                                    page.locator("[aria-busy='true']:visible").count()
                                    > 0
                                )
                            except:
                                busy_visible = False
                            try:
                                skeleton_visible = (
                                    page.locator(".b-skeleton:visible").count() > 0
                                )
                            except:
                                skeleton_visible = False

                            if not busy_visible and not skeleton_visible:
                                break
                            time.sleep(0.3)
                    except:
                        pass

                    time.sleep(1.0)
                    # Không return sớm: tiếp tục chạy vòng scan navigate bình thường
                    # để đảm bảo tab/menu đã thực sự vào đúng context.
                else:
                    print(
                        "   ℹ️ Skip fast-path for 'Classic PVE' (not visible yet); let full path scan handle accordion."
                    )
        except:
            pass

        for i, item_name in enumerate(path_list):
            item_name = str(item_name).strip()
            is_first_step = i == 0
            is_last_step = i == len(path_list) - 1
            regex_name = self._safe_compile(item_name)

            target_element = None

            try:
                # 1. Lấy tất cả ứng viên chứa từ khóa (Partial Match)
                # Thêm div[class*='menu'] để bắt các menu div nếu có
                menu_base = page.locator(
                    "a, button, div, span, li, b, strong, h1, h2, h3, h4, h5, h6, .dropdown-item, .nav-link, [role='menuitem'], [role='button']"
                ).filter(has_text=regex_name)

                # PERF FIX:
                # Tránh `.all()` + lọc is_visible() trên số lượng lớn (có thể gây treo/timeout ở bước navigate).
                # Chỉ sample phần đầu + phần cuối để vẫn bắt được menu cha/con.
                candidate_count = menu_base.count()
                visible_candidates = []

                front_limit = min(candidate_count, 20)
                for ci in range(front_limit):
                    el = menu_base.nth(ci)
                    try:
                        if el.is_visible():
                            visible_candidates.append(el)
                    except:
                        pass

                tail_limit = 20
                if candidate_count > front_limit:
                    tail_start = max(front_limit, candidate_count - tail_limit)
                    for ci in range(tail_start, candidate_count):
                        el = menu_base.nth(ci)
                        try:
                            if el.is_visible():
                                visible_candidates.append(el)
                        except:
                            pass

                # 2b. SINGULAR/PLURAL FALLBACK: Nếu không tìm thấy, thử biến thể số ít/số nhiều
                # VD: "Superstars" không match menu "Superstar" → thử "Superstar"
                # VD: "Superstar" không match → thử "Superstars"
                if not visible_candidates:
                    alt_name = None
                    if item_name.lower().endswith("s") and len(item_name) > 2:
                        alt_name = item_name[:-1]  # Bỏ 's' cuối
                    else:
                        alt_name = item_name + "s"  # Thêm 's'

                    alt_regex = self._safe_compile(alt_name)
                    alt_base = page.locator(
                        "a, button, div, span, li, b, strong, h1, h2, h3, h4, h5, h6, .dropdown-item, .nav-link, [role='menuitem'], [role='button']"
                    ).filter(has_text=alt_regex)

                    alt_count = alt_base.count()
                    alt_visible = []

                    front_limit = min(alt_count, 20)
                    for ci in range(front_limit):
                        el = alt_base.nth(ci)
                        try:
                            if el.is_visible():
                                alt_visible.append(el)
                        except:
                            pass

                    tail_limit = 20
                    if alt_count > front_limit:
                        tail_start = max(front_limit, alt_count - tail_limit)
                        for ci in range(tail_start, alt_count):
                            el = alt_base.nth(ci)
                            try:
                                if el.is_visible():
                                    alt_visible.append(el)
                            except:
                                pass

                    if alt_visible:
                        print(
                            f"   🔄 Singular/Plural fallback: '{item_name}' → '{alt_name}' ({len(alt_visible)} matches)"
                        )
                        visible_candidates = alt_visible
                        item_name = alt_name  # Cập nhật tên để exact match đúng

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
            try:
                target_element.scroll_into_view_if_needed()
            except Exception as e:
                # DOM can detach during animations / re-renders; don't fail the whole navigation.
                print(
                    f"         ⚠️ scroll_into_view_if_needed failed (detached DOM): {e}"
                )
            if not is_first_step:
                time.sleep(0.1)
            target_element.hover(force=True)
            time.sleep(0.05)

            if not is_last_step:
                next_item = path_list[i + 1]

                # LOGIC CHÍNH XÁC: Kiểm tra trùng tên TRƯỚC
                if item_name.lower() == str(next_item).strip().lower():
                    print(
                        f"   🔄 Same-name submenu detected: '{item_name}' -> '{next_item}'. FORCE CLICK."
                    )
                    target_element.click()
                    time.sleep(0.3)

                    wait_start = time.time()
                    submenu_found = False
                    while time.time() - wait_start < 2:
                        try:
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
                        time.sleep(0.1)

                    if not submenu_found:
                        print(
                            f"   ⚠️ Warning: Submenu '{next_item}' may not be visible yet."
                        )
                else:
                    should_click = True
                    try:
                        next_regex = self._safe_compile(next_item)
                        next_cand = page.get_by_text(next_regex, exact=True).all()
                        for n in next_cand:
                            if n.is_visible():
                                should_click = False
                                print(
                                    f"   ℹ️ Submenu '{next_item}' already visible. Skip click."
                                )
                                break
                    except:
                        pass

                    if should_click:
                        target_element.click()
                        time.sleep(0.2)
            else:
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
        try:
            print("      🔍 Checking for Locked Item popup...")
            # Regression speed-up: giảm đợi để không vượt tool timeout (45s)
            time.sleep(0.1)

            lock_btn = page.locator(".btn-acquire-lock, a.btn-acquire-lock").first

            try:
                lock_btn.wait_for(state="visible", timeout=1500)
                print("      🔒 Detected Locked Item popup (Class match).")
                print("       Clicking 'Acquire Lock' button...")

                lock_btn.click(force=True)

                try:
                    page.locator(".btn-acquire-lock").first.wait_for(
                        state="hidden", timeout=1500
                    )
                    print("      ✅ Lock popup closed")
                except:
                    pass

                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1500)
                except:
                    pass

                time.sleep(0.8)
                print("      ✅ Lock acquired successfully!")
                return True
            except:
                pass

            print("      🔍 Checking for lock popup by text...")
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
            return False
        except Exception as e:
            print(f"      ⚠️ Error checking lock popup: {e}")
            return False

    def process_deployment(self, page, options=[]):
        print(f"   🚀 Deploy: {options}")
        try:
            already_home = False
            try:
                if page.locator("text=Process Blueprints").first.is_visible(
                    timeout=1000
                ):
                    already_home = True
                    print("      ✅ Already on Home page")
            except:
                pass

            if not already_home:
                print("      🏠 Navigating to Home page...")
                logo = page.locator(".brand-link, .logo, a.navbar-brand").first
                if not logo.is_visible():
                    logo = page.locator("a").filter(has_text="The Brick").first
                if not logo.is_visible():
                    logo = page.locator(
                        "nav a:first-child, .navbar a:first-child"
                    ).first

                if logo.is_visible():
                    logo.click()
                    print("      ⏳ Waiting for Home page to load (5-10s)...")
                    time.sleep(7)
                    page.wait_for_selector("text=Process Blueprints", timeout=10000)
                    print("      ✅ Navigated to Home page")
                else:
                    raise Exception("Cannot find The Brick logo to navigate home")

            time.sleep(0.5)

            for opt in options:
                is_uncheck = opt.startswith("-")
                opt_name = opt.lstrip("-").strip() if is_uncheck else opt.strip()
                opt_lower = opt_name.lower()

                if opt_lower in ("toggle all", "toogle all", "select all", "check all"):
                    print("      🔲 Clicking Toggle All checkbox...")
                    try:
                        toggle_label = (
                            page.locator("label")
                            .filter(
                                has_text=re.compile(
                                    r"toggle\s*all|select\s*all|check\s*all",
                                    re.IGNORECASE,
                                )
                            )
                            .first
                        )
                        if toggle_label.is_visible():
                            toggle_chk = toggle_label.locator(
                                "input[type='checkbox']"
                            ).first
                            if not toggle_chk.is_visible():
                                id_v = toggle_label.get_attribute("for")
                                if id_v:
                                    toggle_chk = page.locator(f"#{id_v}")
                            if toggle_chk.is_visible():
                                if is_uncheck:
                                    if toggle_chk.is_checked():
                                        toggle_chk.uncheck()
                                        print("         ✅ Unchecked Toggle All")
                                    else:
                                        print(
                                            "         ✅ Already unchecked: Toggle All"
                                        )
                                else:
                                    if not toggle_chk.is_checked():
                                        toggle_chk.check()
                                        print("         ✅ Checked Toggle All")
                                    else:
                                        print("         ✅ Already checked: Toggle All")
                                time.sleep(1)
                                continue

                        toggle_btn = (
                            page.locator("button, a, span")
                            .filter(
                                has_text=re.compile(
                                    r"toggle\s*all|select\s*all", re.IGNORECASE
                                )
                            )
                            .first
                        )
                        if toggle_btn.is_visible():
                            toggle_btn.click()
                            print("         ✅ Clicked Toggle All button")
                            time.sleep(1)
                            continue
                        print("         ⚠️ Toggle All not found")
                    except Exception as e:
                        print(f"         ⚠️ Toggle All error: {e}")
                    continue

                if is_uncheck:
                    print(f"      ☐ Unchecking option: '{opt_name}'")
                else:
                    print(f"      🔲 Ticking option: '{opt_name}'")

                lbl = (
                    page.locator("label")
                    .filter(has_text=re.compile(re.escape(opt_name), re.IGNORECASE))
                    .first
                )
                if lbl.is_visible():
                    chk = lbl.locator("input[type='checkbox']").first
                    if not chk.is_visible():
                        id_v = lbl.get_attribute("for")
                        if id_v:
                            chk = page.locator(f"#{id_v}")
                    if chk.is_visible():
                        if is_uncheck:
                            if chk.is_checked():
                                chk.uncheck()
                                print(f"         ✅ Unchecked: '{opt_name}'")
                            else:
                                print(f"         ✅ Already unchecked: '{opt_name}'")
                        else:
                            if not chk.is_checked():
                                chk.check()
                                print(f"         ✅ Ticked: '{opt_name}'")
                            else:
                                print(f"         ✅ Already ticked: '{opt_name}'")
                    else:
                        print(f"         ⚠️ Checkbox not visible for: '{opt_name}'")
                else:
                    try:
                        text_el = page.locator(f"text='{opt_name}'").first
                        if text_el.is_visible():
                            chk_nearby = text_el.locator(
                                "xpath=preceding-sibling::input[@type='checkbox'] | following-sibling::input[@type='checkbox'] | ../input[@type='checkbox']"
                            ).first
                            if chk_nearby.is_visible():
                                if is_uncheck:
                                    if chk_nearby.is_checked():
                                        chk_nearby.uncheck()
                                        print(
                                            f"         ✅ Unchecked via nearby: '{opt_name}'"
                                        )
                                    else:
                                        print(
                                            f"         ✅ Already unchecked: '{opt_name}'"
                                        )
                                else:
                                    if not chk_nearby.is_checked():
                                        chk_nearby.check()
                                        print(
                                            f"         ✅ Ticked via nearby: '{opt_name}'"
                                        )
                                    else:
                                        print(
                                            f"         ✅ Already checked: '{opt_name}'"
                                        )
                            else:
                                print(
                                    f"         ⚠️ Cannot {'uncheck' if is_uncheck else 'tick'}: '{opt_name}'"
                                )
                        else:
                            print(f"         ⚠️ Label not found: '{opt_name}'")
                    except Exception as e:
                        print(f"         ⚠️ Strategy 2 failed for '{opt_name}': {e}")

            print("      🖱 Clicking Process button...")
            btn = page.locator("button:has-text('Process')").first
            if btn.is_visible():
                btn.click()
                print("      ✅ Clicked Process button")
                time.sleep(2)
            else:
                raise Exception("Process button not found or not visible")

        except Exception as e:
            print(f"   ❌ Process Deployment Error: {e}")
            raise e

    def _is_daily_reward_content_loaded(self, page):
        try:
            return (
                page.locator(
                    "#start_time_send_daily_reward, [name='start_time_send_daily_reward']"
                ).count()
                > 0
            )
        except Exception:
            return False

    def _click_sidebar_nav_by_id(self, page, nav_id, label):
        selectors = [
            f"aside a#{nav_id}",
            f".sidebar a#{nav_id}",
            f"#left-menu a#{nav_id}",
            f"a.navigate-ajax#{nav_id}",
            f"a[href='#{nav_id}']",
        ]
        for sel in selectors:
            try:
                link = page.locator(sel).first
                if link.count() > 0 and link.is_visible():
                    print(f"         ✅ Sidebar nav '{label}' via {sel}")
                    link.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    link.click()
                    return True
            except Exception:
                continue
        return False

    def _try_expand_pve_section(self, page, target_text):
        """
        PVE accordion expander (Chapter Info / Normal Matches / Match panels)
        - Ưu tiên click icon caret/chevron trong header để mở section.
        - Fallback: click chính header container.
        """
        try:
            if not target_text:
                return False

            target = str(target_text).strip()
            target_lower = target.lower()

            # Only handle known PVE collapsibles to avoid side-effects
            is_section = any(
                k in target_lower for k in ["chapter info", "normal matches"]
            )
            is_match_panel = "match" in target_lower  # e.g. "Match 1 !NAME..."
            if not (is_section or is_match_panel):
                return False

            # Regex:
            # - Chapter/Normal: match exact-ish
            # - Match: match contains "Match" (but tighten for "Match 1/2/3..." to avoid
            #   expanding "Match Settings" or other match-related panels)
            match_num = None
            if is_match_panel:
                m = re.search(r"match\s*(\d+)", target_lower, re.IGNORECASE)
                if m:
                    match_num = m.group(1)

            if "chapter info" in target_lower:
                header_re = re.compile(r"chapter\s*info", re.IGNORECASE)
            elif "normal matches" in target_lower:
                header_re = re.compile(r"normal\s*matches", re.IGNORECASE)
            else:
                if match_num is not None:
                    # Avoid strict \b boundaries: Match header text may contain punctuation/newlines (e.g. "Match 1 !!NAME...")
                    header_re = re.compile(rf"match\s*{match_num}", re.IGNORECASE)
                else:
                    header_re = re.compile(r"match", re.IGNORECASE)

            # Candidate headers: containers that contain the text
            candidates = page.locator(
                "header, div, section, fieldset, .panel, .card, [role='tab']"
            ).filter(has_text=header_re)

            count = candidates.count()
            if count <= 0:
                return False

            # Check a few candidates (topmost/closest first usually enough)
            for i in range(min(count, 8)):
                header = candidates.nth(i)
                if not header.is_visible():
                    continue

                # 1) If aria-expanded exists on header or descendant, use it to decide click
                expanded_attr = None
                try:
                    expanded_attr = header.get_attribute("aria-expanded")
                except:
                    expanded_attr = None

                caret_clicked = False

                # 2) Prefer deterministic toggle button (aria-controls / aria-expanded)
                #    Example Normal Matches header (from your HTML):
                #    <button ... aria-expanded="false" aria-controls="match-mode-...">...</button>
                try:
                    toggle_btn = None
                    try:
                        # Normal Matches header in your HTML:
                        # <button ... class="btn-collapse-open not-collapsed"
                        #   aria-expanded="false" aria-controls="match-mode-1-...">...</button>
                        # -> For "normal matches" we MUST click the right-side collapse-open button
                        #    whose aria-controls starts with "match-mode-".
                        if "normal matches" in target_lower:
                            toggle_selector = (
                                "button[aria-controls^='match-mode-'][aria-expanded]"
                            )
                        elif is_match_panel and match_num is not None:
                            # Match panel expander HTML (from user):
                            # <button ... aria-expanded="false" aria-controls="chapter-match-...">
                            # In PVE, match panels use aria-controls="chapter-match-...", not "match-mode-...".
                            # So select by aria-controls contains chapter-match-.
                            toggle_selector = (
                                "button[aria-expanded][aria-controls*='chapter-match-']"
                            )
                        else:
                            toggle_selector = "button[aria-controls][aria-expanded], button[aria-expanded]"

                        toggle_btn = header.locator(toggle_selector).first
                    except:
                        toggle_btn = None

                    if (
                        toggle_btn
                        and toggle_btn.count() > 0
                        and toggle_btn.is_visible()
                    ):
                        try:
                            ea = toggle_btn.get_attribute("aria-expanded")
                        except:
                            ea = None

                        if ea is None or str(ea).lower() in ("false", "0", "no"):
                            toggle_btn.click(force=True)
                            caret_clicked = True
                        else:
                            # Already expanded
                            return True
                except:
                    caret_clicked = False

                # 3) Fallback to caret/chevron/icon heuristic if toggle button not found
                if not caret_clicked:
                    try:
                        caret_control = (
                            header.locator("button, a, span, div")
                            .filter(
                                has=page.locator(
                                    "i[class*='chevron'], i[class*='caret'], i[class*='fa-'], svg[class*='chevron'], svg[class*='caret'], svg[class*='fa-'], [class*='chevron'], [class*='caret']"
                                )
                            )
                            .first
                        )

                        if caret_control.count() > 0 and caret_control.is_visible():
                            caret_expanded = None
                            try:
                                caret_expanded = caret_control.get_attribute(
                                    "aria-expanded"
                                )
                            except:
                                caret_expanded = None

                            effective_expanded = (
                                caret_expanded
                                if caret_expanded is not None
                                else expanded_attr
                            )

                            if effective_expanded is None or str(
                                effective_expanded
                            ).lower() in ("false", "0", "no"):
                                caret_control.click(force=True)
                                caret_clicked = True
                            else:
                                return True
                    except:
                        caret_clicked = False

                # 3) If no caret_control clicked, try aria-expanded descendant
                if not caret_clicked:
                    try:
                        btn_expanded = header.locator("[aria-expanded]").first
                        if btn_expanded.count() > 0 and btn_expanded.is_visible():
                            ea = btn_expanded.get_attribute("aria-expanded")
                            if ea is None or str(ea).lower() in ("false", "0", "no"):
                                btn_expanded.click(force=True)
                                caret_clicked = True
                            else:
                                return True
                    except:
                        pass

                # 4) Fallback: click header itself
                if not caret_clicked:
                    try:
                        header.click(force=True)
                        caret_clicked = True
                    except:
                        caret_clicked = False

                if caret_clicked:
                    time.sleep(0.6)
                    try:
                        self._wait_for_long_loading(page)
                    except:
                        pass

                    # Verify that the panel actually expanded (prefer aria-controls visibility).
                    try:
                        # find the toggle button under header that controls the panel
                        toggle_btn = None
                        try:
                            toggle_btn = header.locator(
                                "button[aria-controls], [role='button'][aria-controls]"
                            ).first
                        except:
                            toggle_btn = None

                        aria_controls = None
                        if toggle_btn and toggle_btn.count() > 0:
                            try:
                                aria_controls = toggle_btn.get_attribute(
                                    "aria-controls"
                                )
                            except:
                                aria_controls = None

                        if aria_controls:
                            panel = page.locator(f"#{aria_controls}")
                            # Wait a bit for DOM visibility (PVE accordion can be slow)
                            try:
                                panel.wait_for(state="visible", timeout=5000)
                            except:
                                panel.wait_for(state="visible", timeout=15000)

                            # Strong verify:
                            # - Normal Matches: must expose Match 1 inside this panel.
                            # - Match N: must expose at least one select2 SSDB search input inside this panel.
                            try:
                                if "normal matches" in target_lower:
                                    match1_in_panel = panel.locator(
                                        "text=Match 1"
                                    ).first
                                    match1_in_panel.wait_for(
                                        state="visible", timeout=8000
                                    )
                                    return True

                                if is_match_panel:
                                    # Match panel render may be slower; accept several stable signals.
                                    # 1) "Match Type" appears in expanded Match settings
                                    # 2) SSDB select2 search input becomes visible
                                    # 3) SSGroup ID label/text appears
                                    try:
                                        match_type = panel.locator(
                                            "text=Match Type"
                                        ).first
                                        match_type.wait_for(
                                            state="visible", timeout=8000
                                        )
                                        return True
                                    except:
                                        pass

                                    try:
                                        ssdb_in_panel = panel.locator(
                                            "input.select2-search__field:visible"
                                        ).first
                                        ssdb_in_panel.wait_for(
                                            state="visible", timeout=8000
                                        )
                                        return True
                                    except:
                                        pass

                                    try:
                                        ssgrp_in_panel = panel.locator(
                                            "text=SSGroup ID"
                                        ).first
                                        if ssgrp_in_panel.count() > 0:
                                            ssgrp_in_panel.wait_for(
                                                state="visible", timeout=2000
                                            )
                                            return True
                                    except:
                                        pass
                            except:
                                pass

                            # fallback: check aria-expanded state directly on the toggle button
                            try:
                                if toggle_btn and toggle_btn.count() > 0:
                                    ea_now = toggle_btn.get_attribute("aria-expanded")
                                    if ea_now and str(ea_now).lower() == "true":
                                        return True
                            except:
                                pass

                            # fallback: check aria-expanded became true somewhere under header
                            try:
                                expanded_now = (
                                    header.locator("[aria-expanded='true']").count() > 0
                                )
                                if expanded_now:
                                    return True
                            except:
                                pass

                        # If still not sure, apply lightweight content checks.
                        if "normal matches" in target_lower:
                            match_re = re.compile(r"Match\s*\d+", re.IGNORECASE)
                            all_matches = page.get_by_text(match_re).all()
                            visible_count = sum(
                                1 for el in all_matches if el.is_visible()
                            )
                            if visible_count >= 1:
                                return True

                        if is_match_panel:
                            ssdb_inp = page.locator(
                                "input.select2-search__field:visible"
                            ).first
                            if ssdb_inp.count() > 0 and ssdb_inp.is_visible():
                                return True

                            ssgrp = page.locator("text=SSGroup ID").first
                            if ssgrp.count() > 0 and ssgrp.is_visible():
                                return True
                    except Exception:
                        pass

        except Exception as e:
            print(f"         ⚠️ _try_expand_pve_section error: {e}")
        return False

    def smart_click(self, page, target_text):
        print(f"      🖱 Smart Click: '{target_text}'")
        target_clean = target_text.strip()
        clicked = False

        # RBE UI timing guard:
        # "Contest Superstars" thường nằm trong accordion "Wrapper" và có thể chưa render kịp
        # khi smart_click bắt đầu quét. Thêm 1 đoạn chờ ngắn để tránh FAIL timing.
        # PVE/Classic PVE accordion expansion attempt first.
        # (Classic PVE is often inside a collapsed accordion; if we don't expand,
        # smart_click('Classic PVE') will fail and abort the navigation chain.)
        try:
            t_lower = target_clean.lower()
            if "classic pve" in t_lower or t_lower.strip() == "pve":
                pve_hdr_re = re.compile(r"\bpve\b", re.IGNORECASE)
                hdrs = page.locator(
                    "header, div, section, fieldset, .panel, .card"
                ).filter(has_text=pve_hdr_re)
                for i in range(min(hdrs.count(), 10)):
                    hdr = hdrs.nth(i)
                    if not hdr.is_visible():
                        continue
                    # prefer explicit aria-expanded=false toggle button if present
                    toggle_btn = None
                    try:
                        toggle_btn = hdr.locator(
                            "button[aria-expanded], [role='button'][aria-expanded]"
                        ).first
                    except:
                        toggle_btn = None

                    if toggle_btn and toggle_btn.count() > 0:
                        try:
                            ea = toggle_btn.get_attribute("aria-expanded")
                        except:
                            ea = None
                        if ea is None or str(ea).lower() in ("false", "0", "no"):
                            toggle_btn.click(force=True)
                            time.sleep(1.0)

                            # also try caret/chevron icon inside header
                            try:
                                caret = hdr.locator(
                                    "i[class*='chevron'], i[class*='caret'], [class*='chevron'], [class*='caret'], svg[class*='chevron'], svg[class*='caret']"
                                ).first
                                if caret.count() > 0 and caret.is_visible():
                                    caret.click(force=True)
                                    time.sleep(0.6)
                            except:
                                pass

                            break
                    else:
                        # fallback: click header itself once
                        try:
                            hdr.click(force=True)
                            time.sleep(0.8)
                            break
                        except:
                            pass
        except:
            pass

        # PVE accordion expansion attempt for known PVE sections (Chapter Info / Normal Matches / Match panels)
        try:
            if self._try_expand_pve_section(page, target_clean):
                return True
        except:
            pass

        try:
            t = target_clean.lower()
            if ("contest superstars" in t) or (t.strip() == "contest superstars"):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=2000)
                except:
                    pass
                time.sleep(1.2)
                self._wait_for_long_loading(page)
        except:
            pass

        # RBE/Contest UI timing guard: “PVP” tab may appear after “Contest Superstars” click + panel load.
        # Add a targeted “PVP” click before generic sidebar fallback (to avoid early FAIL).
        #
        # Modal-scoped click: when "Define Schedules" opens a dialog, "Add Schedule" button
        # may not exist at page level (only inside dialog).
        try:
            if "add schedule" in target_clean.lower():
                add_sched_re = re.compile(r"Add\s*Schedule", re.IGNORECASE)

                modal_scope = page.locator(
                    ".modal.show, .modal.in, [role='dialog']:visible, .swal2-popup:visible"
                ).first

                # Prefer dialog-local search if any modal is open
                if modal_scope.count() > 0 and modal_scope.is_visible():
                    btn = (
                        modal_scope.locator("button, a, [role='button']")
                        .filter(has_text=add_sched_re)
                        .first
                    )
                    if btn.count() > 0 and btn.is_visible():
                        print("         🎯 Modal-scoped click: 'Add Schedule'")
                        btn.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        btn.click(force=True)
                        self._wait_for_long_loading(page)
                        return True

                # Fallback to global search (in case dialog isn't marked .show)
                btn2 = (
                    page.locator("button, a, [role='button']")
                    .filter(has_text=add_sched_re)
                    .first
                )
                if btn2.count() > 0 and btn2.is_visible():
                    print("         🎯 Global click fallback: 'Add Schedule'")
                    btn2.scroll_into_view_if_needed()
                    time.sleep(0.2)
                    btn2.click(force=True)
                    self._wait_for_long_loading(page)
                    return True
        except Exception as _add_sched_e:
            print(
                f"         ⚠️ Modal-scoped 'Add Schedule' click failed: {_add_sched_e}"
            )

        try:
            if target_clean.lower().strip() == "pvp":
                time.sleep(0.8)
                pvp_re = re.compile(r"^\s*pvp\s*$", re.IGNORECASE)
                candidates = page.locator(
                    "button, a, li, span, div[role='button'], .nav-link, .nav-tabs .nav-link, [role='tab']"
                ).filter(has_text=pvp_re)
                if candidates.count() > 0:
                    for i in range(min(candidates.count(), 6)):
                        cand = candidates.nth(i)
                        if cand.is_visible():
                            print("         🎯 PVP targeted click (exact)")
                            cand.scroll_into_view_if_needed()
                            time.sleep(0.2)
                            cand.click(force=True)
                            self._wait_for_long_loading(page)
                            return True

                # Fallback: contains match (handles line breaks / extra text)
                candidates2 = page.locator(
                    "button, a, li, span, div[role='button'], .nav-link, .nav-tabs .nav-link, [role='tab']"
                ).filter(has_text=re.compile(r"pvp", re.IGNORECASE))
                for i in range(min(candidates2.count(), 6)):
                    cand = candidates2.nth(i)
                    if cand.is_visible():
                        print("         🎯 PVP targeted click (contains)")
                        cand.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        cand.click(force=True)
                        self._wait_for_long_loading(page)
                        return True
        except Exception as _pvp_e:
            print(f"         ⚠️ PVP targeted click error: {_pvp_e}")

        # Special reliable retry for "Add Event" (often appears after selecting a tab)
        try:
            if "add event" in target_clean.lower():
                # Primary + fallback patterns (UI may render "Add" and "Event" with extra spacing/newlines)
                add_event_re = re.compile(r"Add\s*Event", re.IGNORECASE)
                add_event_re_fallback = re.compile(
                    r"(Add.*Event|Event.*Add)", re.IGNORECASE
                )

                # Search in likely active contexts first, then global.
                add_event_containers = [
                    ".modal.show",
                    ".modal.in",
                    "[role='dialog']:visible",
                    ".swal2-popup:visible",
                    ".tab-pane.active",
                    ".tab-content .active",
                    "main",
                    "body",
                ]

                # Retry loop (UI may render after animation / load)
                for _ in range(16):
                    try:
                        # 1) Context-aware candidates
                        for csel in add_event_containers:
                            container = page.locator(csel).first
                            if container.count() == 0 or not container.is_visible():
                                continue

                            candidates = container.locator(
                                "button, a, div[role='button'], span[role='button'], li"
                            ).filter(has_text=add_event_re)

                            if candidates.count() > 0:
                                for i in range(min(candidates.count(), 8)):
                                    cand = candidates.nth(i)
                                    if cand.is_visible():
                                        print(
                                            "         🔁 Retry-click 'Add Event' (active container candidates)"
                                        )
                                        cand.scroll_into_view_if_needed()
                                        time.sleep(0.2)
                                        cand.click(force=True)
                                        self._wait_for_long_loading(page)
                                        return True

                        # 2) Global candidates fallback (text + aria/title heuristics)
                        # Some UIs render "Add Event" as icon-only button with aria-label/title,
                        # so we also try a JS-based click by (add && event) tokens.
                        try:
                            js_clicked = page.evaluate("""
() => {
  const els = Array.from(
    document.querySelectorAll("button, a, [role='button'], li")
  );
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const tokenOk = (text) => {
    const t = (text || "").toLowerCase();
    return t.includes("add") && t.includes("event");
  };

  for (const el of els) {
    try {
      const t =
        (el.innerText || "") +
        " " +
        (el.getAttribute("aria-label") || "") +
        " " +
        (el.getAttribute("title") || "");
      if (tokenOk(t) && visible(el)) {
        el.click();
        return true;
      }
    } catch (e) {}
  }
  return false;
}
""")
                            if js_clicked:
                                print(
                                    "         🔁 Retry-click 'Add Event' (JS add+event heuristic)"
                                )
                                self._wait_for_long_loading(page)
                                return True
                        except:
                            pass

                        global_candidates = page.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        ).filter(has_text=add_event_re)
                        if global_candidates.count() > 0:
                            for i in range(min(global_candidates.count(), 6)):
                                cand = global_candidates.nth(i)
                                if cand.is_visible():
                                    print(
                                        "         🔁 Retry-click 'Add Event' (global fallback)"
                                    )
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True
                    except:
                        pass

                    # 3) Final JS sweep (whole page, split text / icon-only / aria-label cases)
                    # Click the first visible element whose normalized text/aria/title contains BOTH "add" and "event".
                    try:
                        js_clicked2 = page.evaluate("""
() => {
  const tokens = ["add", "event"];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const normalize = (s) => (s || "").toString().toLowerCase().replace(/\\s+/g," ").trim();

  const els = Array.from(document.querySelectorAll("*"));
  for (const el of els) {
    try {
      if (!visible(el)) continue;
      const txt =
        normalize(el.innerText) + " " +
        normalize(el.getAttribute("aria-label")) + " " +
        normalize(el.getAttribute("title"));
      const ok = tokens.every(t => txt.includes(t));
      if (ok) {
        el.click();
        return true;
      }
    } catch (e) {}
  }
  return false;
}
""")
                        if js_clicked2:
                            print(
                                "         🔁 Retry-click 'Add Event' (final JS sweep add+event)"
                            )
                            self._wait_for_long_loading(page)
                            return True
                    except Exception:
                        pass

                    time.sleep(0.4)
        except:
            pass

        # RBE UI: "Contest Superstars" thường nằm trong accordion "Wrapper".
        # Nếu accordion đang collapsed thì phần tử bị ẩn và smart_click không tìm thấy.
        # Try-expand một lần để đảm bảo target có thể visible trước khi click.
        try:
            t = target_clean.lower()
            if t in ("contest superstars", "feeder event") or "contest superstars" in t:
                wrapper_candidates = page.locator(
                    "aside a, #sidebar a, .sidebar a, #left-menu a, "
                    "aside div, #sidebar div, .sidebar div, #left-menu div, "
                    "aside span, #sidebar span, .sidebar span, #left-menu span, "
                    "#left-menu, .sidebar"
                ).filter(has_text=re.compile(r"\bWrapper\b", re.IGNORECASE))

                # Prefer the most "clickable" candidate first
                wrapper_toggle = wrapper_candidates.first
                if wrapper_toggle.count() > 0 and wrapper_toggle.is_visible():
                    print("         🔽 Pre-expand: 'Wrapper' accordion")
                    wrapper_toggle.click(force=True)
                    time.sleep(1.2)

                # If wrapper exists but isn't visible yet, force-click it to expand.
                # NOTE: Do NOT click generic 'text=Wrapper' because it can select the
                # "Wrapper" tab/section (wrong navigation). We only want to expand accordion.
                if wrapper_toggle.count() > 0 and not wrapper_toggle.is_visible():
                    try:
                        print(
                            "         🔽 Pre-expand fallback: force click 'Wrapper' accordion"
                        )
                        wrapper_toggle.click(force=True)
                        time.sleep(1.2)
                    except Exception:
                        pass

                # Targeted DOM search inside Wrapper/sidebar region (more reliable than generic sidebar scan)
                clicked_inside = False
                try:
                    # Be flexible: UI text can include line breaks/spaces, so don't anchor to full-string match.
                    contest_re = re.compile(r"Contest\s*Superstars", re.IGNORECASE)
                    targeted = (
                        page.locator(".sidebar, #left-menu, aside")
                        .locator(
                            "a, button, li, span, div[role='button'], div.menu-item"
                        )
                        .filter(has_text=contest_re)
                    )

                    # Priority: click only items whose *own* text is exactly "Contest Superstars"
                    # (after normalizing whitespace). This avoids clicking accordion/container
                    # elements that merely contain descendant text.
                    contest_exact_re = re.compile(
                        r"^\s*Contest\s*Superstars\s*$", re.IGNORECASE
                    )

                    if targeted.count() > 0:
                        # Click first visible exact match
                        clicked = False
                        for i in range(min(targeted.count(), 8)):
                            cand = targeted.nth(i)
                            if not cand.is_visible():
                                continue

                            try:
                                cand_text = cand.inner_text() or ""
                                cand_norm = re.sub(r"\s+", " ", cand_text).strip()
                            except:
                                cand_norm = ""

                            # Skip obvious wrapper header/container
                            if re.search(r"\bWrapper\b", cand_norm, re.IGNORECASE):
                                continue

                            if contest_exact_re.match(cand_norm):
                                print(
                                    "         🎯 Targeted click (exact): 'Contest Superstars' (inside Wrapper/sidebar)"
                                )
                                cand.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                cand.click(force=True)

                                # Verify selection didn't just stop at Wrapper header
                                time.sleep(1.0)
                                try:
                                    is_active = page.evaluate("""
() => {
  const norm = (s) => (s || "").toString().replace(/\\s+/g," ").trim().toLowerCase();
  const isActiveClass = (el) => {
    const cls = (el && el.className ? el.className : "").toString().toLowerCase();
    return cls.includes('active') || cls.includes('selected') || cls.includes('current');
  };
  const root = document.querySelector('.sidebar, #left-menu, aside') || document.body;
  const els = Array.from(root.querySelectorAll('a, button, li, span, div, [role="button"], .menu-item'));
  const target = 'contest superstars';
  for (const el of els) {
    try {
      const t = norm(el.innerText);
      if (t === target && el.offsetParent !== null && isActiveClass(el)) return true;
    } catch(e) {}
  }
  return false;
}
""")
                                except:
                                    is_active = True  # nếu JS detect fail thì coi như ok để không kẹt

                                if is_active:
                                    self._wait_for_long_loading(page)
                                    clicked = True
                                    return True
                                else:
                                    print(
                                        "         ⚠️ 'Contest Superstars' click did not become active; retrying..."
                                    )
                                    clicked = True
                                    # continue trying other candidates in this loop
                                    continue

                        # Fallback (if exact match fails): click first visible candidate whose text contains contest
                        if not clicked:
                            for i in range(min(targeted.count(), 8)):
                                cand = targeted.nth(i)
                                if not cand.is_visible():
                                    continue
                                try:
                                    cand_text = cand.inner_text() or ""
                                    cand_norm = re.sub(r"\s+", " ", cand_text).strip()
                                except:
                                    cand_norm = ""
                                if re.search(
                                    r"Contest\s*Superstars", cand_norm, re.IGNORECASE
                                ) and not re.search(
                                    r"\bWrapper\b", cand_norm, re.IGNORECASE
                                ):
                                    print(
                                        "         🎯 Targeted click (contains): 'Contest Superstars' (inside Wrapper/sidebar)"
                                    )
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True

                    clicked_inside = targeted.count() > 0
                except Exception as _tgt_e:
                    print(
                        f"         ⚠️ Targeted 'Contest Superstars' click failed: {_tgt_e}"
                    )

                # Text-based fallback across the whole page (handles cases outside sidebar selectors).
                try:
                    text_candidates = page.get_by_text(contest_re).all()
                    visible_text_candidates = [
                        c for c in text_candidates if c.is_visible()
                    ]
                    if visible_text_candidates:
                        for i in range(min(len(visible_text_candidates), 6)):
                            cand = visible_text_candidates[i]
                            print(
                                "         🎯 Text-global fallback click: 'Contest Superstars'"
                            )
                            cand.scroll_into_view_if_needed()
                            time.sleep(0.2)
                            cand.click(force=True)
                            self._wait_for_long_loading(page)
                            return True
                except Exception:
                    pass

                # Extra fallback: sometimes it’s rendered outside sidebar (still as a button/link).
                # Search globally for visible elements containing "Contest Superstars".
                try:
                    contest_re = re.compile(r"Contest\s*Superstars", re.IGNORECASE)
                    global_candidates = (
                        page.locator(
                            "main, section, [role='main'], .container, aside, body"
                        )
                        .locator(
                            "a, button, li, span, div[role='button'], div.menu-item"
                        )
                        .filter(has_text=contest_re)
                    )

                    if global_candidates.count() > 0:
                        for i in range(min(global_candidates.count(), 8)):
                            cand = global_candidates.nth(i)
                            if cand.is_visible():
                                print(
                                    "         🎯 Global fallback click: 'Contest Superstars'"
                                )
                                cand.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                cand.click(force=True)
                                self._wait_for_long_loading(page)
                                return True
                except Exception as _g_e:
                    if not clicked_inside:
                        print(
                            f"         ⚠️ Global fallback for 'Contest Superstars' failed: {_g_e}"
                        )

                # JS-based heuristic fallback (handles aria-label/title-only / split text nodes)
                try:
                    js_clicked = page.evaluate("""
() => {
  const tokens = ["contest", "superstars"];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };

  const els = Array.from(
    document.querySelectorAll("a, button, [role='button'], li, span, div")
  );

  const normalize = (s) => (s || "").toString().toLowerCase().replace(/\\s+/g," ").trim();

  for (const el of els) {
    try {
      if (!visible(el)) continue;
      const txt =
        normalize(el.innerText) + " " +
        normalize(el.getAttribute("aria-label")) + " " +
        normalize(el.getAttribute("title"));
      const ok = tokens.every(t => txt.includes(t));
      if (ok) {
        el.click();
        return true;
      }
    } catch (e) {}
  }
  return false;
}
""")
                    if js_clicked:
                        print("         🔁 JS heuristic click: 'Contest Superstars'")
                        self._wait_for_long_loading(page)
                        return True
                except Exception:
                    pass
        except Exception:
            pass

        # Dropdown option click (select2/chosen/bootstrap/listbox/etc.)
        # Important: PVP/Classic/Fightcard... thường là option nằm trong overlay dropdown,
        # không nằm ở sidebar/tab nên phải ưu tiên tìm trong các container dropdown đang visible.
        try:
            dropdown_option_selectors = [
                ".select2-results__option",
                ".select2-results__option[role='option']",
                ".chosen-results li",
                ".dropdown-menu.show a",
                ".dropdown-menu.show li",
                ".dropdown-menu.show button",
                "[role='listbox'] [role='option']",
                "[role='listbox'] li",
                "[role='listbox'] div",
                "ul[role='listbox'] li",
                ".ui-autocomplete .ui-menu-item-wrapper",
                ".mat-select-panel .mat-option",
                ".rc-virtual-list .rc-virtual-list-holder-inner div",
            ]

            opt_text = target_clean.strip()
            if opt_text:
                opt_regex = re.compile(
                    r"^\s*" + re.escape(opt_text) + r"\s*$", re.IGNORECASE
                )

                for sel in dropdown_option_selectors:
                    candidates = page.locator(sel).filter(has_text=opt_regex).all()
                    # Only click visible ones
                    visible_candidates = [c for c in candidates if c.is_visible()]
                    if visible_candidates:
                        for cand in visible_candidates[:10]:
                            try:
                                print(
                                    f"         🎯 Dropdown option click: '{target_clean}'"
                                )
                                cand.scroll_into_view_if_needed()
                                time.sleep(0.2)
                                cand.click(force=True)
                                self._wait_for_long_loading(page)
                                return True
                            except Exception:
                                continue
        except Exception:
            pass

        # Special deeper search for "Add Event" which often appears in the active panel/modal
        try:
            if "add event" in target_clean.lower():
                containers = [
                    ".modal.show",
                    ".modal.in",
                    "[role='dialog']:visible",
                    ".swal2-popup:visible",
                    ".tab-pane.active",
                    ".tab-content .active",
                    "section:has(.active)",
                    "main",
                    "body",
                ]

                opt_regex = re.compile(r"^\s*Add\s*Event\s*$", re.IGNORECASE)
                for csel in containers:
                    container = page.locator(csel).first
                    if container.count() == 0:
                        continue
                    if not container.is_visible():
                        continue

                    cand = (
                        container.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        )
                        .filter(has_text=opt_regex)
                        .first
                    )
                    if cand.count() > 0 and cand.is_visible():
                        print(
                            "         🎯 Special 'Add Event' click (active modal/panel)"
                        )
                        cand.scroll_into_view_if_needed()
                        time.sleep(0.2)
                        cand.click(force=True)
                        self._wait_for_long_loading(page)
                        return True
        except Exception:
            pass

        _nav_map = {
            "daily reward": "daily_reward",
            "division configuration": "division_configuration",
        }
        nav_id = _nav_map.get(target_clean.lower())
        if nav_id:
            if self._click_sidebar_nav_by_id(page, nav_id, target_clean):
                clicked = True
                if nav_id == "daily_reward":
                    try:
                        page.wait_for_selector(
                            "#start_time_send_daily_reward, [name='start_time_send_daily_reward']",
                            state="visible",
                            timeout=8000,
                        )
                        print("         ✅ Daily Reward tab content loaded")
                    except Exception:
                        print(
                            "         ⚠️ Daily Reward fields not visible after nav click"
                        )
                else:
                    time.sleep(0.8)

        if clicked:
            self._wait_for_long_loading(page)
            return clicked

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
                            "a, button, div[role='button'], li, span, div.menu-item"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .first
                    )
                    if item.count() > 0 and item.is_visible():
                        try:
                            bbox = item.bounding_box()
                            if bbox and bbox["height"] > 120:
                                continue
                        except Exception:
                            pass
                        print(f"         ✅ Found '{target_text}' in Sidebar ({sel})")
                        item.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        item.click()
                        clicked = True
                        break
            except:
                continue

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

        if not clicked:
            panel_selectors = [
                "button[class*='store-sidebar']",
                "button[class*='sidebar-item']",
                "button[class*='panel-item']",
                ".list-group-item",
                "li[class*='item']",
                "li[class*='section']",
                ".row-item",
                ".section-item",
                "div[class*='sort']",
                "div[class*='item']",
                "div[class*='draggable']",
            ]
            for panel_sel in panel_selectors:
                try:
                    item = (
                        page.locator(panel_sel)
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .first
                    )
                    if item.count() > 0 and item.is_visible():
                        try:
                            bbox = item.bounding_box()
                            if bbox and bbox["height"] > 120:
                                continue
                        except Exception:
                            pass
                        text_preview = item.inner_text().strip()[:60]
                        print(
                            f"         ✅ Found panel item '{text_preview}' via {panel_sel}"
                        )
                        item.scroll_into_view_if_needed()
                        time.sleep(0.3)
                        item.click()
                        clicked = True
                        break
                except:
                    continue

        if not clicked:
            # NOTE: Don't short-circuit PVE accordion expanders.
            # Otherwise "Normal Matches" (aria-expanded=false) will be treated as "already active"
            # and we never click the caret/toggle, so "Match 1" content can't be reached.
            target_lower_for_guard = target_clean.lower()
            is_pve_accordion_target = any(
                k in target_lower_for_guard for k in ["chapter info", "normal matches"]
            ) or bool(re.search(r"\bmatch\b", target_lower_for_guard, re.IGNORECASE))

            if not is_pve_accordion_target:
                try:
                    active_items = (
                        page.locator(
                            "a.active, li.active, div.active, [class*='selected']"
                        )
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .all()
                    )

                    for item in active_items:
                        if item.is_visible():
                            item_text = item.inner_text().strip()
                            if target_clean.lower() in item_text.lower():
                                if target_clean.lower() == "daily reward":
                                    if self._is_daily_reward_content_loaded(page):
                                        print(
                                            f"         ℹ️ Element '{target_text}' is already active/selected"
                                        )
                                        clicked = True
                                        break
                                    print(
                                        f"         ⚠️ '{target_text}' nav active but content missing — re-clicking"
                                    )
                                    if self._click_sidebar_nav_by_id(
                                        page, "daily_reward", target_clean
                                    ):
                                        clicked = True
                                        time.sleep(1)
                                    break
                                print(
                                    f"         ℹ️ Element '{target_text}' is already active/selected"
                                )
                                clicked = True
                                break
                except:
                    pass

        if not clicked:
            # Dialog/modal thường chứa nút "Add Event" sau khi chọn tab/menu
            try:
                dialog_selectors = [
                    ".modal.show",
                    ".modal.in",
                    ".swal2-popup:visible",
                    "[role='dialog']:visible",
                    ".ui-dialog:visible",
                ]
                for ds in dialog_selectors:
                    dialogs = page.locator(ds)
                    if dialogs.count() > 0:
                        btn_dialog = dialogs.first.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        ).filter(
                            has_text=re.compile(
                                rf"^\s*{re.escape(target_clean)}\s*$",
                                re.IGNORECASE,
                            )
                        )
                        if btn_dialog.count() > 0:
                            for i in range(min(btn_dialog.count(), 5)):
                                cand = btn_dialog.nth(i)
                                if cand.is_visible():
                                    print(f"         🎯 Dialog click: '{target_text}'")
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True

                        # Partial match (e.g. "Add Event" text wraps)
                        btn_dialog2 = dialogs.first.locator(
                            "button, a, div[role='button'], span[role='button'], li"
                        ).filter(
                            has_text=re.compile(
                                re.escape(target_clean),
                                re.IGNORECASE,
                            )
                        )
                        if btn_dialog2.count() > 0:
                            for i in range(min(btn_dialog2.count(), 5)):
                                cand = btn_dialog2.nth(i)
                                if cand.is_visible():
                                    print(
                                        f"         🎯 Dialog partial click: '{target_text}'"
                                    )
                                    cand.scroll_into_view_if_needed()
                                    time.sleep(0.2)
                                    cand.click(force=True)
                                    self._wait_for_long_loading(page)
                                    return True
            except:
                pass

            print("         ⚠️ Sidebar/Tab not found. Trying generic text match...")

            try:
                element = (
                    page.locator("button, a, div[role='button'], span[role='button']")
                    .filter(
                        has_text=re.compile(
                            re.escape(target_clean).replace(r"\ ", r"\s+"),
                            re.IGNORECASE,
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

            if not clicked:
                try:
                    element = (
                        page.locator(
                            "button, a, div[role='button'], span[role='button'], li, div.menu-item"
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

            if not clicked:
                try:
                    candidates = (
                        page.locator("div, li, span, tr, td")
                        .filter(
                            has_text=re.compile(re.escape(target_clean), re.IGNORECASE)
                        )
                        .all()
                    )
                    visible = [el for el in candidates if el.is_visible()]
                    if visible:
                        best = min(visible, key=lambda el: len(el.inner_text().strip()))
                        text_preview = best.inner_text().strip()[:80]
                        if target_clean.lower() in text_preview.lower():
                            print(
                                f"         ✅ Strategy D broad match: '{text_preview}'"
                            )
                            best.scroll_into_view_if_needed()
                            time.sleep(0.3)
                            best.click(force=True)
                            clicked = True
                except:
                    pass

        if clicked:
            self._wait_for_long_loading(page)
            return True

        # --------------------------
        # Slow-load retry (fix for cases where tab/header appears late)
        # --------------------------
        try:
            wait_timeout_ms = 8000
            tab_re = re.compile(re.escape(target_clean), re.IGNORECASE)

            late_tab = (
                page.locator(
                    "a[data-toggle='tab'], button[data-toggle='tab'], [role='tab'], "
                    ".nav-tabs .nav-link, li.nav-item a, li.tab-item a, "
                    "button, a"
                )
                .filter(has_text=tab_re)
                .first
            )

            late_tab.wait_for(state="visible", timeout=wait_timeout_ms)
            late_tab.scroll_into_view_if_needed()
            time.sleep(0.3)
            late_tab.click()
            self._wait_for_long_loading(page)
            return True
        except Exception:
            pass

        print(f"         ❌ FAILED: Cannot find clickable element '{target_text}'")
        return False

    def _wait_for_long_loading(self, page):
        print("         ⏳ Checking for Loaders/Spinners...")

        spinner_selectors = [
            # NOTE: avoid false positives like cursor:progress on normal pages.
            # Keeping only more deterministic spinners.
            "i.fa.fa-cog.fa-spin",
            "i.fa-cog.fa-spin",
            ".fa-spin",
            ".spinner-border",
            ".spinner-grow",
            "[role='status']",
            "[class*='loading']",
            "[class*='spinner']",
            "[class*='loader']",
            ".loading",
            ".spinner",
            ".loader",
            ".swal2-loading",
            ".blockUI",
            "div:has-text('Loading')",
        ]

        def _any_spinner_visible():
            for sel in spinner_selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=200):
                        return sel
                except Exception:
                    pass
            return None

        active_spinner = None

        for _ in range(4):
            active_spinner = _any_spinner_visible()
            if active_spinner:
                break
            time.sleep(0.25)

        if active_spinner:
            print(
                f"         🔄 Spinner DETECTED: '{active_spinner}'. Waiting for it to finish..."
            )
            try:
                # Spinner heuristics: avoid hard-stalling on generic loader overlays
                # (e.g. pages that keep an always-on .loader / [class*='loader'] element).
                spinner_str = str(active_spinner)
                if "has-text('Loading')" in spinner_str:
                    wait_timeout = 2000
                elif (
                    "class*='loader'" in spinner_str
                    or "'.loader'" in spinner_str
                    or ".loader" in spinner_str
                ):
                    # Generic loader: reduce hard wait to avoid step-level timeouts.
                    wait_timeout = 2500
                else:
                    wait_timeout = 2000

                page.locator(active_spinner).first.wait_for(
                    state="hidden", timeout=wait_timeout
                )
                print("         ✅ Spinner finished (Main content loaded).")
            except Exception:
                print(
                    "         ℹ️ Spinner wait timed out (possible false positive). Continuing execution."
                )
        else:
            print(
                "         ℹ️ No spinner detected immediately. Waiting for network idle just in case."
            )

        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except Exception:
            pass

        time.sleep(1.0)

        # PVE heavy render: React shows skeletons + uses aria-busy while loading.
        # If we proceed too early, Normal Matches/Match panels are not fully interactive
        # and select2 (SSDB -> SSGroup ID) might not exist yet.
        try:
            for _ in range(10):
                try:
                    busy_visible = (
                        page.locator("[aria-busy='true']:visible").count() > 0
                    )
                except:
                    busy_visible = False

                try:
                    skeleton_visible = page.locator(".b-skeleton:visible").count() > 0
                except:
                    skeleton_visible = False

                # Match panels sometimes use vld-icon spinner (you provided HTML:
                # <div class="vld-icon">...</div>)
                try:
                    skeleton_visible = page.locator(".b-skeleton:visible").count() > 0
                except:
                    skeleton_visible = False

                # PVE Match panels may show vld-icon loader while React data renders
                # (your provided HTML: <div class="vld-icon">...</div>)
                try:
                    vld_visible = page.locator(".vld-icon:visible").count() > 0
                except:
                    vld_visible = False

                if not busy_visible and not skeleton_visible and not vld_visible:
                    break
                time.sleep(0.3)
        except:
            pass

    def _is_sidebar_item(self, page, text):
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
